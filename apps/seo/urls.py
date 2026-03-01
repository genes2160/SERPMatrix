from django.urls import path
from apps.seo.views import (
    HealthCheckView,
    ClientSiteView,
    AuditRunView,
    RetryRunView,
)

urlpatterns = [
    path("health/", HealthCheckView.as_view()),

    path("sites", ClientSiteView.as_view()),
    path("sites/<uuid:site_id>", ClientSiteView.as_view()),

    path("sites/<uuid:site_id>/runs", AuditRunView.as_view()),
    path("runs/<uuid:run_id>", AuditRunView.as_view()),

    path("runs/<uuid:run_id>/retry", RetryRunView.as_view()),
]