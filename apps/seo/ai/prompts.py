from __future__ import annotations

import json


def build_seo_audit_messages(payload: dict) -> list[dict]:
    """
    # NEW:
    Optimized for: structured output, actionable SEO plan, low hallucination risk.
    Output MUST be JSON to allow deterministic storage.
    """
    schema = {
        "summary": "string (short, executive summary)",
        "recommendations": [
            {
                "title": "string",
                "priority": "HIGH|MED|LOW",
                "expected_impact": "HIGH|MED|LOW",
                "action_type": "string (e.g. content, technical, serp, local-seo, internal-links)",
                "reason": "string",
                "actions": ["string", "string"],
                "evidence_refs": ["string"],
            }
        ],
        "meta": {
            "confidence": "0..1",
            "notes": "string",
        },
    }

    system = (
        "You are a senior SEO strategist. "
        "You will receive structured audit signals (no raw HTML). "
        "Return ONLY valid JSON matching the given schema. "
        "Do not include markdown, backticks, or extra commentary."
    )

    user = {
        "task": "Analyze this SEO audit data and produce a clear summary + prioritized actions.",
        "rules": [
            "Be specific and actionable (titles/H1/content gaps/internal links/technical).",
            "If data is missing, state assumptions in meta.notes.",
            "Keep summary concise; keep recommendations practical.",
            "No fabricated metrics. Use only provided signals.",
        ],
        "output_schema": schema,
        "payload": payload,
    }

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
    ]