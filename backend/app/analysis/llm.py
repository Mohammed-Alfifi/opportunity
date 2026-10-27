"""طبقة موحدة لنماذج اللغة: anthropic | openai (أو أي خادم متوافق) | ollama (محلي)."""
from __future__ import annotations

import json
import re

import httpx

from ..config import settings


class LLMError(Exception):
    pass


def enabled() -> bool:
    return settings.llm_provider in {"anthropic", "openai", "ollama"} and bool(settings.llm_model)


def complete(system: str, prompt: str, max_tokens: int = 1500) -> str:
    p = settings.llm_provider
    try:
        with httpx.Client(timeout=120) as c:
            if p == "anthropic":
                r = c.post(
                    (settings.llm_base_url or "https://api.anthropic.com") + "/v1/messages",
                    headers={"x-api-key": settings.llm_api_key, "anthropic-version": "2023-06-01"},
                    json={"model": settings.llm_model, "max_tokens": max_tokens, "system": system,
                          "messages": [{"role": "user", "content": prompt}]},
                )
                r.raise_for_status()
                return "".join(b.get("text", "") for b in r.json().get("content", []))
            if p == "openai":
                r = c.post(
                    (settings.llm_base_url or "https://api.openai.com/v1") + "/chat/completions",
                    headers={"Authorization": f"Bearer {settings.llm_api_key}"},
                    json={"model": settings.llm_model, "max_tokens": max_tokens,
                          "messages": [{"role": "system", "content": system},
                                       {"role": "user", "content": prompt}]},
                )
                r.raise_for_status()
                return r.json()["choices"][0]["message"]["content"]
            if p == "ollama":
                r = c.post(
                    (settings.llm_base_url or "http://localhost:11434") + "/api/chat",
                    json={"model": settings.llm_model, "stream": False,
                          "messages": [{"role": "system", "content": system},
                                       {"role": "user", "content": prompt}]},
                )
                r.raise_for_status()
                return r.json()["message"]["content"]
    except httpx.HTTPStatusError as e:
        raise LLMError(f"خطأ من مزود النموذج ({e.response.status_code}): {e.response.text[:300]}") from e
    except (httpx.HTTPError, KeyError, ValueError) as e:
        raise LLMError(f"تعذر الاتصال بنموذج اللغة: {e}") from e
    raise LLMError("لم يتم ضبط LLM_PROVIDER")


def complete_json(system: str, prompt: str, max_tokens: int = 1500) -> dict:
    text = complete(system, prompt, max_tokens)
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise LLMError("النموذج لم يُرجع JSON")
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError as e:
        raise LLMError("JSON غير صالح من النموذج") from e
