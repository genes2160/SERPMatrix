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


class HealthCheckView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"status": "ok"})


class ClientSiteView(APIView):

    def post(self, request):
        serializer = CreateSiteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        site = site_service.create_site(**serializer.validated_data)

        return Response(
            SiteResponseSerializer(site).data,
            status=status.HTTP_201_CREATED,
        )

    def get(self, request, site_id):
        site = get_object_or_404(ClientSite, id=site_id)
        return Response(SiteResponseSerializer(site).data)


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