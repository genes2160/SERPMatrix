# apps/seo/tasks/run.py
from __future__ import annotations

from typing import Optional, List

from celery import shared_task, chain
from django.utils import timezone

from apps.seo.models import AuditRun, RunStep
from apps.seo.constants import RUN_STEP_ORDER
import logging

logger = logging.getLogger(__name__)

@shared_task(name="apps.seo.tasks.run.run_start")
def run_start(run_id: str, resume_from: Optional[str] = None):
    run = AuditRun.objects.prefetch_related("steps").get(id=run_id)

    if run.status in [AuditRun.Status.SUCCESS, AuditRun.Status.CANCELED]:
        return {"run_id": run_id, "status": run.status}

    if run.status != AuditRun.Status.RUNNING:
        run.status = AuditRun.Status.RUNNING
        run.started_at = run.started_at or timezone.now()
        run.save(update_fields=["status", "started_at"])

    # ── fast-forward past SUCCESS/SKIPPED steps ──
    steps = {s.step_name: s for s in run.steps.all()}

    start_index = 0
    if resume_from and resume_from in RUN_STEP_ORDER:
        start_index = RUN_STEP_ORDER.index(resume_from)

    # skip already completed steps
    while start_index < len(RUN_STEP_ORDER):
        step_name = RUN_STEP_ORDER[start_index]
        s = steps.get(step_name)
        if s and s.status in [RunStep.Status.SUCCESS, RunStep.Status.SKIPPED]:
            start_index += 1
        else:
            break

    # ── GUARD: if the next step is already RUNNING, do not dispatch a new chain ──
    if start_index < len(RUN_STEP_ORDER):
        next_step_name = RUN_STEP_ORDER[start_index]
        next_step = steps.get(next_step_name)
        if next_step and next_step.status == RunStep.Status.RUNNING:
            logger.info(
                "⏭️ [run_start] Step already RUNNING — skipping dispatch | run_id=%s | step=%s",
                run_id, next_step_name,
            )
            return {"run_id": run_id, "status": "no-op", "reason": f"{next_step_name} already running"}

    if start_index >= len(RUN_STEP_ORDER):
        return {"run_id": run_id, "status": "no-op", "reason": "all steps complete"}

    from apps.seo.tasks.steps import (
        fetch_client_page, classify_site, build_keyword_set,
        serp_capture_batch, fetch_competitors, analyze_and_recommend, finalize_run,
    )

    tasks = [
        fetch_client_page.si(run_id),
        classify_site.si(run_id),
        build_keyword_set.si(run_id),
        serp_capture_batch.si(run_id),
        fetch_competitors.si(run_id),
        analyze_and_recommend.si(run_id),
        finalize_run.si(run_id),
    ]

    pipeline = tasks[start_index:]

    logger.info(
        "🚀 [run_start] Dispatching | run_id=%s | from=%s | steps=%s",
        run_id, RUN_STEP_ORDER[start_index],
        RUN_STEP_ORDER[start_index:],
    )

    chain(*pipeline).apply_async()
    return {"run_id": run_id, "status": "started", "resume_from": resume_from}

