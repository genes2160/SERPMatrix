from celery import shared_task
from django.db import transaction
from django.utils import timezone
from django.db.models import Q

from apps.seo.models import OutboxEvent
from apps.seo.tasks.run import run_start

@shared_task(name="apps.seo.tasks.outbox.dispatch")
def dispatch_outbox_batch(limit: int = 20):

    now = timezone.now()

    # STEP 1: CLAIM rows quickly
    with transaction.atomic():
        events = list(
            OutboxEvent.objects
            .select_for_update(skip_locked=True)
            .filter(
                Q(status=OutboxEvent.Status.PENDING) |
                Q(status=OutboxEvent.Status.FAILED, next_retry_at__lte=now)
            )
            .order_by("created_at")[:limit]
        )

        for event in events:
            event.status = OutboxEvent.Status.PROCESSING
            event.save(update_fields=["status"])

    # transaction ends here — LOCKS RELEASED
    for event in events:
        try:
            if event.event_type == "audit_run_start":
                run_start.delay(
                    event.payload["run_id"],
                    event.payload.get("resume_from"),
                )

            event.status = OutboxEvent.Status.SENT
            event.save(update_fields=["status"])

        except Exception as e:
            event.attempts += 1
            event.last_error = str(e)

            if event.attempts >= event.max_attempts:
                event.status = OutboxEvent.Status.DLQ
            else:
                event.status = OutboxEvent.Status.FAILED
                event.next_retry_at = timezone.now() + timezone.timedelta(minutes=5)

            event.save(
                update_fields=["status", "attempts", "last_error", "next_retry_at"]
            )