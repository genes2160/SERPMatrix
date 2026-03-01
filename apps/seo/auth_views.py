# apps/seo/auth_views.py

from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework.permissions import AllowAny


class PublicTokenObtainPairView(TokenObtainPairView):
    permission_classes = [AllowAny]


class PublicTokenRefreshView(TokenRefreshView):
    permission_classes = [AllowAny]