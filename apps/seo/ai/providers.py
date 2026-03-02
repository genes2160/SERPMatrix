from __future__ import annotations

import json
import os
import time
import urllib.request
import urllib.error


class TransientAIError(Exception):
    """# NEW: triggers celery autoretry (rate limits, timeouts, 5xx)."""


class PermanentAIError(Exception):
    """# NEW: do not autoretry (bad key, invalid request, etc.)."""


class AIClient:
    def generate(self, *, messages: list[dict]) -> dict:
        raise NotImplementedError


def get_ai_client() -> AIClient:
    """
    # NEW:
    Switch via env/settings:
      AI_PROVIDER=openai|anthropic
    """
    provider = (os.getenv("AI_PROVIDER") or "openai").lower()
    if provider == "openai":
        return OpenAIHttpClient()
    if provider == "anthropic":
        return AnthropicHttpClient()
    raise PermanentAIError(f"Unknown AI_PROVIDER: {provider}")


class OpenAIHttpClient(AIClient):
    """
    # NEW:
    Minimal OpenAI REST call using urllib (no extra deps).
    Env:
      OPENAI_API_KEY
      OPENAI_MODEL (e.g. gpt-4.1-mini / gpt-4o-mini / etc)
      OPENAI_BASE_URL (optional)
    """
    def generate(self, *, messages: list[dict]) -> dict:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise PermanentAIError("Missing OPENAI_API_KEY")

        base_url = os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1"
        model = os.getenv("OPENAI_MODEL") or "gpt-4o-mini"

        body = {
            "model": model,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
        }

        req = urllib.request.Request(
            url=f"{base_url}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
                data = json.loads(raw)

            content = data["choices"][0]["message"]["content"]
            return json.loads(content)

        except urllib.error.HTTPError as e:
            status = getattr(e, "code", None)
            raw = e.read().decode("utf-8") if hasattr(e, "read") else ""
            # 429/5xx => retry
            if status in (429, 500, 502, 503, 504):
                raise TransientAIError(f"OpenAI HTTP {status}: {raw[:400]}")
            raise PermanentAIError(f"OpenAI HTTP {status}: {raw[:400]}")

        except urllib.error.URLError as e:
            raise TransientAIError(f"OpenAI network error: {str(e)[:400]}")

        except Exception as e:
            # parsing / unexpected
            raise PermanentAIError(f"OpenAI parse error: {str(e)[:400]}")


class AnthropicHttpClient(AIClient):
    """
    # NEW:
    Minimal Anthropic REST call using urllib.
    Env:
      ANTHROPIC_API_KEY
      ANTHROPIC_MODEL
    Note: This is a basic implementation pattern; adjust fields to your Anthropic API version.
    """
    def generate(self, *, messages: list[dict]) -> dict:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise PermanentAIError("Missing ANTHROPIC_API_KEY")

        model = os.getenv("ANTHROPIC_MODEL") or "claude-3-5-sonnet-latest"

        # Convert chat messages -> Anthropic style (simple)
        # Keep it minimal: concatenate user content.
        user_text = "\n".join([m["content"] for m in messages if m["role"] == "user"])
        system_text = "\n".join([m["content"] for m in messages if m["role"] == "system"])

        body = {
            "model": model,
            "max_tokens": 1200,
            "temperature": 0.2,
            "system": system_text,
            "messages": [{"role": "user", "content": user_text}],
        }

        req = urllib.request.Request(
            url="https://api.anthropic.com/v1/messages",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "x-api-key": api_key,
                "anthropic-version": os.getenv("ANTHROPIC_VERSION") or "2023-06-01",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
                data = json.loads(raw)

            # Anthropic returns content as a list of blocks; extract text
            blocks = data.get("content") or []
            text = ""
            for b in blocks:
                if b.get("type") == "text":
                    text += b.get("text", "")
            return json.loads(text)

        except urllib.error.HTTPError as e:
            status = getattr(e, "code", None)
            raw = e.read().decode("utf-8") if hasattr(e, "read") else ""
            if status in (429, 500, 502, 503, 504):
                raise TransientAIError(f"Anthropic HTTP {status}: {raw[:400]}")
            raise PermanentAIError(f"Anthropic HTTP {status}: {raw[:400]}")

        except urllib.error.URLError as e:
            raise TransientAIError(f"Anthropic network error: {str(e)[:400]}")

        except Exception as e:
            raise PermanentAIError(f"Anthropic parse error: {str(e)[:400]}")