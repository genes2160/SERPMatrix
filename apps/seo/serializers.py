from rest_framework import serializers
from apps.seo.models import ClientSite, AuditRun


class CreateSiteSerializer(serializers.Serializer):
    url = serializers.URLField()
    geo = serializers.CharField(required=False, default="GH")
    language = serializers.CharField(required=False, default="en")
    device = serializers.CharField(required=False, default="desktop")



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
        
class SiteResponseSerializer(serializers.ModelSerializer):
    runs = RunResponseSerializer(many=True, read_only=True)

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
            "runs",  # added
        ]


class CreateRunSerializer(serializers.Serializer):
    config = serializers.JSONField(required=False, default=dict)

    def validate_config(self, value):
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError("config must be a JSON object (dict)")
        return value