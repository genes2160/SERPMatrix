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
        from apps.seo.tasks.run import run_start
        """
        Step-level retry:
        - find first FAILED step; if none, find first non-success step
        - reset that step and downstream to QUEUED
        - enqueue run_start(run_id, resume_from=that_step)
        """
        with transaction.atomic():
            steps = list(run.steps.all().order_by("created_at"))

            # Determine resume point
            resume_from: Optional[str] = None

            failed = [s for s in steps if s.status == RunStep.Status.FAILED]
            if failed:
                # first failed in pipeline order
                for name in RUN_STEP_ORDER:
                    match = next((s for s in failed if s.step_name == name), None)
                    if match:
                        resume_from = match.step_name
                        break
            else:
                # first incomplete (not success)
                for name in RUN_STEP_ORDER:
                    match = next((s for s in steps if s.step_name == name), None)
                    if match and match.status != RunStep.Status.SUCCESS:
                        resume_from = match.step_name
                        break

            # If everything succeeded, allow retry from start (or you can block)
            if resume_from is None:
                resume_from = RUN_STEP_ORDER[0]

            # Reset resume_from + downstream
            start_index = RUN_STEP_ORDER.index(resume_from)
            reset_names = set(RUN_STEP_ORDER[start_index:])

            run.steps.filter(step_name__in=reset_names).update(
                status=RunStep.Status.QUEUED,
                last_error=None,
            )

            # Reset run status
            run.status = AuditRun.Status.QUEUED
            run.error_summary = None
            run.started_at = None
            run.finished_at = None
            run.save(update_fields=["status", "error_summary", "started_at", "finished_at"])

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


run_service = RunService()