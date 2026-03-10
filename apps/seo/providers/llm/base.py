from __future__ import annotations
import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class LLMResponse:
    """Normalised response from any LLM provider."""

    def __init__(self, content: str, raw: Any = None, model: str = "", usage: dict | None = None):
        self.content = content          # raw text from model
        self.raw = raw                  # full provider response (for ai_meta)
        self.model = model
        self.usage = usage or {}

    def __repr__(self):
        return f"<LLMResponse model={self.model} chars={len(self.content)}>"


class BaseLLMProvider(ABC):
    """
    All LLM providers must implement this interface.
    One method: complete(prompt, system, **kwargs) -> LLMResponse
    """

    name: str = "base"

    @abstractmethod
    def complete(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 2048,
        **kwargs,
    ) -> LLMResponse:
        ...

    def safe_complete(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 2048,
        **kwargs,
    ) -> LLMResponse | None:
        """
        Wraps complete() with catch-all so callers never crash on provider failure.
        Returns None on error.
        """
        try:
            return self.complete(prompt, system=system, temperature=temperature, max_tokens=max_tokens, **kwargs)
        except Exception as e:
            logger.exception("[llm:%s] safe_complete failed | error=%s", self.name, str(e))
            return None