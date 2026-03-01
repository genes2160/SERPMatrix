# apps/seo/views.py

from rest_framework.generics import (
    GenericAPIView,
    ListAPIView,
    RetrieveAPIView,
    CreateAPIView,
)
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from drf_spectacular.utils import extend_schema
from django.shortcuts import get_object_or_404

from django.db import connections
from django.db.utils import OperationalError
from django.conf import settings
import redis

from apps.seo.models import ClientSite, AuditRun
from apps.seo.serializers import (
    CreateSiteSerializer,
    SiteResponseSerializer,
    CreateRunSerializer,
    RunResponseSerializer,
)
from apps.seo.services.site_service import create_site
from apps.seo.services.run_service import run_service

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
    queryset = ClientSite.objects.all().order_by("-created_at")
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
        sites = self.get_queryset()
        return Response(SiteResponseSerializer(sites, many=True).data)

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