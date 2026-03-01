# apps/seo/tasks/steps.py
from __future__ import annotations

import hashlib
from typing import Dict, Any, Optional

from celery import shared_task, current_task
from django.db import transaction
from django.utils import timezone
from django.conf import settings

from apps.seo.models import (
    AuditRun,
    RunStep,
    RunStepAttempt,
    PageSnapshot,
    KeywordSetVersion,
    SerpSnapshot,
    KeywordResult,
    Recommendation,
)

# -----------------------------
# Step claiming (race-safe)
# -----------------------------

def _get_worker_hostname() -> Optional[str]:
    try:
        req = getattr(current_task, "request", None)
        return getattr(req, "hostname", None)
    except Exception:
        return None


def _claim_step(run_id: str, step_name: str) -> tuple[Optional[RunStep], Optional[RunStepAttempt], Dict[str, Any]]:
    """
    Atomic step claim:
    - lock RunStep row
    - if SUCCESS -> skip
    - if RUNNING -> skip (another worker)
    - else set RUNNING, increment attempts, create RunStepAttempt
    """
    run = AuditRun.objects.only("id", "status").get(id=run_id)

    if run.status in [AuditRun.Status.SUCCESS, AuditRun.Status.CANCELED]:
        return None, None, {"run_id": run_id, "step": step_name, "status": "skipped_run_done"}

    with transaction.atomic():
        step = (
            RunStep.objects
            .select_for_update()
            .get(audit_run_id=run_id, step_name=step_name)
        )

        if step.status == RunStep.Status.SUCCESS:
            return None, None, {"run_id": run_id, "step": step_name, "status": "skipped_already_success"}

        if step.status == RunStep.Status.RUNNING:
            return None, None, {"run_id": run_id, "step": step_name, "status": "skipped_already_running"}

        step.attempts += 1
        step.status = RunStep.Status.RUNNING
        step.started_at = timezone.now()
        step.last_error = None
        step.save(update_fields=["attempts", "status", "started_at", "last_error"])

        attempt = RunStepAttempt.objects.create(
            run_step=step,
            attempt_no=step.attempts,
            status=RunStepAttempt.Status.RUNNING,
            worker_hostname=_get_worker_hostname(),
            meta={},
        )

        return step, attempt, {"run_id": run_id, "step": step_name, "status": "claimed"}


def _finish_success(step: RunStep, attempt: RunStepAttempt, meta: Dict[str, Any] | None = None):
    now = timezone.now()
    step.status = RunStep.Status.SUCCESS
    step.finished_at = now
    step.meta = meta or step.meta
    step.save(update_fields=["status", "finished_at", "meta"])

    attempt.status = RunStepAttempt.Status.SUCCESS
    attempt.finished_at = now
    attempt.meta = meta or attempt.meta
    attempt.save(update_fields=["status", "finished_at", "meta"])


def _finish_failed(step: RunStep, attempt: RunStepAttempt, err: str):
    now = timezone.now()
    step.status = RunStep.Status.FAILED
    step.finished_at = now
    step.last_error = err
    step.save(update_fields=["status", "finished_at", "last_error"])

    attempt.status = RunStepAttempt.Status.FAILED
    attempt.finished_at = now
    attempt.error = err
    attempt.save(update_fields=["status", "finished_at", "error"])


# -----------------------------
# Tasks
# -----------------------------

@shared_task(name="apps.seo.tasks.steps.fetch_client_page")
def fetch_client_page(run_id: str):
    step, attempt, info = _claim_step(run_id, RunStep.StepName.FETCH_CLIENT)
    if step is None:
        return {"run_id": run_id, "step": "FETCH_CLIENT", **info}

    try:
        run = AuditRun.objects.select_related("client_site").get(id=run_id)
        url = run.client_site.url

        # POC: store a snapshot record (no real HTTP fetch yet)
        fake_html = f"<html><head><title>POC</title></head><body>{url}</body></html>"
        html_hash = hashlib.sha256(fake_html.encode("utf-8")).hexdigest()

        PageSnapshot.objects.create(
            audit_run=run,
            url=url,
            role=PageSnapshot.Role.CLIENT,
            http_status=200,
            html_hash=html_hash,
            content_type="text/html",
            extracted={"title": "POC", "note": "fetch stub"},
            raw_html_ref=None,
        )

        _finish_success(step, attempt, meta={"url": url, "html_hash": html_hash})
        return {"run_id": run_id, "step": "FETCH_CLIENT", "status": "success"}

    except Exception as e:
        _finish_failed(step, attempt, str(e))
        raise


@shared_task(name="apps.seo.tasks.steps.classify_site")
def classify_site(run_id: str):
    step, attempt, info = _claim_step(run_id, RunStep.StepName.CLASSIFY)
    if step is None:
        return {"run_id": run_id, "step": "CLASSIFY", **info}

    try:
        run = AuditRun.objects.select_related("client_site").get(id=run_id)

        # POC classification stub
        niche = run.client_site.niche_label or "unknown"
        run.client_site.niche_label = niche
        run.client_site.save(update_fields=["niche_label"])

        _finish_success(step, attempt, meta={"niche_label": niche})
        return {"run_id": run_id, "step": "CLASSIFY", "status": "success"}

    except Exception as e:
        _finish_failed(step, attempt, str(e))
        raise


