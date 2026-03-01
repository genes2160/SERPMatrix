from unittest.mock import patch
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.seo.models import ClientSite, OutboxEvent
from apps.seo.services.run_service import run_service
from apps.seo.tasks.outbox_dispatcher import dispatch_outbox_batch


class OutboxTests(TestCase):

    def create_site(self):
        return ClientSite.objects.create(
            url="https://example.com",
            normalized_url="https://example.com",
            geo="gh",
            language="en",
            device="desktop",
        )

    def create_outbox_event(self, run_id):
        return OutboxEvent.objects.create(
            event_type="audit_run_start",
            aggregate_id=run_id,
            payload={
                "run_id": str(run_id),
                "resume_from": None,
            },
            status=OutboxEvent.Status.PENDING,
        )

    # --------------------------------------------------

    @override_settings(SEO_DISPATCH_MODE="instant")
    @patch("apps.seo.tasks.run.run_start.delay")
    def test_create_run_instant_dispatch(self, mock_delay):
        site = self.create_site()
        run_service.create_run(site=site, config={})
        mock_delay.assert_called_once()

    # --------------------------------------------------

    @override_settings(SEO_DISPATCH_MODE="outbox")
    def test_create_run_creates_outbox_event(self):
        site = self.create_site()
        run = run_service.create_run(site=site, config={})

        event = OutboxEvent.objects.filter(
            aggregate_id=run.id,
            status=OutboxEvent.Status.PENDING,
        ).first()

        self.assertIsNotNone(event)

    # --------------------------------------------------
    @override_settings(SEO_DISPATCH_MODE="outbox")
    @patch("apps.seo.tasks.run.run_start.delay")
    def test_dispatcher_sends_event(self, mock_delay):
        site = self.create_site()
        run = run_service.create_run(site=site, config={})

        event = OutboxEvent.objects.get(aggregate_id=run.id)

        dispatch_outbox_batch(limit=10)

        event.refresh_from_db()
        self.assertEqual(event.status, OutboxEvent.Status.SENT)
        mock_delay.assert_called_once()

    # --------------------------------------------------
    @override_settings(SEO_DISPATCH_MODE="outbox")
    @patch("apps.seo.tasks.run.run_start.delay", side_effect=Exception("fail"))
    def test_retry_increments_attempts(self, mock_delay):
        site = self.create_site()
        run = run_service.create_run(site=site, config={})
        event = self.create_outbox_event(run.id)

        dispatch_outbox_batch(limit=10)

        event.refresh_from_db()
        self.assertEqual(event.attempts, 1)
        self.assertIn(event.status, [
            OutboxEvent.Status.FAILED,
            OutboxEvent.Status.DLQ
        ])

    # --------------------------------------------------
    @override_settings(SEO_DISPATCH_MODE="outbox")
    @patch("apps.seo.tasks.run.run_start.delay", side_effect=Exception("fail"))
    def test_backoff_sets_retry_time(self, mock_delay):
        site = self.create_site()
        run = run_service.create_run(site=site, config={})
        event = self.create_outbox_event(run.id)

        dispatch_outbox_batch(limit=10)

        event.refresh_from_db()
        if event.status == OutboxEvent.Status.FAILED:
            self.assertIsNotNone(event.next_retry_at)
            self.assertTrue(event.next_retry_at > timezone.now())