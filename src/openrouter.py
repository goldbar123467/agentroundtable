"""Thin OpenRouter chat client.

Keeps dependencies to `requests` + env-var config. No SDK.
"""

from __future__ import annotations

import os
import time
from typing import Iterable

import requests

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterError(RuntimeError):
    pass


def chat(
    model: str,
    messages: Iterable[dict],
    *,
    temperature: float = 0.5,
    max_tokens: int = 1600,
    timeout: float | None = None,
    retries: int = 3,
) -> str:
    """Call OpenRouter and return the assistant message text.

    Retries transient failures (5xx, 429, timeouts) with exponential backoff.
    Raises OpenRouterError on permanent failure.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise OpenRouterError("OPENROUTER_API_KEY is not set")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    referer = os.environ.get("OPENROUTER_REFERER")
    title = os.environ.get("OPENROUTER_TITLE")
    if referer:
        headers["HTTP-Referer"] = referer
    if title:
        headers["X-Title"] = title

    payload = {
        "model": model,
        "messages": list(messages),
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    http_timeout = timeout if timeout is not None else float(
        os.environ.get("HTTP_TIMEOUT", "120")
    )

    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            r = requests.post(
                OPENROUTER_URL,
                json=payload,
                headers=headers,
                timeout=http_timeout,
            )
            if r.status_code == 200:
                data = r.json()
                try:
                    return data["choices"][0]["message"]["content"] or ""
                except (KeyError, IndexError, TypeError) as e:
                    raise OpenRouterError(
                        f"Unexpected response shape from {model}: {data}"
                    ) from e
            if r.status_code in (429, 500, 502, 503, 504):
                last_err = OpenRouterError(
                    f"{model} HTTP {r.status_code}: {r.text[:400]}"
                )
                time.sleep(2 ** attempt)
                continue
            raise OpenRouterError(
                f"{model} HTTP {r.status_code}: {r.text[:800]}"
            )
        except requests.RequestException as e:
            last_err = e
            time.sleep(2 ** attempt)

    raise OpenRouterError(f"OpenRouter call failed after {retries} attempts: {last_err}")
