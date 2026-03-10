# apps/seo/views.py

from apps.seo.constants import _derive_run_status_from_steps
from rest_framework.generics import (
    GenericAPIView,
    ListAPIView,
    RetrieveAPIView,
    CreateAPIView,
)
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
    queryset = ClientSite.objects.all().prefetch_related("runs").order_by("-created_at")
    serializer_class = CreateSiteSerializer

    @extend_schema(
        request=CreateSiteSerializer,
        responses=SiteResponseSerializer,
    )
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        site = create_site(**serializer.validated_data, user=request.user)
        return Response(SiteResponseSerializer(site).data, status=status.HTTP_201_CREATED)

    @extend_schema(responses=SiteResponseSerializer(many=True))
    def get(self, request):
        from django.db.models import Count
        sites = ClientSite.objects.filter(user=request.user).annotate(run_count=Count("runs")).order_by("-created_at")
        return Response(SiteResponseSerializer(sites, many=True).data)
    
class SiteRunsListView(ListAPIView):
    serializer_class = RunResponseSerializer

    def get_queryset(self):
        return AuditRun.objects.filter(
            client_site_id=self.kwargs["site_id"],
            client_site__user=request.user,  # scope to owner
        ).order_by("-created_at")


class ClientSiteDetailView(RetrieveAPIView):
    serializer_class = SiteResponseSerializer
    lookup_field = "id"
    lookup_url_kwarg = "site_id"

    def get_queryset(self):
        return ClientSite.objects.filter(user=self.request.user)

  
class AuditRunCreateView(GenericAPIView):
    serializer_class = CreateRunSerializer

    @extend_schema(
        request=CreateRunSerializer,
        responses=RunResponseSerializer,
    )
    def post(self, request, site_id):
        site = get_object_or_404(ClientSite, id=site_id)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        run = run_service.create_run(
            site=site,
            config=serializer.validated_data.get("config", {}),
        )

        return Response(
            RunResponseSerializer(run).data,
            status=status.HTTP_201_CREATED,
        )

class AuditRunDetailView(RetrieveAPIView):
    queryset = AuditRun.objects.all()
    serializer_class = RunResponseSerializer
    lookup_field = "id"
    lookup_url_kwarg = "run_id"
    
class RetryRunView(GenericAPIView):

    @extend_schema(responses=RunResponseSerializer)
    def post(self, request, run_id):
        run = get_object_or_404(AuditRun, id=run_id)
        force = request.data.get("force", False)
        if force:
            run = run_service.force_retry_run(run=run)
        else:
            run = run_service.retry_run(run=run)
        return Response(RunResponseSerializer(run).data)


 
class AuditRunDashboardView(APIView):
    def get(self, request, run_id):
        run = get_object_or_404(
            AuditRun.objects.select_related("client_site"),
            id=run_id,
            client_site__user=request.user,  # prevent cross-user access
        )

        steps_qs = run.steps.order_by("created_at")
        steps = list(steps_qs.values())  # keep your current response shape

        # NEW: derived status (no DB write)
        derived_status = _derive_run_status_from_steps(steps_qs)

        # NEW: derived finished_at (optional)
        derived_finished_at = run.finished_at
        if derived_status in (AuditRun.Status.SUCCESS, AuditRun.Status.FAILED):
            derived_finished_at = run.finished_at or timezone.now()
        else:
            derived_finished_at = None

        recommendations = list(
            run.recommendations.values(
                "id", "keyword", "action_type", "priority", "reason_text", "expected_impact"
            )
        )

        run_data = RunResponseSerializer(run).data
        # NEW: override in response only
        run_data["status"] = derived_status
        run_data["finished_at"] = derived_finished_at

        import json as _json

        # parse ai_summary safely — old runs stored raw JSON, new runs store plain text
        ai_summary = run.ai_summary or ""
        if ai_summary.strip().startswith("[") or ai_summary.strip().startswith("{"):
            try:
                parsed = _json.loads(ai_summary)
                if isinstance(parsed, list):
                    # old format — render as recommendations directly
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
                    # old format — extract as pre-formatted text, real recs come from DB
                    ai_summary = f"Legacy format: {len(parsed)} recommendations stored as raw JSON. Trigger a new run to get a proper summary."
                    high   = [r for r in parsed if r.get("priority") == "high"]
                    med    = [r for r in parsed if r.get("priority") == "med"]
                    topics = list({r.get("action_type") for r in parsed if r.get("action_type")})
                    ai_summary = (
                        f"Analysis found {len(parsed)} recommendations: "
                        f"{len(high)} high priority, {len(med)} medium priority. "
                        f"Key focus areas: {', '.join(topics)}."
                        f"\nHowever this is a Legacy format: {len(parsed)} recommendations stored as raw JSON. Kindly trigger a new run to get a proper summary."
                    )
                elif isinstance(parsed, dict):
                    ai_summary = parsed.get("summary", ai_summary)
                    recommendations = parsed.get("recommendations", recommendations)
            except Exception:
                pass  # leave as-is

        return Response({
            "run": run_data,
            "steps": steps,
            "ai": {
                "summary": ai_summary,
                "recommendations": recommendations,
                "meta": run.ai_meta or {},
            },
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
        from apps.seo.constants import _derive_run_status_from_steps

        total_sites = ClientSite.objects.count()

        runs =  AuditRun.objects.filter(
            client_site__user=request.user
        ).prefetch_related("steps").all()

        # runs = AuditRun.objects.prefetch_related("steps").all()

        total_runs = runs.count()

        running_runs = 0
        failed_runs = 0
        success_runs = 0
        queued_runs = 0

        for run in runs:
            derived_status = _derive_run_status_from_steps(run.steps.all())

            if derived_status == AuditRun.Status.RUNNING:
                running_runs += 1
            elif derived_status == AuditRun.Status.FAILED:
                failed_runs += 1
            elif derived_status == AuditRun.Status.SUCCESS:
                success_runs += 1
            else:
                queued_runs += 1

        avg_visibility = KeywordResult.objects.aggregate(
            Avg("visibility_score")
        )["visibility_score__avg"] or 0

        return Response({
            "total_sites": total_sites,
            "total_runs": total_runs,
            "running_runs": running_runs,
            "failed_runs": failed_runs,
            "success_runs": success_runs,
            "queued_runs": queued_runs,  # NEW
            "avg_visibility_score": avg_visibility,
        })
        

class NotificationListView(APIView):
    def get(self, request, run_id):
        run = get_object_or_404(AuditRun, id=run_id)
        notifications = run.notifications.all().values(
            "id", "event_type", "title", "body", "meta", "read", "created_at"
        )
        return Response(list(notifications))

class UserNotificationsView(APIView):
    def get(self, request):
        notifications = Notification.objects.filter(
            user=request.user
        ).order_by("-created_at").values(
            "id", "event_type", "title", "body", "meta", "read", "created_at", "audit_run_id"
        )
        return Response(list(notifications))

class NotificationMarkReadView(APIView):
    def patch(self, request, notification_id):
        from django.shortcuts import get_object_or_404
        notification = get_object_or_404(
            Notification,
            id=notification_id,
        )
        notification.read = True
        notification.save(update_fields=["read"])
        return Response({"id": notification_id, "read": True})
    
