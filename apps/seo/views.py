# apps/seo/views.py

from apps.seo.constants import _derive_run_status_from_steps
from rest_framework.generics import (
    GenericAPIView,
    ListAPIView,
    RetrieveAPIView,
    CreateAPIView,
)
from django.db.models import Count
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from drf_spectacular.utils import extend_schema
from django.shortcuts import get_object_or_404

from django.db import connections
from django.db.utils import OperationalError
from django.conf import settings
import redis

from apps.seo.models import ClientSite, AuditRun, KeywordResult
from apps.seo.serializers import (
    CreateSiteSerializer,
    SiteResponseSerializer,
    CreateRunSerializer,
    RunResponseSerializer,
)
from apps.seo.services.site_service import create_site
from apps.seo.services.run_service import run_service
from django.utils import timezone
from apps.seo.models import Notification

class HealthCheckView(GenericAPIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(responses=dict)
    def get(self, request):
        health_status = {
            "status": "ok",
            "services": {
                "database": "ok",
                "redis": "ok",
            }
        }

        overall_ok = True

        # Database check
        try:
            db_conn = connections["default"]
            db_conn.cursor().execute("SELECT 1;")
        except OperationalError:
            health_status["services"]["database"] = "down"
            overall_ok = False

        # Redis check
        try:
            r = redis.from_url(settings.CELERY_BROKER_URL)
            r.ping()
        except Exception:
            health_status["services"]["redis"] = "down"
            overall_ok = False

        if not overall_ok:
            health_status["status"] = "degraded"
            return Response(health_status, status=503)

        return Response(health_status)

class ClientSiteListCreateView(GenericAPIView):
    serializer_class = CreateSiteSerializer

    def get_queryset(self):
        # Explicitly scoped to current user, with prefetch for performance
        return (
            ClientSite.objects.filter(user=self.request.user)
            .prefetch_related("runs")  # prefetch related AuditRun objects
            .annotate(run_count=Count("runs"))  # optional count
            .order_by("-created_at")
        )

    @extend_schema(request=CreateSiteSerializer, responses=SiteResponseSerializer)
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        site = create_site(**serializer.validated_data, user=request.user)
        return Response(SiteResponseSerializer(site).data, status=status.HTTP_201_CREATED)

    @extend_schema(responses=SiteResponseSerializer(many=True))
    def get(self, request):
        sites = self.get_queryset()
        return Response(SiteResponseSerializer(sites, many=True).data)
    
class SiteRunsListView(ListAPIView):
    serializer_class = RunResponseSerializer

    def get_queryset(self):
        return (
            AuditRun.objects.filter(
                client_site_id=self.kwargs["site_id"],
                client_site__user=self.request.user,  # scope to owner
            )
            .prefetch_related("steps")  # optimize steps access
            .order_by("-created_at")
        )


class ClientSiteDetailView(RetrieveAPIView):
    serializer_class = SiteResponseSerializer
    lookup_field = "id"
    lookup_url_kwarg = "site_id"

    def get_queryset(self):
        return ClientSite.objects.filter(user=self.request.user).prefetch_related("runs")

  
class AuditRunCreateView(GenericAPIView):
    serializer_class = CreateRunSerializer

    @extend_schema(request=CreateRunSerializer, responses=RunResponseSerializer)
    def post(self, request, site_id):
        site = get_object_or_404(ClientSite, id=site_id, user=request.user)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        run = run_service.create_run(
            site=site,
            config=serializer.validated_data.get("config", {}),
        )

        return Response(RunResponseSerializer(run).data, status=status.HTTP_201_CREATED)


class AuditRunDetailView(RetrieveAPIView):
    serializer_class = RunResponseSerializer
    lookup_field = "id"
    lookup_url_kwarg = "run_id"

    def get_queryset(self):
        return AuditRun.objects.filter(client_site__user=self.request.user).prefetch_related("steps")
    
class RetryRunView(GenericAPIView):

    @extend_schema(responses=RunResponseSerializer)
    def post(self, request, run_id):
        run = get_object_or_404(
            AuditRun,
            id=run_id,
            client_site__user=request.user
        )
        force = request.data.get("force", False)
        if force:
            run = run_service.force_retry_run(run=run)
        else:
            run = run_service.retry_run(run=run)
        return Response(RunResponseSerializer(run).data)


 
class AuditRunDashboardView(APIView):
    def get(self, request, run_id):
        run = get_object_or_404(
            AuditRun.objects.select_related("client_site").prefetch_related("steps"),
            id=run_id,
            client_site__user=request.user,
        )

        steps_qs = run.steps.order_by("created_at")
        steps = list(steps_qs.values())
        derived_status = _derive_run_status_from_steps(steps_qs)
        derived_finished_at = run.finished_at if derived_status in (AuditRun.Status.SUCCESS, AuditRun.Status.FAILED) else None

        recommendations = list(
            run.recommendations.values(
                "id", "keyword", "action_type", "priority", "reason_text", "expected_impact"
            )
        )

        run_data = RunResponseSerializer(run).data
        run_data["status"] = derived_status
        run_data["finished_at"] = derived_finished_at

        # ---- LEGACY AI SUMMARY HANDLING ----
        import json as _json
        ai_summary = run.ai_summary or ""
        try:
            if ai_summary.strip().startswith("[") or ai_summary.strip().startswith("{"):
                parsed = _json.loads(ai_summary)
                if isinstance(parsed, list):
                    recommendations = [
                        {
                            "id": None,
                            "keyword": r.get("keyword"),
                            "action_type": r.get("action_type"),
                            "priority": r.get("priority"),
                            "reason_text": r.get("reason_text"),
                            "expected_impact": r.get("expected_impact"),
                        }
                        for r in parsed if isinstance(r, dict)
                    ]
                    high   = [r for r in parsed if r.get("priority") == "high"]
                    med    = [r for r in parsed if r.get("priority") == "med"]
                    topics = list({r.get("action_type") for r in parsed if r.get("action_type")})
                    ai_summary = (
                        f"Analysis found {len(parsed)} recommendations: "
                        f"{len(high)} high priority, {len(med)} medium priority. "
                        f"Key focus areas: {', '.join(topics)}."
                        f"\nLegacy format: {len(parsed)} recommendations stored as raw JSON. Trigger a new run to get a proper summary."
                    )
                elif isinstance(parsed, dict):
                    ai_summary = parsed.get("summary", ai_summary)
                    recommendations = parsed.get("recommendations", recommendations)
        except Exception:
            pass  # leave as-is
        # ------------------------------------

        return Response({
            "run": run_data,
            "steps": steps,
            "ai": {"summary": ai_summary, "recommendations": recommendations, "meta": run.ai_meta or {}},
            "system": run.summary or {},
            "site": {
                "url": run.client_site.url,
                "normalized_url": run.client_site.normalized_url,
                "geo": run.client_site.geo,
                "language": run.client_site.language,
                "device": run.client_site.device,
                "niche_label": run.client_site.niche_label,
            },
        })
        
            
class DashboardOverviewView(APIView):
    def get(self, request):
        from django.db.models import Avg

        total_sites = ClientSite.objects.count()  # old behavior
        runs = AuditRun.objects.prefetch_related("steps").all()  # old behavior

        total_runs = runs.count()
        running_runs = failed_runs = success_runs = queued_runs = 0

        for run in runs:
            status = _derive_run_status_from_steps(run.steps.all())
            if status == AuditRun.Status.RUNNING: running_runs += 1
            elif status == AuditRun.Status.FAILED: failed_runs += 1
            elif status == AuditRun.Status.SUCCESS: success_runs += 1
            else: queued_runs += 1

        avg_visibility = KeywordResult.objects.aggregate(Avg("visibility_score"))["visibility_score__avg"] or 0

        return Response({
            "total_sites": total_sites,
            "total_runs": total_runs,
            "running_runs": running_runs,
            "failed_runs": failed_runs,
            "success_runs": success_runs,
            "queued_runs": queued_runs,
            "avg_visibility_score": avg_visibility,
        })

class NotificationListView(APIView):
    def get(self, request, run_id):
        run = get_object_or_404(AuditRun, id=run_id, client_site__user=request.user)
        return Response(list(run.notifications.all().values("id","event_type","title","body","meta","read","created_at")))

class UserNotificationsView(APIView):
    def get(self, request):
        return Response(list(Notification.objects.filter(user=request.user).order_by("-created_at").values(
            "id","event_type","title","body","meta","read","created_at","audit_run_id"
        )))

class NotificationMarkReadView(APIView):
    def patch(self, request, notification_id):
        notification = get_object_or_404(Notification, id=notification_id, user=request.user)
        notification.read = True
        notification.save(update_fields=["read"])
        return Response({"id": notification_id, "read": True})