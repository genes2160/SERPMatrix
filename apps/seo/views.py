from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from django.shortcuts import get_object_or_404

from apps.seo.models import ClientSite, AuditRun
from apps.seo.serializers import (
    CreateSiteSerializer,
    SiteResponseSerializer,
    CreateRunSerializer,
    RunResponseSerializer,
)
from apps.seo.services import site_service, run_service
from django.db import connections
from django.db.utils import OperationalError
from django.conf import settings
import redis


class HealthCheckView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        health_status = {
            "status": "ok",
            "services": {
                "database": "ok",
                "redis": "ok",
            }
        }

        overall_ok = True

        # -----------------------------
        # Database check
        # -----------------------------
        try:
            db_conn = connections["default"]
            db_conn.cursor().execute("SELECT 1;")
        except OperationalError:
            health_status["services"]["database"] = "down"
            overall_ok = False

        # -----------------------------
        # Redis check
        # -----------------------------
        try:
            redis_url = settings.CELERY_BROKER_URL
            r = redis.from_url(redis_url)
            r.ping()
        except Exception:
            health_status["services"]["redis"] = "down"
            overall_ok = False

        if not overall_ok:
            health_status["status"] = "degraded"
            return Response(health_status, status=503)

        return Response(health_status)

class ClientSiteView(APIView):

    def post(self, request):
        serializer = CreateSiteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        site = site_service.create_site(**serializer.validated_data)

        return Response(
            SiteResponseSerializer(site).data,
            status=status.HTTP_201_CREATED,
        )

    def get(self, request, site_id=None):
        if site_id:
            site = get_object_or_404(ClientSite, id=site_id)
            return Response(SiteResponseSerializer(site).data)

        # LIST
        sites = ClientSite.objects.all().order_by("-created_at")
        return Response(SiteResponseSerializer(sites, many=True).data)
class AuditRunView(APIView):

    def post(self, request, site_id):
        site = get_object_or_404(ClientSite, id=site_id)

        serializer = CreateRunSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        run = run_service.create_run(
            site=site,
            config=serializer.validated_data.get("config", {}),
        )

        return Response(
            RunResponseSerializer(run).data,
            status=status.HTTP_201_CREATED,
        )

    def get(self, request, run_id):
        run = get_object_or_404(AuditRun, id=run_id)
        return Response(RunResponseSerializer(run).data)


class RetryRunView(APIView):

    def post(self, request, run_id):
        run = get_object_or_404(AuditRun, id=run_id)
        run = run_service.retry_run(run=run)

        return Response(RunResponseSerializer(run).data)