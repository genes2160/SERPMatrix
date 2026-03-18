from __future__ import annotations
import json
import logging

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------
# Token budget constants (conservative — works across all providers)
# Adjust if you move to a 128k context model
# ----------------------------------------------------------------
MAX_COMPETITORS = 8          # max competitor snapshots to include
MAX_KEYWORDS = 15            # max keyword results to include
MAX_TITLE_CHARS = 120        # truncate titles
MAX_H1_CHARS = 120           # truncate h1s
MAX_REASON_CHARS = 400       # truncate any existing reason text


SYSTEM_PROMPT = """You are a senior SEO strategist with deep expertise in technical SEO, content strategy, and competitive analysis.

You will receive structured data about a client website including:
- Client page metadata and content signals
- Competitor pages found in SERP results
- Keyword ranking positions for the client

Your task is to produce a prioritised, actionable list of SEO recommendations plus a brief summary.

RULES:
- Respond with a valid JSON object ONLY — no prose, no markdown fences, no explanation outside the JSON
- The object must have exactly these two keys:
  {
    "summary": "1-3 sentence plain English overview of the site's SEO health and biggest opportunities",
    "recommendations": [ ...array of recommendation objects... ]
  }
- Each recommendation must have exactly these fields:
  {
    "keyword": string or null,
    "action_type": string,
    "priority": "low" | "med" | "high",
    "expected_impact": "low" | "med" | "high",
    "reason_text": string,
    "evidence_refs": []
  }
- action_type must be one of: content_expand, title_fix, ranking_improvement, meta_description, internal_linking, backlink_gap, page_speed, structured_data, keyword_cannibalization, competitor_gap
- reason_text must be specific and reference actual data from the input (numbers, URLs, keywords)
- priority and expected_impact must reflect realistic SEO effort vs reward
- Produce between 3 and 10 recommendations — quality over quantity
- Do NOT invent data not present in the input
- Return STRICT valid JSON. No markdown. No commentary. No trailing commas.
- Do NOT invent data not present in the input
================================================
REQUIRED OUTPUT
================================================

Return ONLY valid JSON IN THE JSON LIST.

Rules:
- Output must be a JSON LIST
- One object per contact
- No markdown
- No commentary
- No text outside JSON
- Never omit required keys
- Use [] instead of null for arrays
- Return STRICT valid JSON LIST.
- Do NOT include comments.
- Do NOT include trailing commas.
- Arrays must contain values, not key:value pairs.
- If you include structured data, use objects inside arrays.
"""


def _truncate(value: str | None, max_chars: int) -> str | None:
    """Safely truncate a string field."""
    if not value:
        return value
    value = str(value).strip()
    if len(value) > max_chars:
        return value[:max_chars] + "…"
    return value


def _build_client_block(
    client_url: str,
    client_extracted: dict,
    geo: str = "",
    language: str = "",
    device: str = "",
) -> dict:
    return {
        "url": client_url,
        "geo": geo or "unknown",
        "language": language or "unknown",
        "device": device or "desktop",
        "title": _truncate(client_extracted.get("title"), MAX_TITLE_CHARS),
        "h1": _truncate(client_extracted.get("h1"), MAX_H1_CHARS),
        "word_count": client_extracted.get("word_count") or 0,
        "note": _truncate(client_extracted.get("note"), 200),
    }


def _build_competitor_blocks(competitor_snapshots: list[dict]) -> list[dict]:
    # Deduplicate by URL, cap at MAX_COMPETITORS
    seen = set()
    out = []

    for c in competitor_snapshots:
        url = (c.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)

        extracted = c.get("extracted") or {}
        out.append({
            "url": url,
            "title": _truncate(extracted.get("title"), MAX_TITLE_CHARS),
            "h1": _truncate(extracted.get("h1"), MAX_H1_CHARS),
            "word_count": extracted.get("word_count") or 0,
        })

        if len(out) >= MAX_COMPETITORS:
            logger.debug("[prompts] Competitor list capped at %s", MAX_COMPETITORS)
            break

    return out


def _build_keyword_blocks(keyword_results: list[dict]) -> list[dict]:
    # Sort: unranked first (None position), then by position ascending
    # Cap at MAX_KEYWORDS
    sorted_kws = sorted(
        keyword_results,
        key=lambda k: (k.get("position") is not None, k.get("position") or 999),
    )

    out = []
    for k in sorted_kws[:MAX_KEYWORDS]:
        kw = (k.get("keyword") or "").strip()
        if not kw:
            continue
        out.append({
            "keyword": kw,
            "client_position": k.get("position"),   # None = not ranking
            "top_competitor_domains": (k.get("competitors") or [])[:3],
        })

    if len(keyword_results) > MAX_KEYWORDS:
        logger.debug(
            "[prompts] Keyword list truncated from %s to %s",
            len(keyword_results), MAX_KEYWORDS,
        )

    return out


def build_analysis_prompt(
    client_url: str,
    client_extracted: dict,
    pre_analysis: dict,
    competitor_snapshots: list[dict],
    keyword_results: list[dict],
    geo: str = "",
    language: str = "",
    device: str = "",
) -> str:
    """
    Builds a token-efficient, production-grade prompt for LLM SEO analysis.

    - Truncates long text fields
    - Deduplicates competitors
    - Caps list sizes to avoid context window blowout
    - Includes geo/language/device context for accurate recommendations
    - Sorts keywords by priority (unranked first)
    """

    client_block = _build_client_block(
        client_url=client_url,
        client_extracted=client_extracted,
        geo=geo,
        language=language,
        device=device,
    )

    competitor_blocks = _build_competitor_blocks(competitor_snapshots)
    keyword_blocks = _build_keyword_blocks(keyword_results)

    logger.info(
        "[prompts] Built prompt | competitors=%s | keywords=%s",
        len(competitor_blocks), len(keyword_blocks),
    )
    # NEW: include pre-analysis block (VERY IMPORTANT)
    pre_analysis_block = pre_analysis or {}

    logger.info(
        "[prompts] Pre-analysis included | keys=%s",
        list(pre_analysis_block.keys())
    )
    # Use compact JSON (no indent) to save tokens
    prompt = (
        "Analyse the following SEO data and return a JSON object with summary and recommendations.\n\n"
        f"=== CLIENT SITE ===\n{json.dumps(client_block, separators=(',', ':'))}\n\n"
        f"=== PRE-ANALYSIS SIGNALS ===\n{json.dumps(pre_analysis_block, separators=(',', ':'))}\n\n"  # NEW
        f"=== COMPETITORS (top pages found in SERP) ===\n{json.dumps(competitor_blocks, separators=(',', ':'))}\n\n"
        f"=== KEYWORD RANKINGS ===\n{json.dumps(keyword_blocks, separators=(',', ':'))}\n\n"
        "Respond ONLY with valid JSON object containing summary and recommendations."
    )

    logger.debug("[prompts] Prompt length | chars=%s", len(prompt))

    return prompt