# apps/seo/tasks/steps.py
from __future__ import annotations
import logging
import hashlib
import time
from typing import List, Dict, Any, Optional
import json
from apps.seo.providers.serp_base import extract_domain, fetch_page
from apps.seo.utils.functions import compress_html, extract_page_data
from celery import shared_task, current_task
from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from apps.seo.notifications import notify
from apps.seo.models import Notification
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
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    max_retries=3,
)
def fetch_client_page(self, run_id: str):
    step, attempt, info = _claim_step(run_id, RunStep.StepName.FETCH_CLIENT)
    if step is None:
        return {"run_id": run_id, "step": "FETCH_CLIENT", **info}

    run = AuditRun.objects.select_related("client_site").get(id=run_id)
    try:
        url = run.client_site.url

        logger.info("[FETCH_CLIENT] Fetching URL | %s", url)

        response = fetch_page(url)
        if not response:
            raise ValueError(f"Empty response for {url}")

        html = response.text or ""

        # ---- Hash ----
        html_hash = hashlib.sha256(html.encode("utf-8")).hexdigest()

        # ---- Extract structured data ----
        extracted_data = extract_page_data(html, url)

        # ---- Compress HTML ----
        compressed_html = compress_html(html)

        logger.info(
            "✅ [FETCH_CLIENT] Extracted | words=%s | keywords=%s",
            extracted_data.get("word_count"),
            len(extracted_data.get("top_keywords", [])),
        )

        # ---- Save snapshot ----
        PageSnapshot.objects.update_or_create(
            audit_run=run,
            url=url,
            role=PageSnapshot.Role.CLIENT,
            defaults={
                "http_status": response.status_code,
                "html_hash": html_hash,
                "content_type": response.headers.get("Content-Type"),
                "extracted": extracted_data,
                "raw_html_ref": compressed_html,  # ✅ compressed now
            },
        )

        _finish_success(
            step,
            attempt,
            meta={
                "url": url,
                "word_count": extracted_data.get("word_count"),
                "keywords": len(extracted_data.get("top_keywords", [])),
            },
        )

        notify(
            run=run,
            event_type=Notification.EventType.STEP_SUCCESS,
            title="Page fetched",
            body=f"Successfully fetched and analyzed {url}",
            meta={
                "step": "FETCH_CLIENT",
                "word_count": extracted_data.get("word_count"),
            },
        )

        return {"run_id": run_id, "step": "FETCH_CLIENT", "status": "success"}

    except Exception as e:
        err = str(e)
        logger.exception("[FETCH_CLIENT] FAILED | run_id=%s | error=%s", run_id, err)

        _finish_failed(step, attempt, err)

        if step.attempts > 3:
            notify(
                run=run,
                event_type=Notification.EventType.STEP_FAILED,
                title="Fetch failed",
                body=f"Failed after {step.attempts} attempts: {err}",
                meta={"step": "FETCH_CLIENT", "error": err},
            )
            raise
        else:
            raise self.retry(countdown=30)

