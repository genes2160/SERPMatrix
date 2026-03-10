from __future__ import annotations
import logging
import requests
from apps.seo.providers.llm.base import BaseLLMProvider, LLMResponse

logger = logging.getLogger(__name__)

API_URL = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterProvider(BaseLLMProvider):
    """
    OpenRouter provider using plain requests — routes to any model.
    Env: OPENROUTER_API_KEY

    Model examples:
      openai/gpt-4o
      anthropic/claude-3.5-sonnet
      mistralai/mistral-7b-instruct
      meta-llama/llama-3.1-8b-instruct
    """

    name = "openrouter"

    def __init__(
        self,
        api_key: str,
        model: str = "openai/gpt-4o",
        site_url: str = "",
        site_name: str = "",
        timeout: int = 60,
    ):
        self.api_key = api_key
        self.model = model
        self.site_url = site_url
        self.site_name = site_name
        self.timeout = timeout

    def complete(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 2048,
        **kwargs,
    ) -> LLMResponse:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        # Optional: shown in OpenRouter dashboard
        if self.site_url:
            headers["HTTP-Referer"] = self.site_url
        if self.site_name:
            headers["X-Title"] = self.site_name

        logger.info("[llm:openrouter] POST %s | model=%s | max_tokens=%s", API_URL, self.model, max_tokens)

        data = {}
        try:
            resp = requests.post(API_URL, json=payload, headers=headers, timeout=self.timeout)

            if not resp.ok:
                logger.error(
                    "[llm:openrouter] HTTP %s | body=%s",
                    resp.status_code, resp.text[:500],
                )
                resp.raise_for_status()

            data = resp.json()
            content = data["choices"][0]["message"]["content"] or ""
            usage = data.get("usage", {})

            logger.info("[llm:openrouter] OK | chars=%s | usage=%s", len(content), usage)
            return LLMResponse(content=content, raw=data, model=self.model, usage=usage)

        except requests.exceptions.Timeout:
            logger.error("[llm:openrouter] Request timed out | timeout=%ss", self.timeout)
            raise

        except requests.exceptions.ConnectionError as e:
            logger.error("[llm:openrouter] Connection error | %s", str(e))
            raise

        except requests.exceptions.HTTPError as e:
            logger.error("[llm:openrouter] HTTP error | %s", str(e))
            raise

        except (KeyError, IndexError) as e:
            logger.error(
                "[llm:openrouter] Unexpected response shape | error=%s | data=%s",
                str(e), str(data)[:300],
            )
            raise

        except Exception as e:
            logger.exception("[llm:openrouter] Unexpected error | %s", str(e))
            raise