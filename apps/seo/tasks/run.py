# apps/seo/tasks/run.py
from __future__ import annotations

from typing import Optional, List

from celery import shared_task, chain
from django.utils import timezone

from apps.seo.models import AuditRun, RunStep
from apps.seo.constants import RUN_STEP_ORDER



@shared_task(name="apps.seo.tasks.run.run_start")
def run_start(run_id: str, resume_from: Optional[str] = None):
    """
    Deterministic pipeline entry point.
    - marks AuditRun RUNNING
    - builds a celery chain from resume_from
    """
    run = AuditRun.objects.get(id=run_id)

    # If already successful/canceled, don't restart unintentionally
    if run.status in [AuditRun.Status.SUCCESS, AuditRun.Status.CANCELED]:
        return {"run_id": run_id, "status": run.status}

    if run.status != AuditRun.Status.RUNNING:
        run.status = AuditRun.Status.RUNNING
        run.started_at = run.started_at or timezone.now()
        run.save(update_fields=["status", "started_at"])

    # Build chain from resume point
    start_index = 0
    if resume_from and resume_from in RUN_STEP_ORDER:
        start_index = RUN_STEP_ORDER.index(resume_from)

    from apps.seo.tasks.steps import (
        fetch_client_page,
        classify_site,
        build_keyword_set,
        serp_capture_batch,
        fetch_competitors,
        analyze_and_recommend,
        finalize_run,
    )

    tasks: List = [
        fetch_client_page.s(run_id),
        classify_site.s(run_id),
        build_keyword_set.s(run_id),
        serp_capture_batch.s(run_id),
        fetch_competitors.s(run_id),
        analyze_and_recommend.s(run_id),
        finalize_run.s(run_id),
    ]

    # slice pipeline
    pipeline = tasks[start_index:]

    if not pipeline:
        return {"run_id": run_id, "status": "no-op"}

    chain(*pipeline).apply_async()
    return {"run_id": run_id, "status": "started", "resume_from": resume_from}


@shared_task(name="apps.seo.tasks.run.finalize_run")
def finalize_run(run_id: str):
    """
    (kept for routing compatibility) — actual finalize logic is in steps.finalize_run.
    """
    return {"run_id": run_id, "status": "delegated"}