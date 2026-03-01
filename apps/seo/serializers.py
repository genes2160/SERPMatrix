from rest_framework import serializers
from apps.seo.models import ClientSite, AuditRun


class CreateSiteSerializer(serializers.Serializer):
    url = serializers.URLField()
    geo = serializers.CharField(required=False, default="GH")
    language = serializers.CharField(required=False, default="en")
    device = serializers.CharField(required=False, default="desktop")


class SiteResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClientSite
        fields = [
            "id",
            "url",
            "normalized_url",
            "geo",
            "language",
            "device",
            "created_at",
        ]


class CreateRunSerializer(serializers.Serializer):
    config = serializers.JSONField(required=False)


class RunResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditRun
        fields = [
            "id",
            "client_site",
            "status",
            "config",
            "created_at",
            "started_at",
            "finished_at",
        ]