from __future__ import annotations
import json
import logging
from apps.seo.providers.llm.base import BaseLLMProvider, LLMResponse

logger = logging.getLogger(__name__)


class MockLLMProvider(BaseLLMProvider):
    """
    Mock provider for local dev / testing — no API key needed.
    Returns a hardcoded JSON recommendation list.
    """

    name = "mock"

    def complete(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 2048,
        **kwargs,
    ) -> LLMResponse:
        logger.info("[llm:mock] Returning mock recommendations")

        mock_payload = json.dumps([
            {
                "keyword": None,
                "action_type": "content_expand",
                "priority": "high",
                "expected_impact": "high",
                "reason_text": "Mock: client content is shorter than competitor average. Expand depth.",
                "evidence_refs": []
            },
            {
                "keyword": "example keyword",
                "action_type": "ranking_improvement",
                "priority": "med",
                "expected_impact": "high",
                "reason_text": "Mock: keyword not ranking in top 5. Improve on-page SEO.",
                "evidence_refs": []
            }
        ])

        return LLMResponse(
            content=mock_payload,
            raw={"mock": True},
            model="mock",
            usage={},
        )