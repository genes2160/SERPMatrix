from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth.models import User
from apps.seo.models import ClientSite, AuditRun
import uuid


class SeoApiTests(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser",
            password="strongpassword123"
        )

        # login
        response = self.client.post("/api/auth/login/", {
            "username": "testuser",
            "password": "strongpassword123"
        })

        self.access = response.data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.access}")

    # ---------------------------------
    # HEALTH
    # ---------------------------------

    def test_health_endpoint(self):
        response = self.client.get("/api/health/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("status", response.data)

    # ---------------------------------
    # SITE
    # ---------------------------------

    def test_create_site(self):
        payload = {
            "url": "https://example.com",
            "normalized_url": "https://example.com",
            "geo": "GH",
            "language": "en",
            "device": "desktop"
        }

        response = self.client.post("/api/sites", payload)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(ClientSite.objects.count(), 1)

    def test_list_sites(self):
        ClientSite.objects.create(
            url="https://a.com",
            normalized_url="https://a.com",
            user=self.user  # ← add this
        )

        response = self.client.get("/api/sites")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)

    def test_get_site(self):
        site = ClientSite.objects.create(
            url="https://b.com",
            normalized_url="https://b.com",
            user=self.user  # ← add this
        )

        response = self.client.get(f"/api/sites/{site.id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(str(response.data["id"]), str(site.id))
    # ---------------------------------
    # RUN
    # ---------------------------------

    def test_create_run(self):
        site = ClientSite.objects.create(
            url="https://c.com",
            normalized_url="https://c.com",
            user=self.user  # ← add
        )

        response = self.client.post(
            f"/api/sites/{site.id}/runs",
            {"config": {"provider": "google"}},
            format="json"
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(AuditRun.objects.count(), 1)

    def test_get_run(self):
        site = ClientSite.objects.create(
            url="https://d.com",
            normalized_url="https://d.com",
            user=self.user  # ← add
        )

        run = AuditRun.objects.create(client_site=site)

        response = self.client.get(f"/api/runs/{run.id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(str(response.data["id"]), str(run.id))

    def test_retry_run(self):
        site = ClientSite.objects.create(
            url="https://e.com",
            normalized_url="https://e.com",
            user=self.user  # ← add
        )

        run = AuditRun.objects.create(client_site=site)

        response = self.client.post(f"/api/runs/{run.id}/retry")
        self.assertEqual(response.status_code, 200)

    # ---------------------------------
    # AUTH REQUIRED
    # ---------------------------------

    def test_auth_required(self):
        self.client.credentials()  # remove token

        response = self.client.get("/api/sites")
        self.assertEqual(response.status_code, 401)