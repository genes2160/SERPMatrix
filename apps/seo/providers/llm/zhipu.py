from __future__ import annotations
import logging
import requests
from apps.seo.providers.llm.base import BaseLLMProvider, LLMResponse

logger = logging.getLogger(__name__)

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"


class ZhipuProvider(BaseLLMProvider):
    """
    Zhipu AI provider.

    Env: ZHIPU_API_KEY

    Model examples:
      glm-4.7-flash
      glm-4
      glm-4-air
    """

    name = "zhipu"

    def __init__(
        self,
        api_key: str,
        model: str = "glm-4.7-flash",
        timeout: int = 60,
    ):
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

        logger.info(
            "[llm:zhipu] POST %s | model=%s | max_tokens=%s",
            API_URL,
            self.model,
            max_tokens,
        )

        data = {}

        try:
            resp = requests.post(
                API_URL,
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )

            if not resp.ok:
                logger.error(
                    "[llm:zhipu] HTTP %s | body=%s",
                    resp.status_code,
                    resp.text[:500],
                )
                resp.raise_for_status()

            data = resp.json()

            content = data["choices"][0]["message"]["content"] or ""
            usage = data.get("usage", {})

            logger.info(
                "[llm:zhipu] OK | chars=%s | usage=%s",
                len(content),
                usage,
            )

            return LLMResponse(
                content=content,
                raw=data,
                model=self.model,
                usage=usage,
            )

        except requests.exceptions.Timeout:
            logger.error("[llm:zhipu] Request timed out | timeout=%ss", self.timeout)
            raise

        except requests.exceptions.ConnectionError as e:
            logger.error("[llm:zhipu] Connection error | %s", str(e))
            raise

        except requests.exceptions.HTTPError as e:
            logger.error("[llm:zhipu] HTTP error | %s", str(e))
            raise

        except (KeyError, IndexError) as e:
            logger.error(
                "[llm:zhipu] Unexpected response shape | error=%s | data=%s",
                str(e),
                str(data)[:300],
            )
            raise

        except Exception as e:
            logger.exception("[llm:zhipu] Unexpected error | %s", str(e))
            raise