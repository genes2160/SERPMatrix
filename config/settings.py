import os
from pathlib import Path
from datetime import timedelta
import urllib.parse as up

BASE_DIR = Path(__file__).resolve().parent.parent

# -------------------------------------------------
# Core
# -------------------------------------------------

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "unsafe-dev-key")
DEBUG = os.getenv("DJANGO_DEBUG", "1") in ["1", "true", "True"]

ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "*").split(",")

# -------------------------------------------------
# Applications
# -------------------------------------------------

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "drf_spectacular",
    "apps.seo.apps.SeoConfig",
]
TEST_RUNNER = "django.test.runner.DiscoverRunner"
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
]
ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# -------------------------------------------------
# Database
# -------------------------------------------------

DATABASE_URL = os.getenv("DATABASE_URL", "")

if DATABASE_URL.startswith("postgres://") or DATABASE_URL.startswith("postgresql://"):
    u = up.urlparse(DATABASE_URL.replace("postgres://", "postgresql://"))
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": u.path.lstrip("/"),
            "USER": u.username,
            "PASSWORD": u.password,
            "HOST": u.hostname,
            "PORT": u.port or 5432,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# -------------------------------------------------
# REST Framework
# -------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}
SPECTACULAR_SETTINGS = {
    "TITLE": "SEO Audit Engine API",
    "DESCRIPTION": "Scalable SEO intelligence and ranking audit platform",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SECURITY": [{"BearerAuth": []}],
    "SECURITY_SCHEMES": {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        }
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}
# -------------------------------------------------
# Static
# -------------------------------------------------

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# -------------------------------------------------
# Celery
# -------------------------------------------------

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/1")

CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1

CELERY_TASK_TIME_LIMIT = 180
CELERY_TASK_SOFT_TIME_LIMIT = 150

CELERY_TASK_ROUTES = {
    "apps.seo.tasks.run.run_start": {"queue": "seo_light"},
    "apps.seo.tasks.run.finalize_run": {"queue": "seo_light"},

    "apps.seo.tasks.steps.fetch_client_page": {"queue": "seo_light"},
    "apps.seo.tasks.steps.classify_site": {"queue": "seo_light"},
    "apps.seo.tasks.steps.build_keyword_set": {"queue": "seo_light"},

    "apps.seo.tasks.steps.serp_capture_batch": {"queue": "seo_serp"},
    "apps.seo.tasks.steps.fetch_competitors": {"queue": "seo_heavy"},
    "apps.seo.tasks.steps.analyze_and_recommend": {"queue": "seo_heavy"},
    "apps.seo.tasks.outbox.dispatch": {"queue": "control"},
}

# -------------------------------------------------
# Default Primary Key
# -------------------------------------------------

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

SEO_DISPATCH_MODE = "instant"  # or "outbox"

CELERY_BEAT_SCHEDULE = {
    "outbox-dispatcher": {
        "task": "apps.seo.tasks.outbox.dispatch",
        "schedule": 10.0,  # every 10 seconds
    },
}