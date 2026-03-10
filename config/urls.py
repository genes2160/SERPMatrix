from django.contrib import admin
from django.urls import path, include, re_path
from django.http import JsonResponse
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
)
from apps.seo.auth_views import (
    PublicTokenObtainPairView,
    PublicTokenRefreshView,
)



urlpatterns = [
    path("admin/", admin.site.urls),

    # JWT
    path("api/auth/login/", PublicTokenObtainPairView.as_view(), name="jwt-login"),
    path("api/auth/refresh/", PublicTokenRefreshView.as_view(), name="jwt-refresh"),

    # OpenAPI schema
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),

    # Swagger UI
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),

    # App endpoints
    path("api/", include("apps.seo.urls")),

    # catch-all — must be last
    re_path(r"^.*$", lambda request, *args, **kwargs: JsonResponse(
        {"detail": "The requested endpoint does not exist."}, status=404
    )),
]