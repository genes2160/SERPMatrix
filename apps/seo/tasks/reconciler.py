import logging
from celery import shared_task
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.seo.models import AuditRun, RunStep, OutboxEvent
from django.db.models import Q, Exists, OuterRef
from apps.seo.models import RunStep
from apps.seo.constants import STEP_MAX_ATTEMPTS
from datetime import timedelta  # ← ADD THIS IMPORT

logger = logging.getLogger(__name__)

PIPELINE_ORDER = [
    RunStep.StepName.FETCH_CLIENT,
    RunStep.StepName.CLASSIFY,
    RunStep.StepName.KEYWORDS,
    RunStep.StepName.SERP,
    RunStep.StepName.COMPETITORS,
    RunStep.StepName.ANALYZE,
    RunStep.StepName.FINALIZE,
]

MAX_STEP_ATTEMPTS = 5


def _next_resume_step(run: AuditRun):
    """
    Returns (resume_from_step_name_str or None, terminal_error_str or None)

    - If everything done => (None, None)
    - If a step failed and attempts >= MAX_STEP_ATTEMPTS => (None, "terminal")
    - Else => (step_name, None) where step_name is the earliest incomplete step
    """
    steps = {s.step_name: s for s in run.steps.all()}

    for step_name in PIPELINE_ORDER:
        s = steps.get(step_name)

        # Missing step row: resume from this step (run_start can create/claim it)
        if s is None:
            return (step_name, None)

        # Completed
        if s.status in [RunStep.Status.SUCCESS, RunStep.Status.SKIPPED]:
            continue

        # Running or queued => resume from here (idempotent claim in steps will no-op if already running)
        if s.status in [RunStep.Status.QUEUED, RunStep.Status.RUNNING]:
            return (step_name, None)

        # Failed => check attempts
        if s.status == RunStep.Status.FAILED:
            if (s.attempts or 0) >= MAX_STEP_ATTEMPTS:
                logger.info("🧾 Run reconciler exceeded max attempts=%s", s.attempts)
                return (None, f"Step {step_name} exceeded max attempts ({s.attempts})")
            return (step_name, None)

    return (None, None)


@shared_task(
    name="apps.seo.tasks.reconciler.reconcile_runs",
    queue="control",
)
def reconcile_runs(limit: int = 25):
    """
    Background supervisor:
    - finds stuck/partial runs (queued/running)
    - enqueues outbox event audit_run_start with resume_from
    - skips if an outbox event for same run is already pending/processing/failed
    """
    logger.info("🧭 Run reconciler started | limit=%s", limit)

    now = timezone.now()
    stale_cutoff = now - timedelta(minutes=2)       # ← ADD
    reconcile_cutoff = now - timedelta(minutes=10)  # ← ADD

    # Subquery: FINALIZE SUCCESS
    finalize_success = RunStep.objects.filter(
        audit_run_id=OuterRef("pk"),
        step_name=RunStep.StepName.FINALIZE,
        status=RunStep.Status.SUCCESS,
    )

    # Subquery: terminal failed step
    terminal_failed = RunStep.objects.filter(
        audit_run_id=OuterRef("pk"),
        status=RunStep.Status.FAILED,
        attempts__gte=STEP_MAX_ATTEMPTS,
    )

    with transaction.atomic():
        runs = list(
            AuditRun.objects
            .select_for_update(skip_locked=True)
            .annotate(
                has_finalize_success=Exists(finalize_success),
                has_terminal_failed=Exists(terminal_failed),
            )
            .filter(
                Q(last_reconciled_at__isnull=True) |          # ← Q objects first
                Q(last_reconciled_at__lt=reconcile_cutoff),
                has_finalize_success=False,
                has_terminal_failed=False,
                started_at__isnull=False,
                started_at__lt=stale_cutoff,
            )
            .order_by("created_at")[:limit]
        )

    logger.info("🧾 Run reconciler claimed runs | count=%s", len(runs))

    if not runs:
        return {"checked": 0, "enqueued": 0, "skipped": 0, "terminal": 0, "errors": 0}

    enqueued, skipped, terminal, errors = 0, 0, 0, 0

    for run in runs:
        try:
            logger.info("🔎 Reconciling run | run_id=%s | status=%s", run.id, run.status)

            inflight = OutboxEvent.objects.filter(
                event_type="audit_run_start",
                aggregate_id=run.id,
                status__in=[
                    OutboxEvent.Status.PENDING,
                    OutboxEvent.Status.PROCESSING,
                    # ← REMOVED OutboxEvent.Status.FAILED
                ],
            ).exists()

            if inflight:
                logger.info("⏭️ Skip run (outbox inflight) | run_id=%s", run.id)
                skipped += 1
                continue

            run = AuditRun.objects.prefetch_related("steps").get(id=run.id)
            resume_from, terminal_error = _next_resume_step(run)

            if terminal_error:
                logger.error("⛔ Run terminal failure | run_id=%s | reason=%s", run.id, terminal_error)
                terminal += 1
                continue

            if resume_from is None:
                logger.info("✅ Run appears complete (no resume needed) | run_id=%s", run.id)
                skipped += 1
                continue

            payload = {"run_id": str(run.id), "resume_from": resume_from}

            OutboxEvent.objects.create(
                event_type="audit_run_start",
                aggregate_id=run.id,
                payload=payload,
                status=OutboxEvent.Status.PENDING,
            )

            AuditRun.objects.filter(id=run.id).update(last_reconciled_at=now)  # ← ADD

            enqueued += 1
            logger.info("📨 Enqueued audit_run_start via outbox | run_id=%s | resume_from=%s", run.id, resume_from)

        except Exception as e:
            logger.exception("❌ Reconciler failed for run | run_id=%s | error=%s", run.id, str(e))
            errors += 1

    logger.info("🏁 Run reconciler finished")

    result = {"checked": len(runs), "enqueued": enqueued, "skipped": skipped, "terminal": terminal, "errors": errors}
    logger.info("🏁 Run reconciler finished | %s", result)
    return result

# ← ADD THIS ENTIRE NEW TASK
@shared_task(
    name="apps.seo.tasks.reconciler.cleanup_outbox",
    queue="control",  # ← ADD
)
def cleanup_outbox():
    cutoff = timezone.now() - timedelta(hours=24)
    deleted, _ = OutboxEvent.objects.filter(
        status__in=[
            OutboxEvent.Status.SENT,
            OutboxEvent.Status.FAILED,
            OutboxEvent.Status.DLQ,
        ],
        updated_at__lt=cutoff,
    ).delete()
    logger.info("🧹 Outbox cleanup | deleted=%s", deleted)
    return {"deleted": deleted}