@shared_task(
    name="apps.seo.tasks.steps.classify_site",
    bind=True,
    
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    max_retries=3,
)
def classify_site(self, run_id: str):
    step, attempt, info = _claim_step(run_id, RunStep.StepName.CLASSIFY)
    if step is None:
        return {"run_id": run_id, "step": "CLASSIFY", **info}

    run = AuditRun.objects.select_related("client_site").get(id=run_id)
    try:

        # Pull real data from the client snapshot
        client_snapshot = (
            run.page_snapshots
            .filter(role=PageSnapshot.Role.CLIENT)
            .order_by("-fetched_at")
            .first()
        )

        if not client_snapshot:
            raise ValueError("Client snapshot missing — cannot classify site")

        extracted = client_snapshot.extracted or {}
        text = " ".join([
            extracted.get("title") or "",
            extracted.get("h1") or "",
        ]).lower().strip()

        logger.info("[CLASSIFY] Classifying site | run_id=%s | text_seed=%r", run_id, text[:120])

        # Simple niche keyword map — extend as needed
        NICHE_MAP = {
            "ecommerce":    ["shop", "store", "buy", "cart", "checkout", "product", "price", "sale", "order", "shipping"],
            "saas":         ["software", "platform", "dashboard", "integration", "api", "subscription", "trial", "cloud", "automation"],
            "blog":         ["blog", "article", "post", "news", "guide", "tips", "how to", "tutorial", "read", "story"],
            "finance":      ["finance", "invest", "loan", "bank", "insurance", "mortgage", "credit", "trading", "tax", "wealth"],
            "health":       ["health", "medical", "doctor", "clinic", "wellness", "fitness", "diet", "nutrition", "therapy", "hospital"],
            "real_estate":  ["property", "real estate", "rent", "lease", "apartment", "house", "mortgage", "realtor", "listing", "buy home"],
            "education":    ["course", "learn", "school", "university", "training", "certification", "study", "tutor", "education", "class"],
            "agency":       ["agency", "marketing", "seo", "design", "branding", "creative", "digital", "consulting", "strategy", "advertising"],
            "travel":       ["travel", "hotel", "flight", "tour", "booking", "vacation", "trip", "destination", "holiday", "resort"],
            "legal":        ["law", "legal", "attorney", "lawyer", "firm", "court", "contract", "compliance", "litigation", "counsel"],
        }

        scores = {}
        for niche, keywords in NICHE_MAP.items():
            scores[niche] = sum(1 for kw in keywords if kw in text)

        logger.info("[CLASSIFY] Niche scores | run_id=%s | scores=%s", run_id, scores)

        best_niche = max(scores, key=scores.get)
        best_score = scores[best_niche]

        # If nothing matched fall back to "general"
        niche_label = best_niche if best_score > 0 else "general"

        logger.info("[CLASSIFY] Niche resolved | run_id=%s | niche=%s | score=%s", run_id, niche_label, best_score)

        run.client_site.niche_label = niche_label
        run.client_site.save(update_fields=["niche_label"])

        _finish_success(step, attempt, meta={"niche_label": niche_label, "score": best_score, "all_scores": scores})
        notify(
            run=run,
            event_type=Notification.EventType.STEP_SUCCESS,
            title="Site classified",
            body=f"Site identified as {niche_label}",
            meta={"step": "CLASSIFY", "niche": niche_label, "score": best_score},
        )
        return {"run_id": run_id, "step": "CLASSIFY", "status": "success", "niche": niche_label}

    except Exception as e:
        logger.exception("[CLASSIFY] Step FAILED | run_id=%s | error=%s", run_id, str(e))
        _finish_failed(step, attempt, str(e))

        if step.attempts >= 3:
            notify(
                run=run,
                event_type=Notification.EventType.STEP_FAILED,
                title=f"{step.step_name} failed",
                body=f"Step failed after {step.attempts} attempts. Error: {e}",
                meta={"step": step.step_name, "attempts": step.attempts, "error": str(e)},
            )
            logger.error("⛔ [CLASSIFY] Max retries reached | run_id=%s", run_id)
            raise
        else:
            logger.warning("🔁 [CLASSIFY] Retrying step | attempt=%s", step.attempts)
            raise self.retry(countdown=30)



@shared_task(
    name="apps.seo.tasks.steps.build_keyword_set",
    bind=True,
    
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    max_retries=3,
)
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

    run = AuditRun.objects.get(id=run_id)
    try:
        logger.info("📥 [KEYWORDS] Loading run | run_id=%s", run_id)

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
        STOP_WORDS = {
            "the", "and", "for", "are", "but", "not", "you", "all", "can", "her",
            "was", "one", "our", "out", "day", "get", "has", "him", "his", "how",
            "its", "may", "new", "now", "old", "see", "two", "who", "boy", "did",
            "she", "too", "use", "way", "with", "that", "this", "have", "from",
            "they", "will", "been", "more", "when", "your", "what", "said", "each",
            "which", "their", "time", "into", "than", "then", "some", "could",
            "these", "other", "also", "just", "over", "such", "very", "well",
            "even", "most", "made", "after", "where", "while", "about", "would",
        }

        words = [
            w.lower() for w in text_seed.split()
            if len(w) >= 3 and w.lower() not in STOP_WORDS
        ]
        unique_words = list(dict.fromkeys(words))[:10]
        # words = [w.lower() for w in text_seed.split() if len(w) > 3]
        # unique_words = list(dict.fromkeys(words))[:10]

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

        notify(
            run=run,
            event_type=Notification.EventType.STEP_SUCCESS,
            title="Keywords extracted",
            body=f"Found {len(kws)} keywords",
            meta={"step": "KEYWORDS", "count": len(kws)},
        )
        return {"run_id": run_id, "step": "KEYWORDS", "status": "success"}

    except Exception as e:
        logger.exception(
            "❌ [KEYWORDS] Step FAILED | run_id=%s | error=%s",
            run_id, str(e),
        )

        _finish_failed(step, attempt, str(e))

        if step.attempts >= 3:
            notify(
                run=run,
                event_type=Notification.EventType.STEP_FAILED,
                title=f"{step.step_name} failed",
                body=f"Step failed after {step.attempts} attempts. Error: {e}",
                meta={"step": step.step_name, "attempts": step.attempts, "error": str(e)},
            )
            logger.error("⛔ [KEYWORDS] Max retries reached | run_id=%s", run_id)
            raise
        else:
            logger.warning("🔁 [KEYWORDS] Retrying step | attempt=%s", step.attempts)
            raise self.retry(countdown=30)

