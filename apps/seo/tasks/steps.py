# apps/seo/tasks/steps.py
from __future__ import annotations
import logging
import hashlib
from typing import List, Dict, Any, Optional
import json
from apps.seo.providers.serp_base import extract_domain, fetch_page
from celery import shared_task, current_task
from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist

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
from bs4 import BeautifulSoup
from apps.seo.constants import previous_steps  # NEW



logger = logging.getLogger(__name__)
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
    - enforce pipeline order: all previous steps must be SUCCESS/SKIPPED
    - if SUCCESS -> skip
    - if RUNNING -> skip (another worker)
    - else set RUNNING, increment attempts, create RunStepAttempt
    """
    run = AuditRun.objects.only("id", "status").get(id=run_id)

    if run.status in [AuditRun.Status.SUCCESS, AuditRun.Status.CANCELED]:
        return None, None, {"run_id": run_id, "step": step_name, "status": "skipped_run_done"}

    with transaction.atomic():
        # NEW: lock this step row
        step = (
            RunStep.objects
            .select_for_update()
            .get(audit_run_id=run_id, step_name=step_name)
        )

        # NEW: enforce predecessor completion
        prev_names = previous_steps(step_name)
        if prev_names:
            prev_steps = list(
                RunStep.objects
                .select_for_update()  # NEW: lock previous too to avoid races
                .filter(audit_run_id=run_id, step_name__in=prev_names)
                .only("step_name", "status")
            )

            incomplete = [
                s.step_name for s in prev_steps
                if s.status not in [RunStep.Status.SUCCESS, RunStep.Status.SKIPPED]
            ]

            if incomplete:
                # do not mutate current step; just refuse claim
                return None, None, {
                    "run_id": run_id,
                    "step": step_name,
                    "status": "blocked_by_previous",
                    "blocked_by": incomplete,
                }

        if step.status == RunStep.Status.SUCCESS:
            return None, None, {"run_id": run_id, "step": step_name, "status": "skipped_already_success"}

        if step.status == RunStep.Status.RUNNING:
            return None, None, {"run_id": run_id, "step": step_name, "status": "skipped_already_running"}

        # aggregate on related attempts table
        next_no = (step.attempt_records.aggregate(m=Max("attempt_no"))["m"] or 0) + 1

        step.attempts = next_no
        step.status = RunStep.Status.RUNNING
        step.started_at = timezone.now()
        step.last_error = None
        step.save(update_fields=["attempts", "status", "started_at", "last_error"])

        attempt, _ = RunStepAttempt.objects.get_or_create(
            run_step=step,
            attempt_no=next_no,
            defaults={
                "status": RunStepAttempt.Status.RUNNING,
                "worker_hostname": _get_worker_hostname(),
                "meta": {},
            },
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

    # NEW: If max attempts reached → fail run
    # if step.attempts >= 3:
    #     AuditRun.objects.filter(id=step.audit_run_id).update(
    #         status=AuditRun.Status.FAILED,
    #         error_summary=f"{step.step_name} failed: {err}",
    #         finished_at=now,
    #     )


# -----------------------------
# Tasks
# -----------------------------

@shared_task(
    name="apps.seo.tasks.steps.fetch_client_page",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    max_retries=3,
)
def fetch_client_page(self, run_id: str):
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
        err = str(e)
        _finish_failed(step, attempt, err)

        if step.attempts < 3:
            raise self.retry(countdown=30)
        else:
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



@shared_task(name="apps.seo.tasks.steps.build_keyword_set", bind=True)
def build_keyword_set(self, run_id: str):
    logger.info("🔄 [KEYWORDS] Step started | run_id=%s", run_id)

    step, attempt, info = _claim_step(run_id, RunStep.StepName.KEYWORDS)

    logger.info(
        "🔄 [KEYWORDS] Step claim | step=%s | attempt=%s | info=%s",
        str(step), str(attempt), str(info),
    )

    if step is None:
        logger.info("⏭️ [KEYWORDS] Step already handled | run_id=%s", run_id)
        return {"run_id": run_id, "step": "KEYWORDS", **info}

    try:
        logger.info("📥 [KEYWORDS] Loading run | run_id=%s", run_id)
        run = AuditRun.objects.get(id=run_id)

        # ---- REAL SOURCE: client snapshot ----
        client_snapshot = (
            run.page_snapshots
            .filter(role=PageSnapshot.Role.CLIENT)
            .order_by("-fetched_at")
            .first()
        )

        if not client_snapshot:
            logger.warning("⚠️ [KEYWORDS] No client snapshot found | run_id=%s", run_id)
            raise ValueError("Client snapshot missing — cannot extract keywords")

        extracted = client_snapshot.extracted or {}
        text_seed = " ".join([
            extracted.get("title") or "",
            extracted.get("h1") or "",
        ])

        if not text_seed.strip():
            logger.warning("⚠️ [KEYWORDS] Snapshot text empty | run_id=%s", run_id)
            raise ValueError("Snapshot contains no usable text")

        logger.info("🧠 [KEYWORDS] Generating keyword candidates")

        # ---- VERY SIMPLE heuristic extractor (replace with NLP later) ----
        words = [w.lower() for w in text_seed.split() if len(w) > 3]
        unique_words = list(dict.fromkeys(words))[:10]

        kws: List[Dict] = [
            {"kw": w, "w": round(1.0 - (i * 0.05), 2)}
            for i, w in enumerate(unique_words)
        ]

        if not kws:
            raise ValueError("Keyword extraction produced empty list")

        logger.info("📊 [KEYWORDS] Extracted | count=%s", len(kws))

        # ---- Ensure only one EXTRACTED version per run ----
        KeywordSetVersion.objects.filter(
            audit_run=run,
            source=KeywordSetVersion.Source.EXTRACTED
        ).delete()

        KeywordSetVersion.objects.create(
            audit_run=run,
            source=KeywordSetVersion.Source.EXTRACTED,
            keywords=kws,
        )

        logger.info("💾 [KEYWORDS] KeywordSetVersion saved | run_id=%s", run_id)

        _finish_success(step, attempt, meta={"count": len(kws)})

        logger.info("🎯 [KEYWORDS] Step marked SUCCESS | run_id=%s", run_id)

        return {"run_id": run_id, "step": "KEYWORDS", "status": "success"}

    except Exception as e:
        logger.exception(
            "❌ [KEYWORDS] Step FAILED | run_id=%s | error=%s",
            run_id, str(e),
        )

        _finish_failed(step, attempt, str(e))
        raise


@shared_task(
    name="apps.seo.tasks.steps.serp_capture_batch",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    max_retries=3
)
def serp_capture_batch(self, run_id: str):
    logger.info("🔄 [SERP] Batch started | run_id=%s", run_id)

    step, attempt, info = _claim_step(run_id, RunStep.StepName.SERP)

    logger.info("🔄 [SERP] Step claim result | step=%s | attempt=%s | info=%s",
                str(step), str(attempt), str(info))

    if step is None:
        logger.info("⏭️ [SERP] Step already completed or skipped | run_id=%s", run_id)
        return {"run_id": run_id, "step": "SERP", **info}

    try:
        logger.info("📥 [SERP] Fetching AuditRun from DB | run_id=%s", run_id)
        run = AuditRun.objects.select_related("client_site").get(id=run_id)

        logger.info("📥 [SERP] Run loaded | site=%s | status=%s",
                    run.client_site.normalized_url, run.status)

        latest_kw_set = run.keyword_sets.order_by("-created_at").first()

        if latest_kw_set:
            logger.info("📚 [SERP] Latest keyword set found | created_at=%s",
                        latest_kw_set.created_at)
        else:
            logger.warning("⚠️ [SERP] No keyword set found | run_id=%s", run_id)

        keywords = (latest_kw_set.keywords if latest_kw_set else [])[:5]

        logger.info("📝 [SERP] Keywords selected | count=%s | keywords=%s",
                    len(keywords), str(keywords))

        config = run.config or {}

        if isinstance(config, str):
            s = config.strip()

            # NEW: handle empty/"null"/"none" strings safely
            if not s or s.lower() in ("null", "none", "undefined"):
                logger.warning("⚠️ [SERP] Config string is empty/null-like | raw=%r", config)  # NEW:
                config = {}
            else:
                try:
                    logger.info("🧩 [SERP] Parsing config JSON string | raw=%r", s[:200])  # NEW:
                    config = json.loads(s)  # NEW:
                except json.JSONDecodeError as err:  # NEW:
                    logger.error("❌ [SERP] Config JSON decode failed | raw=%r | error=%s", s[:200], str(err))  # NEW:
                    config = {}
        else:
            logger.info("✅ [SERP] Config already dict | keys=%s", list((config or {}).keys()))  # NEW:

        logger.info("⚙️ [SERP] Config detected | %s", str(config))

        provider_name = config.get("provider", "mock")
        logger.info("🌐 [SERP] Provider selected | provider=%s", provider_name)

        from django.conf import settings

        if provider_name == "google":
            logger.info("🔑 [SERP] Using GoogleSerpProvider")
            from apps.seo.providers.serp.google import GoogleSerpProvider
            provider = GoogleSerpProvider(api_key=settings.SERP_API_KEY)

        elif provider_name == "simple_google":
            logger.info("🔑 [SERP] Using SimpleGoogleScrapeProvider")
            from apps.seo.providers.serp.simple_google_scrape import SimpleGoogleScrapeProvider
            provider = SimpleGoogleScrapeProvider()

        elif provider_name == "duckduckgo":
            logger.info("🔑 [SERP] Using DuckDuckGoSerpProvider")
            from apps.seo.providers.serp.duckduckgo import DuckDuckGoSerpProvider
            provider = DuckDuckGoSerpProvider()

        elif provider_name == "brave":
            logger.info("🔑 [SERP] Using BraveSerpProvider")
            from apps.seo.providers.serp.brave import BraveSerpProvider
            provider = BraveSerpProvider(api_key=settings.BRAVE_API_KEY)

        else:
            logger.info("🔑 [SERP] Using MockSerpProvider")
            from apps.seo.providers.serp.mock import MockSerpProvider
            provider = MockSerpProvider()

        client_domain = extract_domain(run.client_site.normalized_url)
        logger.info("🏷️ [SERP] Client domain extracted | %s", client_domain)

        for item in keywords:
            kw = item["kw"]
            logger.info("🔍 [SERP] Processing keyword | %s", kw)

            organic_results = provider.search(
                keyword=kw,
                geo=run.client_site.geo,
                device=run.client_site.device,
            )

            logger.info("📊 [SERP] Results fetched | keyword=%s | total_results=%s",
                        kw, len(organic_results))

            top_results = organic_results[:5]
            logger.info("📊 [SERP] Top 5 results extracted | keyword=%s", kw)

            competitors = []
            client_position = None

            for idx, result in enumerate(top_results, start=1):
                result_url = result.get("link")

                if not result_url:
                    logger.warning("⚠️ [SERP] Missing link in result | keyword=%s | idx=%s", kw, idx)
                    continue

                result_domain = extract_domain(result_url)

                logger.debug("🔎 [SERP] Result analyzed | keyword=%s | idx=%s | domain=%s",
                             kw, idx, result_domain)

                if result_domain == client_domain:
                    client_position = idx
                    logger.info("🏆 [SERP] Client found in SERP | keyword=%s | position=%s",
                                kw, idx)
                else:
                    competitors.append(result_domain)

            logger.info("👥 [SERP] Competitors detected | keyword=%s | competitors=%s",
                        kw, competitors)

            SerpSnapshot.objects.create(
                audit_run=run,
                keyword=kw,
                provider=provider_name,
                provider_meta={},
                results={"top": top_results},
            )

            logger.info("💾 [SERP] SerpSnapshot saved | keyword=%s", kw)

            KeywordResult.objects.create(
                audit_run=run,
                keyword=kw,
                client_position=client_position,
                visibility_score=1 / (client_position or 100),
                difficulty_score=0.5,
                competitor_urls=competitors,
            )

            logger.info("💾 [SERP] KeywordResult saved | keyword=%s | position=%s",
                        kw, client_position)

        logger.info("✅ [SERP] All keywords processed | count=%s", len(keywords))

        _finish_success(step, attempt, meta={"keywords_processed": len(keywords)})

        logger.info("🎯 [SERP] Step marked SUCCESS | run_id=%s", run_id)

        return {"run_id": run_id, "step": "SERP", "status": "success"}

    except Exception as e:
        logger.exception("❌ [SERP] Step FAILED | run_id=%s | error=%s", run_id, str(e))

        _finish_failed(step, attempt, str(e))

        if step.attempts < 3:
            logger.warning("🔁 [SERP] Retrying step | attempt=%s", step.attempts)
            raise self.retry(countdown=30)
        else:
            logger.error("⛔ [SERP] Max retries reached | run_id=%s", run_id)
            raise     

@shared_task(name="apps.seo.tasks.steps.fetch_competitors",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    max_retries=5,
)
def fetch_competitors(self, run_id: str):
    logger.info("🔄 [COMPETITORS] Step started | run_id=%s", run_id)

    step, attempt, info = _claim_step(run_id, RunStep.StepName.COMPETITORS)

    logger.info("🔄 [COMPETITORS] Step claim | step=%s | attempt=%s | info=%s",
                str(step), str(attempt), str(info))

    if step is None:
        logger.info("⏭️ [COMPETITORS] Step already handled | run_id=%s", run_id)
        return {"run_id": run_id, "step": "COMPETITORS", **info}

    try:
        logger.info("📥 [COMPETITORS] Loading run | run_id=%s", run_id)
        run = AuditRun.objects.get(id=run_id)

        keyword_results = run.keyword_results.all()
        logger.info("📊 [COMPETITORS] Keyword results loaded | count=%s", keyword_results.count())

        fetched_domains = set()

        for kr in keyword_results:
            logger.info("🔍 [COMPETITORS] Processing KeywordResult | keyword=%s | competitors_count=%s",
                        getattr(kr, "keyword", None), len(kr.competitor_urls or []))

            for domain in kr.competitor_urls:
                if domain in fetched_domains:
                    logger.debug("⏭️ [COMPETITORS] Domain already fetched | domain=%s", domain)
                    continue

                logger.info("🌐 [COMPETITORS] Fetching competitor page | domain=%s", domain)

                try:
                    response = fetch_page(domain)

                    # if ran into error page is blank nothing for beautiful soup to fetch
                    if not response:
                        logger.warning("⚠️ [COMPETITORS] Empty/No response from fetch_page | domain=%s", domain)

                        import hashlib
                        html_hash = hashlib.sha256("html_content".encode()).hexdigest()

                        logger.info("💾 [COMPETITORS] Saving placeholder snapshot | domain=%s | http_status=404", domain)
                        PageSnapshot.objects.update_or_create(  # NEW:
                            audit_run=run,
                            url=f"https://{domain}",
                            role=PageSnapshot.Role.COMPETITOR,
                            defaults={  # NEW:
                                "http_status": 404,  # NEW: int field (you had "404" string)
                                "html_hash": html_hash,
                                "content_type": "Unknown",
                                "extracted": {
                                    "title": "empty",
                                    "h1": "empty",
                                    "word_count": 0,
                                },
                                "raw_html_ref": "unknown ran into error",
                            },
                        )
                        logger.error("❌ [COMPETITORS] Raising after placeholder snapshot | domain=%s", domain)
                        fetched_domains.add(domain)  # NEW: count it so we don't loop it again
                        continue  # NEW: do not raise; move to next competitor

                    logger.info("✅ [COMPETITORS] Response received | domain=%s | status=%s | content_type=%s",
                                domain,
                                getattr(response, "status_code", None),
                                getattr(response, "headers", {}).get("Content-Type") if getattr(response, "headers", None) else None)

                    soup = BeautifulSoup(response.text, "html.parser")

                    title = soup.title.string.strip() if soup.title else None
                    h1 = soup.find("h1")
                    h1_text = h1.get_text(strip=True) if h1 else None
                    word_count = len(soup.get_text().split())

                    logger.info("🧾 [COMPETITORS] Extracted | domain=%s | title=%s | h1=%s | words=%s",
                                domain, str(title), str(h1_text), word_count)

                    # NEW: html_hash must NEVER be None (model NOT NULL)
                    import hashlib  # NEW:
                    html_hash = hashlib.sha256((response.text or "").encode()).hexdigest()  # NEW:
                    logger.info("🔑 [COMPETITORS] Computed html_hash | domain=%s | hash=%s", domain, html_hash)  # NEW:

                    logger.info("💾 [COMPETITORS] Saving PageSnapshot | domain=%s", domain)

                    # PageSnapshot.objects.create(
                    #     audit_run=run,
                    #     url=f"https://{domain}",
                    #     role=PageSnapshot.Role.COMPETITOR,
                    #     http_status=response.status_code,
                    #     html_hash=html_hash,  # NEW: was None → caused NOT NULL crash
                    #     content_type=response.headers.get("Content-Type"),
                    #     extracted={
                    #         "title": title,
                    #         "h1": h1_text,
                    #         "word_count": word_count,
                    #     },
                    #     raw_html_ref=response.text,
                    # )
                    PageSnapshot.objects.update_or_create(  # NEW:
                        audit_run=run,
                        url=f"https://{domain}",
                        role=PageSnapshot.Role.COMPETITOR,
                        defaults={  # NEW:
                            "http_status": response.status_code,
                            "html_hash": html_hash,
                            "content_type": response.headers.get("Content-Type"),
                            "extracted": {
                                "title": title,
                                "h1": h1_text,
                                "word_count": word_count,
                            },
                            "raw_html_ref": response.text,
                        },
                    )
                    fetched_domains.add(domain)
                    logger.info("✅ [COMPETITORS] Domain saved | domain=%s | fetched_total=%s",
                                domain, len(fetched_domains))

                except Exception as ex:
                    logger.exception("❌ [COMPETITORS] Domain fetch/save failed | domain=%s | error=%s",
                                     domain, str(ex))
                    # transient failure → retry whole step
                    raise

        logger.info("✅ [COMPETITORS] Completed | competitors_fetched=%s", len(fetched_domains))

        _finish_success(step, attempt, meta={"competitors_fetched": len(fetched_domains)})

        logger.info("🎯 [COMPETITORS] Step marked SUCCESS | run_id=%s", run_id)

        return {"run_id": run_id, "step": "COMPETITORS", "status": "success"}

    except Exception as e:
        logger.exception("❌ [COMPETITORS] Step FAILED | run_id=%s | error=%s", run_id, str(e))

        _finish_failed(step, attempt, str(e))

        if step.attempts < 3:
            logger.warning("🔁 [COMPETITORS] Retrying whole step | attempt=%s", step.attempts)
            raise self.retry(countdown=30)
        else:
            logger.error("⛔ [COMPETITORS] Max retries reached | run_id=%s", run_id)
            raise    
        
@shared_task(name="apps.seo.tasks.steps.analyze_and_recommend")
def analyze_and_recommend(run_id: str):
    step, attempt, info = _claim_step(run_id, RunStep.StepName.ANALYZE)
    if step is None:
        return {"run_id": run_id, "step": "ANALYZE", **info}

    try:
        run = AuditRun.objects.get(id=run_id)

        client_snapshot = run.page_snapshots.filter(
            role=PageSnapshot.Role.CLIENT
        ).first()

        competitor_snapshots = run.page_snapshots.filter(
            role=PageSnapshot.Role.COMPETITOR
        )

        if not client_snapshot:
            raise Exception("Client snapshot missing")

        client_word_count = client_snapshot.extracted.get("word_count", 0)

        competitor_word_counts = [
            snap.extracted.get("word_count", 0)
            for snap in competitor_snapshots
        ]

        avg_competitor_wc = (
            sum(competitor_word_counts) / len(competitor_word_counts)
            if competitor_word_counts else 0
        )

        recommendations_created = 0

        if client_word_count < avg_competitor_wc:
            Recommendation.objects.create(
                audit_run=run,
                keyword=None,
                action_type="content_expand",
                priority=Recommendation.Priority.HIGH,
                expected_impact=Recommendation.Priority.HIGH,
                reason_text=(
                    f"Client content length ({client_word_count}) "
                    f"is below competitor average ({int(avg_competitor_wc)}). "
                    "Expand content depth and coverage."
                ),
                evidence_refs=[],
            )
            recommendations_created += 1

        for kr in run.keyword_results.all():
            if kr.client_position is None or kr.client_position > 5:
                Recommendation.objects.create(
                    audit_run=run,
                    keyword=kr.keyword,
                    action_type="ranking_improvement",
                    priority=Recommendation.Priority.HIGH,
                    expected_impact=Recommendation.Priority.HIGH,
                    reason_text=(
                        f"Keyword '{kr.keyword}' not ranking in top 5. "
                        "Optimize page structure and keyword alignment."
                    ),
                    evidence_refs=[],
                )
                recommendations_created += 1

        _finish_success(step, attempt, meta={"recommendations": recommendations_created})
        return {"run_id": run_id, "step": "ANALYZE", "status": "success"}

    except Exception as e:
        _finish_failed(step, attempt, str(e))
        raise
    
@shared_task(name="apps.seo.tasks.steps.finalize_run")
def finalize_run(run_id: str):
    logger.info("🏁 [FINALIZE] Step started | run_id=%s", run_id)

    step, attempt, info = _claim_step(run_id, RunStep.StepName.FINALIZE)

    logger.info(
        "🔒 [FINALIZE] Step claim | step=%s | attempt=%s | info=%s",
        str(step), str(attempt), str(info),
    )

    if step is None:
        logger.info("⏭️ [FINALIZE] Step already handled | run_id=%s | info=%s", run_id, info)
        return {"run_id": run_id, "step": "FINALIZE", **info}

    try:
        logger.info("📥 [FINALIZE] Loading run | run_id=%s", run_id)
        run = AuditRun.objects.get(id=run_id)
        logger.info("✅ [FINALIZE] Run loaded | run_id=%s | status=%s", run_id, getattr(run, "status", None))

        logger.info("📊 [FINALIZE] Counting keyword_results | run_id=%s", run_id)
        keywords_count = run.keyword_results.count()
        logger.info("✅ [FINALIZE] keyword_results count=%s | run_id=%s", keywords_count, run_id)

        logger.info("📊 [FINALIZE] Counting recommendations | run_id=%s", run_id)
        recommendations_count = run.recommendations.count()
        logger.info("✅ [FINALIZE] recommendations count=%s | run_id=%s", recommendations_count, run_id)

        logger.info("📊 [FINALIZE] Counting page_snapshots | run_id=%s", run_id)
        snapshots_count = run.page_snapshots.count()
        logger.info("✅ [FINALIZE] page_snapshots count=%s | run_id=%s", snapshots_count, run_id)

        summary = {
            "keywords": keywords_count,
            "recommendations": recommendations_count,
            "snapshots": snapshots_count,
        }
        logger.info("🧾 [FINALIZE] Summary prepared | run_id=%s | summary=%s", run_id, summary)

        logger.info("💾 [FINALIZE] Updating AuditRun fields | run_id=%s", run_id)
        # run.status = AuditRun.Status.SUCCESS
        run.summary = summary
        run.finished_at = timezone.now()
        logger.info("⏱️ [FINALIZE] finished_at set | run_id=%s | finished_at=%s", run_id, str(run.finished_at))

        logger.info("💾 [FINALIZE] Saving AuditRun | run_id=%s", run_id)
        run.save(update_fields=["summary", "status", "finished_at"])
        logger.info("✅ [FINALIZE] AuditRun saved | run_id=%s", run_id)

        logger.info("🏷️ [FINALIZE] Marking step SUCCESS | run_id=%s", run_id)
        _finish_success(step, attempt, meta=summary)
        logger.info("🎯 [FINALIZE] Step marked SUCCESS | run_id=%s", run_id)

        return {"run_id": run_id, "step": "FINALIZE", "status": "success"}

    except Exception as e:
        logger.exception("❌ [FINALIZE] Step FAILED | run_id=%s | error=%s", run_id, str(e))

        now = timezone.now()
        logger.info("💾 [FINALIZE] Marking run FAILED | run_id=%s | finished_at=%s", run_id, str(now))

        AuditRun.objects.filter(id=run_id).update(
            error_summary=str(e),
            finished_at=now,
        )
        logger.info("✅ [FINALIZE] Run updated to FAILED | run_id=%s", run_id)

        logger.info("🏷️ [FINALIZE] Marking step FAILED | run_id=%s", run_id)
        _finish_failed(step, attempt, str(e))
        logger.info("🧨 [FINALIZE] Raising exception | run_id=%s", run_id)
        raise
