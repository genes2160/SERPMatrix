# apps/seo/services/run_service.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Dict, Any, List

from django.db import transaction
from django.utils import timezone

from apps.seo.models import AuditRun, ClientSite, RunStep
from apps.seo.constants import RUN_STEP_ORDER
from django.conf import settings
from apps.seo.models import OutboxEvent

class RunService:
    @staticmethod
    def create_run(*, site: ClientSite, config: Dict[str, Any]) -> AuditRun:
        from apps.seo.tasks.run import run_start
        with transaction.atomic():
            run = AuditRun.objects.create(
                client_site=site,
                status=AuditRun.Status.QUEUED,
                config=config or {},
            )

            RunStep.objects.bulk_create([
                RunStep(audit_run=run, step_name=step_name, status=RunStep.Status.QUEUED)
                for step_name in RUN_STEP_ORDER
            ])

            if settings.SEO_DISPATCH_MODE == "instant":

                def enqueue():
                    run_start.delay(str(run.id), None)

                if settings.TESTING:
                    enqueue()
                else:
                    transaction.on_commit(enqueue)

            else:  # outbox mode
                OutboxEvent.objects.create(
                    event_type="audit_run_start",
                    aggregate_id=run.id,
                    payload={
                        "run_id": str(run.id),
                        "resume_from": None,
                    },
                )
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

        run = AuditRun.objects.prefetch_related("steps").get(id=run.id)

        resume_from, terminal_error = next_resume_step_from_db(run)

        # Terminal state (exhausted attempts)
        if terminal_error:
            run.error_summary = terminal_error
            run.save(update_fields=["error_summary"])
            return run

        # Already fully complete
        if resume_from is None:
            return run

        with transaction.atomic():

            # DO NOT touch steps.
            # DO NOT reset attempts.
            # Only enqueue resume event.

            if settings.SEO_DISPATCH_MODE == "instant":

                def enqueue():
                    run_start.delay(str(run.id), resume_from)

                if settings.TESTING:
                    enqueue()
                else:
                    transaction.on_commit(enqueue)

            else:
                OutboxEvent.objects.create(
                    event_type="audit_run_start",
                    aggregate_id=run.id,
                    payload={
                        "run_id": str(run.id),
                        "resume_from": resume_from,
                    },
                )

        return run

run_service = RunService()