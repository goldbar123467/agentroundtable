"""Thin Brave Search client.

Returns a compact list of {title, url, snippet} dicts ready to be formatted
into a debater dossier.
"""

from __future__ import annotations

import os
import time
from typing import Any

import requests

BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"


class BraveError(RuntimeError):
    pass


def search(query: str, *, count: int = 8, retries: int = 3) -> list[dict[str, str]]:
    api_key = os.environ.get("BRAVE_API_KEY")
    if not api_key:
        raise BraveError("BRAVE_API_KEY is not set")

    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": api_key,
    }
    params = {"q": query, "count": max(1, min(count, 20))}
    timeout = float(os.environ.get("HTTP_TIMEOUT", "60"))

    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            r = requests.get(BRAVE_URL, headers=headers, params=params, timeout=timeout)
            if r.status_code == 200:
                return _extract(r.json())
            if r.status_code in (429, 500, 502, 503, 504):
                last_err = BraveError(f"HTTP {r.status_code}: {r.text[:400]}")
                time.sleep(2 ** attempt)
                continue
            raise BraveError(f"HTTP {r.status_code}: {r.text[:400]}")
        except requests.RequestException as e:
            last_err = e
            time.sleep(2 ** attempt)

    raise BraveError(f"Brave call failed after {retries} attempts: {last_err}")


def _extract(data: dict[str, Any]) -> list[dict[str, str]]:
    results = (data.get("web") or {}).get("results") or []
    out = []
    for r in results:
        out.append(
            {
                "title": (r.get("title") or "").strip(),
                "url": (r.get("url") or "").strip(),
                "snippet": (r.get("description") or "").strip(),
            }
        )
    return out


def format_dossier(results: list[dict[str, str]], start_index: int = 1) -> str:
    """Render results as `[S#] title — url\\n   snippet` for prompt injection."""
    lines = []
    for i, r in enumerate(results, start=start_index):
        lines.append(f"[S{i}] {r['title']} — {r['url']}")
        if r["snippet"]:
            lines.append(f"    {r['snippet']}")
    return "\n".join(lines) if lines else "(no results)"
