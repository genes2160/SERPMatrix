from __future__ import annotations
import logging
import requests
from apps.seo.providers.llm.base import BaseLLMProvider, LLMResponse

logger = logging.getLogger(__name__)

API_URL = "https://api.jina.ai/v1/chat/completions"


class JinaProvider(BaseLLMProvider):
    """
    Jina AI LLM provider.

    Env: JINA_API_KEY

    Model examples:
      jina-chat
      jina-chat-v1
    """

    name = "jina"

    def __init__(
        self,
        api_key: str,
        model: str = "jina-chat",
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

        logger.info("[llm:jina] POST %s | model=%s", API_URL, self.model)

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
                    "[llm:jina] HTTP %s | body=%s",
                    resp.status_code,
                    resp.text[:500],
                )
                resp.raise_for_status()

            data = resp.json()

            content = data["choices"][0]["message"]["content"] or ""
            usage = data.get("usage", {})

            logger.info(
                "[llm:jina] OK | chars=%s | usage=%s",
                len(content),
                usage,
            )

            return LLMResponse(
                content=content,
                raw=data,
                model=self.model,
                usage=usage,
            )

        except Exception as e:
            logger.exception("[llm:jina] Unexpected error | %s", str(e))
            raise
        
if __name__ == "main":
    import os
    provider = JinaProvider(
        api_key=os.getenv("JINA_API_KEY"),
        model="jina-chat",
    )