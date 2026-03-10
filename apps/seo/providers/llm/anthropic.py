from __future__ import annotations
import logging
import requests
from apps.seo.providers.llm.base import BaseLLMProvider, LLMResponse

logger = logging.getLogger(__name__)

API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


class AnthropicProvider(BaseLLMProvider):
    """
    Anthropic provider using plain requests.
    Env: ANTHROPIC_API_KEY
    Models: claude-3-5-sonnet-20241022, claude-3-opus-20240229, claude-3-haiku-20240307, etc.
    """

    name = "anthropic"

    def __init__(self, api_key: str, model: str = "claude-3-5-sonnet-20241022", timeout: int = 60):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def complete(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 2048,
        **kwargs,
    ) -> LLMResponse:
        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }

        if system:
            payload["system"] = system

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "Content-Type": "application/json",
        }

        logger.info("[llm:anthropic] POST %s | model=%s | max_tokens=%s", API_URL, self.model, max_tokens)

        data = {}
        try:
            resp = requests.post(API_URL, json=payload, headers=headers, timeout=self.timeout)

            if not resp.ok:
                logger.error(
                    "[llm:anthropic] HTTP %s | body=%s",
                    resp.status_code, resp.text[:500],
                )
                resp.raise_for_status()

            data = resp.json()
            content = data["content"][0]["text"] if data.get("content") else ""
            usage = data.get("usage", {})

            logger.info("[llm:anthropic] OK | chars=%s | usage=%s", len(content), usage)
            return LLMResponse(content=content, raw=data, model=self.model, usage=usage)

        except requests.exceptions.Timeout:
            logger.error("[llm:anthropic] Request timed out | timeout=%ss", self.timeout)
            raise

        except requests.exceptions.ConnectionError as e:
            logger.error("[llm:anthropic] Connection error | %s", str(e))
            raise

        except requests.exceptions.HTTPError as e:
            logger.error("[llm:anthropic] HTTP error | %s", str(e))
            raise

        except (KeyError, IndexError) as e:
            logger.error(
                "[llm:anthropic] Unexpected response shape | error=%s | data=%s",
                str(e), str(data)[:300],
            )
            raise

        except Exception as e:
            logger.exception("[llm:anthropic] Unexpected error | %s", str(e))
            raise