@shared_task(
    name="apps.seo.tasks.steps.serp_capture_batch",
    bind=True,
    
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

    run = AuditRun.objects.select_related("client_site").get(id=run_id)
    try:
        logger.info("📥 [SERP] Fetching AuditRun from DB | run_id=%s", run_id)

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
                logger.warning("⚠️ [SERP] Config string is empty/null-like | raw=%r", config)
                config = {}
            else:
                try:
                    logger.info("🧩 [SERP] Parsing config JSON string | raw=%r", s[:200])
                    config = json.loads(s)
                except json.JSONDecodeError as err:
                    logger.error("❌ [SERP] Config JSON decode failed | raw=%r | error=%s", s[:200], str(err))
                    config = {}
        else:
            logger.info("✅ [SERP] Config already dict | keys=%s", list((config or {}).keys()))

        logger.info("⚙️ [SERP] Config detected | %s", str(config))

        from django.conf import settings
        provider_name = config.get("provider") or getattr(settings, "SERP_PROVIDER", "duckduckgo")
        logger.info("🌐 [SERP] Provider selected | provider=%s", provider_name)


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

            top_results = organic_results[:10]
            logger.info("📊 [SERP] Top 10 results extracted | keyword=%s", kw)

            competitors = []
            client_position = None
            clean_results = []  # NEW: structured results

            for idx, result in enumerate(top_results, start=1):
                result_url = result.get("link")
                title = result.get("title")      # NEW
                snippet = result.get("snippet")  # NEW

                if not result_url:
                    logger.warning("⚠️ [SERP] Missing link in result | keyword=%s | idx=%s", kw, idx)
                    continue

                result_domain = extract_domain(result_url)

                logger.debug("🔎 [SERP] Result analyzed | keyword=%s | idx=%s | domain=%s",
                             kw, idx, result_domain)

                # NEW: structured result
                clean_results.append({
                    "position": idx,
                    "link": result_url,
                    "title": title,
                    "snippet": snippet,
                })

                if result_domain == client_domain:
                    client_position = idx
                    logger.info("🏆 [SERP] Client found in SERP | keyword=%s | position=%s",
                                kw, idx)
                else:
                    competitors.append(result_url)

            logger.info("👥 [SERP] Competitors detected | keyword=%s | competitors=%s",
                        kw, competitors)

            # AFTER
            if not SerpSnapshot.objects.filter(audit_run=run, keyword=kw).exists():
                SerpSnapshot.objects.create(
                    audit_run=run,
                    keyword=kw,
                    provider=provider_name,
                    provider_meta={},
                    results={"top": clean_results},
                )
            else:
                logger.info("⏭️ [SERP] SerpSnapshot already exists, skipping | keyword=%s", kw)

            logger.info("💾 [SERP] SerpSnapshot saved | keyword=%s", kw)
            # AFTER
            existing_kr = KeywordResult.objects.filter(audit_run=run, keyword=kw).first()
            merged_competitors = list(set((existing_kr.competitor_urls or []) + competitors)) if existing_kr else competitors

            KeywordResult.objects.update_or_create(
                audit_run=run,
                keyword=kw,
                defaults={
                    "client_position": client_position,
                    "visibility_score": 1 / (client_position or 100),
                    "difficulty_score": 0.5,
                    "competitor_urls": merged_competitors,
                },
            )

            logger.info("💾 [SERP] KeywordResult saved | keyword=%s | position=%s",
                        kw, client_position)

        # =========================
        # NEW: DOMAIN-BASED SEARCH
        # =========================
        logger.info("🌐 [SERP] Running domain-based search")

        domain_query = client_domain

        domain_results = provider.search(
            keyword=domain_query,
            geo=run.client_site.geo,
            device=run.client_site.device,
        )

        domain_top = domain_results[:10]

        domain_competitors = []

        for result in domain_top:
            url = result.get("link")
            if not url:
                continue

            if extract_domain(url) != client_domain:
                domain_competitors.append(url)

        logger.info(
            "🌐 [SERP] Domain competitors found | count=%s",
            len(domain_competitors),
        )
        # AFTER
        existing_domain_kr = KeywordResult.objects.filter(audit_run=run, keyword="__domain_search__").first()
        merged_domain_competitors = list(set((existing_domain_kr.competitor_urls or []) + domain_competitors)) if existing_domain_kr else domain_competitors

        KeywordResult.objects.update_or_create(
            audit_run=run,
            keyword="__domain_search__",
            defaults={
                "client_position": None,
                "visibility_score": 0,
                "difficulty_score": 0,
                "competitor_urls": merged_domain_competitors,
            },
        )

        logger.info("✅ [SERP] All keywords processed | count=%s", len(keywords))

        _finish_success(step, attempt, meta={"keywords_processed": len(keywords)})

        notify(
            run=run,
            event_type=Notification.EventType.STEP_SUCCESS,
            title="SERP captured",
            body=f"Processed {len(keywords)} keywords",
            meta={"step": "SERP", "keywords_processed": len(keywords)},
        )
        logger.info("🎯 [SERP] Step marked SUCCESS | run_id=%s", run_id)

        return {"run_id": run_id, "step": "SERP", "status": "success"}

    except Exception as e:
        logger.exception("❌ [SERP] Step FAILED | run_id=%s | error=%s", run_id, str(e))

        _finish_failed(step, attempt, str(e))

        if step.attempts >= 3: 
            logger.error("⛔ [SERP] Max retries reached | run_id=%s", run_id)
            notify(
                run=run,
                event_type=Notification.EventType.STEP_FAILED,
                title=f"{step.step_name} failed",
                body=f"Step failed after {step.attempts} attempts. Error: {e}",
                meta={"step": step.step_name, "attempts": step.attempts, "error": str(e)},
            )
            raise     
        else:
            logger.warning("🔁 [SERP] Retrying step | attempt=%s", step.attempts)
            raise self.retry(countdown=30)


@shared_task(
    name="apps.seo.tasks.steps.fetch_competitors",
    bind=True,
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    max_retries=5,
)
def fetch_competitors(self, run_id: str):
    logger.info("🔄 [COMPETITORS]  Step started | run_id=%s", run_id)

    step, attempt, info = _claim_step(run_id, RunStep.StepName.COMPETITORS)

    logger.info("🔄 [COMPETITORS] Step claim | step=%s | attempt=%s | info=%s",
                str(step), str(attempt), str(info))

    if step is None:
        logger.info("⏭️ [COMPETITORS] Step already done | run_id=%s", run_id)
        return {"run_id": run_id, "step": "COMPETITORS", **info}

    run = AuditRun.objects.get(id=run_id)
    try:

        logger.info("📥 [COMPETITORS] Loading keyword results")

        keyword_results = run.keyword_results.all()

        logger.info("📊 [COMPETITORS] KeywordResult count=%s", keyword_results.count())

        # =========================
        # NEW: COLLECT + DEDUPE URLS
        # =========================
        competitor_urls = set()

        for kr in keyword_results:
            urls = kr.competitor_urls or []

            for url in urls:
                if url:
                    competitor_urls.add(url)

        logger.info(
            "👥 [COMPETITORS] Unique URLs collected | total=%s",
            len(competitor_urls),
        )

        # =========================
        # NEW: AVOID REFETCHING
        # =========================
        existing_urls = set(
            PageSnapshot.objects.filter(
                audit_run=run,
                role=PageSnapshot.Role.COMPETITOR
            ).values_list("url", flat=True)
        )

        logger.info(
            "📦 [COMPETITORS] Already fetched | count=%s",
            len(existing_urls),
        )

        urls_to_fetch = competitor_urls - existing_urls

        logger.info(
            "🚀 [COMPETITORS] To fetch | count=%s",
            len(urls_to_fetch),
        )

        fetched = 0
        failed = 0

        for url in urls_to_fetch:
            logger.info("🌐 [COMPETITORS] Fetching | %s", url)

            try:
                response = fetch_page(url)

                if not response:
                    raise ValueError("Empty response")

                html = response.text or ""

                # ---- hash ----
                html_hash = hashlib.sha256(html.encode("utf-8")).hexdigest()

                # ---- extract ----
                extracted_data = extract_page_data(html, url)

                # ---- compress ----
                compressed_html = compress_html(html)

                PageSnapshot.objects.update_or_create(
                    audit_run=run,
                    url=url,
                    role=PageSnapshot.Role.COMPETITOR,
                    defaults={
                        "http_status": response.status_code,
                        "html_hash": html_hash,
                        "content_type": response.headers.get("Content-Type"),
                        "extracted": extracted_data,
                        "raw_html_ref": compressed_html,
                    },
                )

                fetched += 1

                logger.info(
                    "✅ [COMPETITORS] Saved | url=%s | words=%s",
                    url,
                    extracted_data.get("word_count"),
                )

            except Exception as ex:
                failed += 1
                logger.warning(
                    "⚠️ [COMPETITORS] Failed | url=%s | error=%s",
                    url,
                    str(ex),
                )
                continue  # IMPORTANT: don't kill whole batch

        logger.info(
            "📊 [COMPETITORS] Done | fetched=%s | failed=%s | total=%s",
            fetched,
            failed,
            len(urls_to_fetch),
        )

        _finish_success(
            step,
            attempt,
            meta={
                "fetched": fetched,
                "failed": failed,
                "total": len(competitor_urls),
            },
        )

        notify(
            run=run,
            event_type=Notification.EventType.STEP_SUCCESS,
            title="Competitors analyzed",
            body=f"Fetched {fetched} competitor pages",
            meta={
                "step": "COMPETITORS",
                "fetched": fetched,
                "failed": failed,
                "total": len(competitor_urls),
            },
        )

        return {
            "run_id": run_id,
            "step": "COMPETITORS",
            "status": "success",
            "fetched": fetched,
            "failed": failed,
        }

    except Exception as e:
        err = str(e)
        logger.exception("❌ [COMPETITORS] FAILED | run_id=%s | error=%s", run_id, err)

        _finish_failed(step, attempt, err)

        if step.attempts >= 5:
            logger.error("⛔ [COMPETITORS] Max retries reached | run_id=%s", run_id)

            notify(
                run=run,
                event_type=Notification.EventType.STEP_FAILED,
                title="Competitor fetch failed",
                body=f"Failed after {step.attempts} attempts: {err}",
                meta={"step": "COMPETITORS", "error": err},
            )
            raise
        else:
            logger.warning("🔁 [COMPETITORS] Retrying | attempt=%s", step.attempts)
            raise self.retry(countdown=30)


        
@shared_task(name="apps.seo.tasks.steps.analyze_and_recommend",
    bind=True,
    
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    max_retries=3,
)
def analyze_and_recommend(self, run_id: str):
    step, attempt, info = _claim_step(run_id, RunStep.StepName.ANALYZE)
    if step is None:
        return {"run_id": run_id, "step": "ANALYZE", **info}

    try:
        from apps.seo.providers.llm.factory import get_llm_provider
        from apps.seo.providers.llm.prompts import build_analysis_prompt, SYSTEM_PROMPT
        from apps.seo.models import LLMBatch, LLMRun

        run = AuditRun.objects.select_related("client_site").get(id=run_id)
        logger.info("[ANALYZE] Run loaded | run_id=%s | site=%s | config=%s", run_id, run.client_site.url, run.config)

        client_snapshot = run.page_snapshots.filter(
            role=PageSnapshot.Role.CLIENT
        ).first()
        logger.info("[ANALYZE] Client snapshot | found=%s | url=%s", bool(client_snapshot), getattr(client_snapshot, "url", None))

        competitor_snapshots = list(run.page_snapshots.filter(
            role=PageSnapshot.Role.COMPETITOR
        ))
        logger.info("[ANALYZE] Competitor snapshots | count=%s", len(competitor_snapshots))

        if not client_snapshot:
            raise Exception("Client snapshot missing")

        # ---- Build prompt context ----
        competitor_data = [
            {"url": s.url, "extracted": s.extracted or {}}
            for s in competitor_snapshots
        ]

        keyword_data = [
            {
                "keyword": kr.keyword,
                "position": kr.client_position,
                "competitors": kr.competitor_urls or [],
            }
            for kr in run.keyword_results.all()
        ]
        logger.info("[ANALYZE] Prompt context | competitors=%s | keywords=%s", len(competitor_data), len(keyword_data))

        # =========================
        # NEW: PRE-ANALYSIS (STRUCTURED SIGNALS)
        # =========================
        logger.info("[ANALYZE] Running pre-analysis computations")

        client_data = client_snapshot.extracted or {}

        comp_word_counts = []
        comp_keywords = []

        for snap in competitor_snapshots:
            data = snap.extracted or {}

            if data.get("word_count"):
                comp_word_counts.append(data["word_count"])

            for kw in data.get("top_keywords", []):
                if isinstance(kw, dict):
                    comp_keywords.append(kw.get("kw"))
                else:
                    comp_keywords.append(kw)

        from collections import Counter

        avg_comp_words = int(sum(comp_word_counts) / len(comp_word_counts)) if comp_word_counts else 0
        top_comp_keywords = [kw for kw, _ in Counter(comp_keywords).most_common(10)]

        client_words = client_data.get("word_count", 0)
        client_keywords_raw = client_data.get("top_keywords", [])

        client_keywords = [
            kw.get("kw") if isinstance(kw, dict) else kw
            for kw in client_keywords_raw
        ]

        missing_keywords = [
            kw for kw in top_comp_keywords
            if kw not in client_keywords
        ]

        content_gap = avg_comp_words - client_words

        logger.info(
            "[ANALYZE] Pre-analysis | client_words=%s | avg_comp_words=%s | gap=%s | missing_kw=%s",
            client_words,
            avg_comp_words,
            content_gap,
            len(missing_keywords),
        )
        prompt = build_analysis_prompt(
            client_url=run.client_site.url,
            client_extracted=client_snapshot.extracted or {},
            competitor_snapshots=competitor_data,
            keyword_results=keyword_data,
            geo=run.client_site.geo,
            language=run.client_site.language,
            device=run.client_site.device,
            pre_analysis={
                "client_word_count": client_words,
                "avg_competitor_word_count": avg_comp_words,
                "content_gap": content_gap,
                "missing_keywords": missing_keywords[:10],
                "top_competitor_keywords": top_comp_keywords,
            },
        )
        logger.info("[ANALYZE] Prompt built | chars=%s | snippet=%s", len(prompt), prompt[:200])

        # ---- Resolve provider from run.config ----
        # provider = get_llm_provider(run.config or {})
        config = {"llm_provider": "openrouter", "llm_model": "openai/gpt-4o-mini"}
        logger.info("[ANALYZE] Config | %s", config)
        provider = get_llm_provider(config or {})
        logger.info("[ANALYZE] LLM provider resolved | provider=%s | run_id=%s", provider.name, run_id)

        # ---- Create LLMBatch — one per prompt sent ----
        batch = LLMBatch.objects.create(
            audit_run = run,
            provider  = provider.name,
            model     = config.get("llm_model", ""),
            prompt    = prompt,
            system    = SYSTEM_PROMPT,
        )
        logger.info("[ANALYZE] LLMBatch created | batch_id=%s", batch.id)

        recommendations_created = 0
        # ---- Call LLM with retry, heuristics on 3rd attempt ----
        MAX_LLM_ATTEMPTS = 3
        llm_response = None
        llm_error = None
        llm_latency = 0.0  # ← default so it's never undefined
        llm_start = time.monotonic()  # ← initialise before loop

        for llm_attempt in range(1, MAX_LLM_ATTEMPTS + 1):
            try:
                logger.info(
                    "[ANALYZE] LLM attempt %s/%s | provider=%s | run_id=%s",
                    llm_attempt, MAX_LLM_ATTEMPTS, provider.name, run_id,
                )
                llm_start = time.monotonic()
                # llm_response = provider.safe_complete(
                llm_response = provider.complete(
                    prompt=prompt,
                    system=SYSTEM_PROMPT,
                    temperature=0.3,
                    max_tokens=2048,
                    run_id=run_id,
                )
                llm_latency = round(time.monotonic() - llm_start, 3)

                if llm_response is not None:
                    logger.info(
                        "[ANALYZE] LLM succeeded | attempt=%s | latency=%.3fs | run_id=%s",
                        llm_attempt, llm_latency, run_id,
                    )
                    break

                logger.warning(
                    "[ANALYZE] LLM returned None | attempt=%s/%s | run_id=%s",
                    llm_attempt, MAX_LLM_ATTEMPTS, run_id,
                )

            except Exception as llm_err:
                llm_latency = round(time.monotonic() - llm_start, 3)  # safe now
                llm_error = str(llm_err)
                logger.warning(
                    "[ANALYZE] LLM attempt %s failed | error=%s | run_id=%s",
                    llm_attempt, llm_error, run_id,
                )

            if llm_attempt < MAX_LLM_ATTEMPTS:
                wait = 2 ** llm_attempt  # 2s, 4s
                logger.info("[ANALYZE] Waiting %ss before retry | run_id=%s", wait, run_id)
                time.sleep(wait)
            else:
                logger.warning(
                    "[ANALYZE] All %s LLM attempts failed — falling back to heuristics | run_id=%s",
                    MAX_LLM_ATTEMPTS, run_id,
                )
                logger.info(
                    "[ANALYZE] LLM response | received=%s | latency=%.3fs | run_id=%s",
                    bool(llm_response), llm_latency, run_id,
                )

        if llm_response is None:
            # LLM failed entirely — fall back to heuristics so run still completes
            logger.warning("[ANALYZE] LLM call failed, falling back to heuristics | run_id=%s", run_id)

            # ---- Trace: record LLM failure ----
            LLMRun.objects.create(
                audit_run       = run,
                batch           = batch,
                provider        = provider.name,
                model           = config.get("llm_model", ""),
                status          = LLMRun.Status.FAILED,
                error           = "safe_complete returned None — see worker logs for traceback",
                parse_status    = LLMRun.ParseStatus.SKIPPED,
                latency_seconds = llm_latency,
            )
            logger.info("[ANALYZE] LLMRun saved | status=failed | latency=%.3fs | run_id=%s", llm_latency, run_id)

            client_word_count = client_snapshot.extracted.get("word_count", 0)
            competitor_word_counts = [
                s.extracted.get("word_count", 0) for s in competitor_snapshots
            ]
            avg_competitor_wc = (
                sum(competitor_word_counts) / len(competitor_word_counts)
                if competitor_word_counts else 0
            )
            logger.info("[ANALYZE] Heuristics | client_wc=%s | avg_competitor_wc=%s", client_word_count, avg_competitor_wc)

            if content_gap > 200:
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
                logger.info("[ANALYZE] Heuristic rec created | action=content_expand")

            logger.info(f"[ANALYZE] Heuristic key word results:: {len(run.keyword_results.all())}")
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
                    logger.info("[ANALYZE] Heuristic rec created | action=ranking_improvement | keyword=%s | position=%s", kr.keyword, kr.client_position)
                else:
                    logger.info("[ANALYZE] Heuristic kr.client_position is not None or kr.client_position < 5 | position=%s", kr.client_position)

        else:
            logger.info("[ANALYZE] LLM response received | chars=%s | snippet=%s", len(llm_response.content), llm_response.content[:300])

            # ---- Parse LLM JSON response ----
            # Strip markdown fences if model wrapped it anyway
            raw_text = llm_response.content.strip()
            if raw_text.startswith("```"):
                raw_text = raw_text.split("```")[1]
                if raw_text.startswith("json"):
                    raw_text = raw_text[4:]
                raw_text = raw_text.strip()
            logger.info("[ANALYZE] Raw text after fence strip | chars=%s | snippet=%s", len(raw_text), raw_text[:300])

            parse_status = LLMRun.ParseStatus.OK
            parse_error  = ""
            recs         = []

            try:
                parsed = raw_text if isinstance(raw_text, dict) else json.loads(raw_text)

                # support both old list format and new {summary, recommendations} format
                if isinstance(parsed, list):
                    # handle both flat rec list AND [{summary, recommendations}] wrapper
                    if parsed and isinstance(parsed[0], dict) and "recommendations" in parsed[0]:
                        # LLM returned [{summary: ..., recommendations: [...]}]
                        summary = parsed[0].get("summary", "")
                        recs = parsed[0].get("recommendations", [])
                    else:
                        recs    = parsed
                        summary = ""
                elif isinstance(parsed, dict):
                    recs    = parsed.get("recommendations", [])
                    summary = parsed.get("summary", "")
                else:
                    raise ValueError(f"Unexpected LLM response type: {type(parsed)}")

                if not isinstance(recs, list):
                    raise ValueError("recommendations field is not a JSON array")

                logger.info("[ANALYZE] JSON parsed OK | recs=%s | summary_chars=%s", len(recs), len(summary))

            except Exception as parse_err:
                parse_status = LLMRun.ParseStatus.FAILED
                parse_error  = str(parse_err)
                logger.error(
                    "[ANALYZE] LLM JSON parse failed | run_id=%s | error=%s | raw=%s",
                    run_id, str(parse_err), raw_text[:300],
                )
                recs    = []
                summary = ""

            usage = llm_response.usage or {}

            # ---- Trace: record LLM success + parse outcome ----
            LLMRun.objects.create(
                audit_run         = run,
                batch             = batch,
                provider          = provider.name,
                model             = llm_response.model or "",
                status            = LLMRun.Status.SUCCESS,
                response_raw      = llm_response.content,
                response          = recs if recs else None,
                prompt_tokens     = usage.get("prompt_tokens"),
                completion_tokens = usage.get("completion_tokens"),
                total_tokens      = usage.get("total_tokens"),
                parse_status      = parse_status,
                parse_error       = parse_error,
                recs_parsed       = len(recs),
                latency_seconds   = llm_latency,
            )
            logger.info("[ANALYZE] LLMRun saved | status=success | parse=%s | recs=%s | latency=%.3fs | run_id=%s", parse_status, len(recs), llm_latency, run_id)
            priority_map = {
                "low": Recommendation.Priority.LOW,
                "med": Recommendation.Priority.MED,
                "high": Recommendation.Priority.HIGH,
            }

            for rec in recs:
                try:
                    Recommendation.objects.create(
                        audit_run=run,
                        keyword=rec.get("keyword"),
                        action_type=rec.get("action_type", "general"),
                        priority=priority_map.get(rec.get("priority", "med"), Recommendation.Priority.MED),
                        expected_impact=priority_map.get(rec.get("expected_impact", "med"), Recommendation.Priority.MED),
                        reason_text=rec.get("reason_text", ""),
                        evidence_refs=rec.get("evidence_refs", []),
                    )
                    recommendations_created += 1
                    logger.info("[ANALYZE] Rec saved | action=%s | keyword=%s | priority=%s", rec.get("action_type"), rec.get("keyword"), rec.get("priority"))
                except Exception as rec_err:
                    logger.warning("[ANALYZE] Failed to save recommendation | error=%s | rec=%s", str(rec_err), rec)

            logger.info("[ANALYZE] All recs saved | total=%s | run_id=%s", recommendations_created, run_id)

            # ---- Persist raw LLM output on the run for auditing ----
            AuditRun.objects.filter(id=run_id).update(
                ai_summary=llm_response.content,
                ai_meta={
                    "provider": provider.name,
                    "model": llm_response.model,
                    "usage": llm_response.usage,
                    "recs_raw": llm_response.content,  # keep raw for auditing
                },
            )
            logger.info("[ANALYZE] AuditRun ai_summary + ai_meta saved | run_id=%s", run_id)

        logger.info("[ANALYZE] Recommendations created | count=%s | run_id=%s", recommendations_created, run_id)

        _finish_success(step, attempt, meta={"recommendations": recommendations_created, "llm": provider.name})
        notify(
            run=run,
            event_type=Notification.EventType.STEP_SUCCESS,
            title="Analysis complete",
            body=f"Generated {recommendations_created} recommendations",
            meta={"step": "ANALYZE", "recommendations": recommendations_created},
        )
        return {"run_id": run_id, "step": "ANALYZE", "status": "success", "recommendations": recommendations_created}

    except Exception as e:
        logger.exception("[ANALYZE] Step FAILED | run_id=%s | error=%s", run_id, str(e))
        _finish_failed(step, attempt, str(e))

        if step.attempts >= 3: 
            logger.error("⛔ [ANALYZE] Max retries reached | run_id=%s", run_id)
            notify(
                run=run,
                event_type=Notification.EventType.STEP_FAILED,
                title=f"{step.step_name} failed",
                body=f"Step failed after {step.attempts} attempts. Error: {e}",
                meta={"step": step.step_name, "attempts": step.attempts, "error": str(e)},
            )
            raise 
        else:
            logger.warning("🔁 [ANALYZE] Retrying whole step | attempt=%s", step.attempts)
            raise self.retry(countdown=30)

   
@shared_task(name="apps.seo.tasks.steps.finalize_run",
    bind=True,
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    max_retries=3,
)
def finalize_run(self, run_id: str):
    logger.info("🏁 [FINALIZE] Step started | run_id=%s", run_id)

    step, attempt, info = _claim_step(run_id, RunStep.StepName.FINALIZE)

    logger.info(
        "🔒 [FINALIZE] Step claim | step=%s | attempt=%s | info=%s",
        str(step), str(attempt), str(info),
    )

    if step is None:
        logger.info("⏭️ [FINALIZE] Step already handled | run_id=%s | info=%s", run_id, info)
        return {"run_id": run_id, "step": "FINALIZE", **info}

    run = AuditRun.objects.get(id=run_id)
    try:
        logger.info("📥 [FINALIZE] Loading run | run_id=%s", run_id)
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
        run.status = AuditRun.Status.SUCCESS
        run.summary = summary
        run.finished_at = timezone.now()
        logger.info("⏱️ [FINALIZE] finished_at set | run_id=%s | finished_at=%s", run_id, str(run.finished_at))

        logger.info("💾 [FINALIZE] Saving AuditRun | run_id=%s", run_id)
        run.save(update_fields=["summary", "status", "finished_at"])
        
        logger.info("✅ [FINALIZE] AuditRun saved | run_id=%s", run_id)

        logger.info("🏷️ [FINALIZE] Marking step SUCCESS | run_id=%s", run_id)
        _finish_success(step, attempt, meta=summary)
        notify(
            run=run,
            event_type=Notification.EventType.RUN_COMPLETE,
            title="Audit complete",
            body=f"Your SEO audit for {run.client_site.url} is ready",
            meta=summary,
        )
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
        notify(
            run=run,
            event_type=Notification.EventType.RUN_FAILED,
            title="Audit failed",
            body=f"Your SEO audit for {run.client_site.url} could not be completed. Error: {str(e)}",
            meta={"step": "FINALIZE", "error": str(e)},
        )
        logger.info("🧨 [FINALIZE] Raising exception | run_id=%s", run_id)
        raise
