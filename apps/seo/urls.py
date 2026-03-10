from django.urls import path, re_path
from django.http import JsonResponse
from apps.seo.views import (
    AuditRunCreateView,
    AuditRunDashboardView,
    AuditRunDetailView,
    ClientSiteDetailView,
    ClientSiteListCreateView,
    DashboardOverviewView,
    HealthCheckView,
    NotificationListView,
    NotificationMarkReadView,
    RetryRunView,
    SiteRunsListView,
    UserNotificationsView,
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
    path("notifications", UserNotificationsView.as_view()),
    path("runs/<uuid:run_id>/notifications", NotificationListView.as_view()),
    path("notifications/<uuid:notification_id>/read", NotificationMarkReadView.as_view()),
    re_path(r"^.*$", lambda request, *args, **kwargs: JsonResponse(
        {"detail": "The requested endpoint does not exist."}, status=404
    )),
]