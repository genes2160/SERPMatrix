# apps/seo/services/run_service.py
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any, List

from django.db import transaction
from django.utils import timezone

from apps.seo.models import AuditRun, ClientSite, RunStep
from apps.seo.constants import RUN_STEP_ORDER
from django.conf import settings
from apps.seo.models import OutboxEvent

logger = logging.getLogger(__name__)

class RunService:
    @staticmethod
    def create_run(*, site: ClientSite, config: Dict[str, Any]) -> AuditRun:
        from apps.seo.tasks.run import run_start
        logger.info("[run_service] create_run | site_id=%s | site_url=%s", site.id, site.url)

        with transaction.atomic():
            run = AuditRun.objects.create(
                client_site=site,
                status=AuditRun.Status.QUEUED,
                config=config or {},
            )
            logger.info("[run_service] AuditRun created | run_id=%s | status=%s", run.id, run.status)

            RunStep.objects.bulk_create([
                RunStep(audit_run=run, step_name=step_name, status=RunStep.Status.QUEUED)
                for step_name in RUN_STEP_ORDER
            ])
            logger.info("[run_service] RunSteps created | run_id=%s | steps=%s", run.id, RUN_STEP_ORDER)

            if settings.SEO_DISPATCH_MODE == "instant":
                logger.info("[run_service] Dispatch mode=instant | run_id=%s", run.id)

                def enqueue():
                    logger.info("[run_service] Enqueuing run_start | run_id=%s", run.id)
                    run_start.delay(str(run.id), None)

                if settings.TESTING:
                    logger.info("[run_service] TESTING mode — enqueue immediate | run_id=%s", run.id)
                    enqueue()
                else:
                    logger.info("[run_service] Registering on_commit enqueue | run_id=%s", run.id)
                    transaction.on_commit(enqueue)

            else:  # outbox mode
                logger.info("[run_service] Dispatch mode=outbox | run_id=%s", run.id)
                OutboxEvent.objects.create(
                    event_type="audit_run_start",
                    aggregate_id=run.id,
                    payload={
                        "run_id": str(run.id),
                        "resume_from": None,
                    },
                )
                logger.info("[run_service] OutboxEvent created | run_id=%s", run.id)

            logger.info("[run_service] create_run complete | run_id=%s", run.id)
            return run

        
    @staticmethod
    def retry_run(*, run: AuditRun) -> AuditRun:
        """
        Safe retry:
        - DO NOT reset steps
        - DO NOT wipe downstream work
        - Resume from earliest incomplete step
        """

        from apps.seo.constants import next_resume_step_from_db
        from apps.seo.tasks.run import run_start

        logger.info("[run_service] retry_run | run_id=%s | current_status=%s", run.id, run.status)

        run = AuditRun.objects.prefetch_related("steps").get(id=run.id)

        resume_from, terminal_error = next_resume_step_from_db(run)
        logger.info("[run_service] next_resume_step | run_id=%s | resume_from=%s | terminal_error=%s", run.id, resume_from, terminal_error)

        # Terminal state (exhausted attempts)
        if terminal_error:
            logger.warning("[run_service] Terminal error detected | run_id=%s | error=%s", run.id, terminal_error)
            run.error_summary = terminal_error
            run.save(update_fields=["error_summary"])
            return run

        # Already fully complete
        if resume_from is None:
            logger.info("[run_service] Run already complete, nothing to retry | run_id=%s", run.id)
            return run

        with transaction.atomic():

            # DO NOT touch steps.
            # DO NOT reset attempts.
            # Only enqueue resume event.

            if settings.SEO_DISPATCH_MODE == "instant":
                logger.info("[run_service] Retry dispatch mode=instant | run_id=%s | resume_from=%s", run.id, resume_from)

                def enqueue():
                    logger.info("[run_service] Enqueuing run_start retry | run_id=%s | resume_from=%s", run.id, resume_from)
                    run_start.delay(str(run.id), resume_from)

                if settings.TESTING:
                    logger.info("[run_service] TESTING mode — enqueue immediate | run_id=%s", run.id)
                    enqueue()
                else:
                    logger.info("[run_service] Registering on_commit enqueue | run_id=%s", run.id)
                    transaction.on_commit(enqueue)

            else:
                logger.info("[run_service] Retry dispatch mode=outbox | run_id=%s | resume_from=%s", run.id, resume_from)
                OutboxEvent.objects.create(
                    event_type="audit_run_start",
                    aggregate_id=run.id,
                    payload={
                        "run_id": str(run.id),
                        "resume_from": resume_from,
                    },
                )
                logger.info("[run_service] OutboxEvent created for retry | run_id=%s | resume_from=%s", run.id, resume_from)

        logger.info("[run_service] retry_run complete | run_id=%s | resume_from=%s", run.id, resume_from)
        return run

    @staticmethod
    def force_retry_run(*, run: AuditRun) -> AuditRun:
        """
        Force retry — resets failed steps that hit max attempts
        so the pipeline can resume from them again.
        Use this for manual operator retries only.
        """
        from apps.seo.constants import next_resume_step_from_db
        from apps.seo.tasks.run import run_start

        logger.info("[run_service] force_retry_run | run_id=%s", run.id)

        with transaction.atomic():
            # Reset any FAILED steps that exhausted attempts back to QUEUED
            reset_count = RunStep.objects.filter(
                audit_run=run,
                status=RunStep.Status.FAILED,
            ).update(
                status=RunStep.Status.QUEUED,
                attempts=0,
                last_error=None,
                started_at=None,
                finished_at=None,
            )

            logger.info("[run_service] force_retry reset steps | run_id=%s | reset_count=%s", run.id, reset_count)

            OutboxEvent.objects.create(
                event_type="audit_run_start",
                aggregate_id=run.id,
                payload={"run_id": str(run.id), "resume_from": None},
            )
            logger.info("[run_service] force_retry OutboxEvent created | run_id=%s", run.id)

        return AuditRun.objects.prefetch_related("steps").get(id=run.id)
run_service = RunService()