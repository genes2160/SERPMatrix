from __future__ import annotations

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from apps.seo.models import AuditRun, RunStep
from apps.seo.tasks.steps import _claim_step, _finish_success, _finish_failed  # reuse your existing infra
from apps.seo.ai.prompts import build_seo_audit_messages  # NEW
from apps.seo.ai.providers import get_ai_client, TransientAIError  # NEW


def _build_ai_payload(run: AuditRun) -> dict:
    """
    # NEW:
    Build a compact, structured payload for the LLM.
    IMPORTANT: no raw HTML; only extracted + aggregated signals.
    """
    site = run.client_site

    latest_snapshot = run.page_snapshots.order_by("-created_at").first()
    latest_kw_set = run.keyword_sets.order_by("-created_at").first()

    keyword_results = list(
        run.keyword_results.order_by("-visibility_score").values(
            "keyword",
            "client_position",
            "visibility_score",
            "difficulty_score",
            "competitor_urls",
        )[:50]
    )

    payload = {
        "run": {
            "id": str(run.id),
            "created_at": run.created_at.isoformat() if getattr(run, "created_at", None) else None,
            "config": run.config if isinstance(run.config, dict) else {},
        },
        "client_site": {
            "id": str(site.id),
            "url": site.url,
            "normalized_url": site.normalized_url,
            "geo": site.geo,
            "language": site.language,
            "device": site.device,
            "niche_label": getattr(site, "niche_label", None),
        },
        "page_snapshot": {
            "url": getattr(latest_snapshot, "url", None),
            "http_status": getattr(latest_snapshot, "http_status", None),
            "content_type": getattr(latest_snapshot, "content_type", None),
            "extracted": getattr(latest_snapshot, "extracted", None),
        } if latest_snapshot else None,
        "keyword_set": {
            "count": len(latest_kw_set.keywords) if latest_kw_set and latest_kw_set.keywords else 0,
            "keywords": (latest_kw_set.keywords or [])[:50] if latest_kw_set else [],
        },
        "keyword_results": keyword_results,
        "counts": {
            "snapshots": run.page_snapshots.count(),
            "keyword_sets": run.keyword_sets.count(),
            "serp_snapshots": run.serp_snapshots.count(),
            "keyword_results": run.keyword_results.count(),
            "recommendations": run.recommendations.count(),
        },
    }
    return payload


@shared_task(
    name="apps.seo.tasks.steps.ai_analyze",
    bind=True,
    queue="seo_heavy",
    autoretry_for=(TransientAIError,),
    retry_backoff=True,      # exponential backoff
    retry_jitter=True,
    retry_kwargs={"max_retries": 5},
)
def ai_analyze(self, _, run_id: str):
    """
    # NEW:
    LLM interpretation layer:
    - reads structured signals from DB
    - generates summary + recommendations
    - writes results back to AuditRun (+ optional Recommendation rows)
    """
    step, attempt, info = _claim_step(run_id, RunStep.StepName.AI_ANALYZE)
    if step is None:
        return {"run_id": run_id, "step": "AI_ANALYZE", **info}

    try:
        run = AuditRun.objects.select_related("client_site").get(id=run_id)

        payload = _build_ai_payload(run)
        messages = build_seo_audit_messages(payload)

        client = get_ai_client()
        result = client.generate(messages=messages)

        # Expected shape:
        # {
        #   "summary": "...",
        #   "recommendations": [{"title": "...", "priority": "HIGH", "reason": "...", "actions": [...]}, ...],
        #   "meta": {...}
        # }

        summary = (result or {}).get("summary") or ""
        meta = (result or {}).get("meta") or {}
        recs = (result or {}).get("recommendations") or []

        with transaction.atomic():
            run.ai_summary = summary
            run.ai_meta = meta
            run.save(update_fields=["ai_summary", "ai_meta"])

            # Optional: persist AI recs as Recommendation rows (if you want them in DB)
            # Keep it minimal; you can enrich later.
            from apps.seo.models import Recommendation  # local import to avoid cycles

            for r in recs[:50]:
                Recommendation.objects.create(
                    audit_run=run,
                    keyword=None,
                    action_type=(r.get("action_type") or "ai_recommendation"),
                    priority=_map_priority(r.get("priority")),
                    expected_impact=_map_priority(r.get("expected_impact") or r.get("priority")),
                    reason_text=(r.get("reason") or r.get("title") or "")[:2000],
                    evidence_refs=r.get("evidence_refs") or [],
                )

        _finish_success(step, attempt, meta={"ai": {"recommendations": len(recs)}})
        return {"run_id": run_id, "step": "AI_ANALYZE", "status": "success", "recs": len(recs)}

    except Exception as e:
        _finish_failed(step, attempt, str(e))

        if step.attempts < 3:
            raise self.retry(countdown=30)
        else:
            raise


def _map_priority(val: str | None):
    # NEW: tiny mapping; match your Recommendation.Priority
    from apps.seo.models import Recommendation
    v = (val or "").upper()
    if v in ("HIGH", "H"):
        return Recommendation.Priority.HIGH
    if v in ("LOW", "L"):
        return Recommendation.Priority.LOW
    return Recommendation.Priority.MED