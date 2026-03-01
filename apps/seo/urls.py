from django.urls import path
from apps.seo.views import (
    AuditRunCreateView,
    AuditRunDetailView,
    ClientSiteDetailView,
    ClientSiteListCreateView,
    HealthCheckView,
    RetryRunView,
)

urlpatterns = [
    path("health/", HealthCheckView.as_view()),

    path("sites", ClientSiteListCreateView.as_view()),
    path("sites/<uuid:site_id>", ClientSiteDetailView.as_view()),

    path("sites/<uuid:site_id>/runs", AuditRunCreateView.as_view()),
    path("runs/<uuid:run_id>", AuditRunDetailView.as_view()),
    path("runs/<uuid:run_id>/retry", RetryRunView.as_view()),
]