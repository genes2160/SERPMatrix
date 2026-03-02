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

        site = create_site(**serializer.validated_data)

        return Response(
            SiteResponseSerializer(site).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(responses=SiteResponseSerializer(many=True))
    def get(self, request):
        from django.db.models import Count
        sites = self.get_queryset().annotate(run_count=Count("runs"))
        return Response(SiteResponseSerializer(sites, many=True).data)
    
class SiteRunsListView(ListAPIView):
    serializer_class = RunResponseSerializer

    def get_queryset(self):
        return AuditRun.objects.filter(
            client_site_id=self.kwargs["site_id"]
        ).order_by("-created_at")

class ClientSiteDetailView(RetrieveAPIView):
    queryset = ClientSite.objects.all()
    serializer_class = SiteResponseSerializer
    lookup_field = "id"
    lookup_url_kwarg = "site_id"
    
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
        run = run_service.retry_run(run=run)

        return Response(RunResponseSerializer(run).data)


 
class AuditRunDashboardView(APIView):
    def get(self, request, run_id):
        run = get_object_or_404(AuditRun, id=run_id)

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

        return Response({
            "run": run_data,
            "steps": steps,
            "ai": {
                "summary": run.ai_summary,
                "recommendations": run.ai_meta or [],
            },
            "system": {
                "summary": run.summary,
                "recommendations": recommendations,
            },
        })

class DashboardOverviewView(APIView):

    def get(self, request):
        from django.db.models import Avg
        from apps.seo.constants import _derive_run_status_from_steps

        total_sites = ClientSite.objects.count()

        runs = AuditRun.objects.prefetch_related("steps").all()

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