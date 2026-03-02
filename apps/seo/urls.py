from django.urls import path
from apps.seo.views import (
    AuditRunCreateView,
    AuditRunDashboardView,
    AuditRunDetailView,
    ClientSiteDetailView,
    ClientSiteListCreateView,
    DashboardOverviewView,
    HealthCheckView,
    RetryRunView,
    SiteRunsListView,
)

urlpatterns = [
    path("health/", HealthCheckView.as_view()),

    path("sites", ClientSiteListCreateView.as_view()),
    path("sites/<uuid:site_id>", ClientSiteDetailView.as_view()),
    path("sites/<uuid:site_id>/runs", AuditRunCreateView.as_view()),
    path("runs/<uuid:run_id>", AuditRunDetailView.as_view()),
    path("runs/<uuid:run_id>/retry", RetryRunView.as_view()),
    path("runs/<uuid:run_id>/dashboard", AuditRunDashboardView.as_view()),
    path("dashboard/overview", DashboardOverviewView.as_view()),
    path("sites/<uuid:site_id>/runs", SiteRunsListView.as_view()),
]