@shared_task(name="apps.seo.tasks.steps.build_keyword_set")
def build_keyword_set(run_id: str):
    step, attempt, info = _claim_step(run_id, RunStep.StepName.KEYWORDS)
    if step is None:
        return {"run_id": run_id, "step": "KEYWORDS", **info}

    try:
        run = AuditRun.objects.get(id=run_id)

        # POC keyword extraction stub
        kws = [
            {"kw": "dentist accra", "w": 1.0},
            {"kw": "teeth whitening ghana", "w": 0.8},
            {"kw": "dental clinic near me", "w": 0.7},
        ]

        KeywordSetVersion.objects.create(
            audit_run=run,
            source=KeywordSetVersion.Source.EXTRACTED,
            keywords=kws,
        )

        _finish_success(step, attempt, meta={"count": len(kws)})
        return {"run_id": run_id, "step": "KEYWORDS", "status": "success"}

    except Exception as e:
        _finish_failed(step, attempt, str(e))
        raise


@shared_task(name="apps.seo.tasks.steps.serp_capture_batch")
def serp_capture_batch(run_id: str):
    step, attempt, info = _claim_step(run_id, RunStep.StepName.SERP)
    if step is None:
        return {"run_id": run_id, "step": "SERP", **info}

    try:
        run = AuditRun.objects.get(id=run_id)

        latest_kw_set = run.keyword_sets.order_by("-created_at").first()
        keywords = (latest_kw_set.keywords if latest_kw_set else [])[:5]

        provider = run.config.get("provider", "google")
        competitor_stub = run.config.get("competitor_stub_url", "https://competitor.com")

        # POC serp results stub
        for item in keywords:
            kw = item["kw"]

            SerpSnapshot.objects.create(
                audit_run=run,
                keyword=kw,
                provider=provider,
                provider_meta={"note": "serp stub"},
                results={"top": [{"pos": 1, "url": competitor_stub}]},
            )

            KeywordResult.objects.create(
                audit_run=run,
                keyword=kw,
                client_position=None,  # not found in stub
                visibility_score=0.1,
                difficulty_score=0.7,
                competitor_urls=[competitor_stub],
            )

        _finish_success(step, attempt, meta={"keywords_processed": len(keywords)})
        return {"run_id": run_id, "step": "SERP", "status": "success"}

    except Exception as e:
        _finish_failed(step, attempt, str(e))
        raise


@shared_task(name="apps.seo.tasks.steps.fetch_competitors")
def fetch_competitors(run_id: str):
    step, attempt, info = _claim_step(run_id, RunStep.StepName.COMPETITORS)
    if step is None:
        return {"run_id": run_id, "step": "COMPETITORS", **info}

    try:
        # POC: competitors are already in serp stubs; nothing to fetch yet
        _finish_success(step, attempt, meta={"note": "competitors stub"})
        return {"run_id": run_id, "step": "COMPETITORS", "status": "success"}

    except Exception as e:
        _finish_failed(step, attempt, str(e))
        raise


@shared_task(name="apps.seo.tasks.steps.analyze_and_recommend")
def analyze_and_recommend(run_id: str):
    step, attempt, info = _claim_step(run_id, RunStep.StepName.ANALYZE)
    if step is None:
        return {"run_id": run_id, "step": "ANALYZE", **info}

    try:
        run = AuditRun.objects.get(id=run_id)

        # POC recommendation
        Recommendation.objects.create(
            audit_run=run,
            keyword=None,
            action_type="content_expand",
            priority=Recommendation.Priority.MED,
            expected_impact=Recommendation.Priority.MED,
            reason_text="POC: Add content targeting extracted keywords and align titles/H1s with SERP intent.",
            evidence_refs=[],
        )

        _finish_success(step, attempt, meta={"recommendations": 1})
        return {"run_id": run_id, "step": "ANALYZE", "status": "success"}

    except Exception as e:
        _finish_failed(step, attempt, str(e))
        raise


@shared_task(name="apps.seo.tasks.steps.finalize_run")
def finalize_run(run_id: str):
    step, attempt, info = _claim_step(run_id, RunStep.StepName.FINALIZE)
    if step is None:
        return {"run_id": run_id, "step": "FINALIZE", **info}

    try:
        run = AuditRun.objects.get(id=run_id)

        # POC summary
        summary = {
            "keywords": run.keyword_results.count(),
            "recommendations": run.recommendations.count(),
            "snapshots": run.page_snapshots.count(),
        }

        run.summary = summary
        run.status = AuditRun.Status.SUCCESS
        run.finished_at = timezone.now()
        run.save(update_fields=["summary", "status", "finished_at"])

        _finish_success(step, attempt, meta=summary)
        return {"run_id": run_id, "step": "FINALIZE", "status": "success"}

    except Exception as e:
        # keep run status consistent with step failure
        now = timezone.now()
        AuditRun.objects.filter(id=run_id).update(
            status=AuditRun.Status.FAILED,
            error_summary=str(e),
            finished_at=now,
        )
        _finish_failed(step, attempt, str(e))
        raise