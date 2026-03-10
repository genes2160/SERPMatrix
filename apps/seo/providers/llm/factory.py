from __future__ import annotations
import logging
from django.conf import settings
from apps.seo.providers.llm.base import BaseLLMProvider

logger = logging.getLogger(__name__)


def get_llm_provider(config: dict) -> BaseLLMProvider:
    """
    Resolves the correct LLM provider from run.config.

    config keys:
      llm_provider  : "openai" | "anthropic" | "grok" | "openrouter" | "mock"  (default: "mock")
      llm_model     : model string specific to the provider (optional, falls back to provider default)

    Examples in run.config:
      {"llm_provider": "openai",      "llm_model": "gpt-4o"}
      {"llm_provider": "anthropic",   "llm_model": "claude-3-5-sonnet-20241022"}
      {"llm_provider": "grok",        "llm_model": "grok-2"}
      {"llm_provider": "openrouter",  "llm_model": "mistralai/mistral-7b-instruct"}
      {"llm_provider": "mock"}
      {"llm_provider": "openai", "llm_model": "gpt-4o-mini"}

    {"llm_provider": "openrouter", "llm_model": "openai/gpt-4o-mini"}

    {"llm_provider": "grok", "llm_model": "grok-2-latest"}
    """

    provider_name = (config or {}).get("llm_provider", "mock")
    model = (config or {}).get("llm_model", None)  # None → provider uses its default

    logger.info("[llm:factory] Resolving provider | provider=%s | model=%s", provider_name, model)

    if provider_name == "openai":
        from apps.seo.providers.llm.openai import OpenAIProvider
        kwargs = {}
        if model:
            kwargs["model"] = model
        return OpenAIProvider(api_key=settings.OPENAI_API_KEY, **kwargs)

    if provider_name == "anthropic":
        from apps.seo.providers.llm.anthropic import AnthropicProvider
        kwargs = {}
        if model:
            kwargs["model"] = model
        return AnthropicProvider(api_key=settings.ANTHROPIC_API_KEY, **kwargs)

    if provider_name == "grok":
        from apps.seo.providers.llm.grok import GrokProvider
        kwargs = {}
        if model:
            kwargs["model"] = model
        return GrokProvider(api_key=settings.GROK_API_KEY, **kwargs)

    if provider_name == "openrouter":
        from apps.seo.providers.llm.openrouter import OpenRouterProvider
        kwargs = {}
        if model:
            kwargs["model"] = model
        return OpenRouterProvider(
            api_key=settings.OPENROUTER_API_KEY,
            site_url=getattr(settings, "OPENROUTER_SITE_URL", ""),
            site_name=getattr(settings, "OPENROUTER_SITE_NAME", ""),
            **kwargs,
        )

    # default / explicit mock
    if provider_name != "mock":
        logger.warning("[llm:factory] Unknown provider=%s — falling back to mock", provider_name)

    from apps.seo.providers.llm.mock import MockLLMProvider
    return MockLLMProvider()