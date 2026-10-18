"""DeepSeek Search / Fetch web provider — user plugin.

Registers ``deepseek`` as a Hermes web backend using the raw JSON API at
https://api.deepseek.com/v1/tools/{search,fetch}.

Auth: same ``DEEPSEEK_API_KEY`` as the model API (Bearer).
Pricing: 5 CNY per 1,000 successful requests, per endpoint.
Rate limit: 5 QPS per account, search and fetch counted separately.
Extract returns Markdown only — the vendor has no HTML/text variant, so the
``format`` kwarg the tool forwards is ignored on purpose.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

import httpx

from agent.web_search_provider import WebSearchProvider, get_provider_env

logger = logging.getLogger(__name__)

BASE_URL = "https://api.deepseek.com/v1/tools"
_MISSING_KEY = (
    "DEEPSEEK_API_KEY not set. DeepSeek Search/Fetch reuses the model API key "
    "from https://platform.deepseek.com"
)
_TIMEOUT = 60.0
# Fetch is the slow leg (measured 0.2–11s per page). Two 45s attempts would let one
# page eat most of the tool's 120s whole-batch cap (web.extract_timeout), which
# replaces the ENTIRE batch with timeout entries and throws the good pages away.
_FETCH_TIMEOUT = 25.0
# ponytail: one worker per QPS slot. Raise only if DeepSeek lifts the 5 QPS cap.
_CONCURRENCY = 5


def _post(path: str, payload: Dict[str, Any], api_key: str, timeout: float = _TIMEOUT) -> Dict[str, Any]:
    """POST to one tools endpoint, retrying once on 408/429/5xx."""
    url = f"{BASE_URL}/{path}"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    last_error = ""
    for attempt in range(2):
        try:
            resp = httpx.post(url, json=payload, headers=headers, timeout=timeout)
            if resp.status_code in (408, 429) or resp.status_code >= 500:
                last_error = f"HTTP {resp.status_code}: {(resp.text or '').strip()[:200]}"
                if attempt == 0:
                    time.sleep(1.5)
                    continue
                raise ValueError(last_error)
            if resp.status_code >= 400:
                raise ValueError(f"HTTP {resp.status_code}: {(resp.text or '').strip()[:300]}")
            return resp.json()
        except httpx.HTTPError as exc:
            last_error = f"network error: {exc}"
            if attempt == 0:
                time.sleep(1.0)
                continue
            raise ValueError(last_error) from exc
    raise ValueError(last_error or "unknown error")


def _interrupt_requested() -> bool:
    """Single seam for the user's cancel request; overridable in the self-check."""
    try:
        from tools.interrupt import is_interrupted
    except Exception:  # stripped install — no interrupt surface to honour
        return False
    return is_interrupted()


class DeepSeekWebSearchProvider(WebSearchProvider):
    """DeepSeek 自研搜索引擎（search）+ 服务端抓取（fetch）。"""

    @property
    def name(self) -> str:
        return "deepseek"

    @property
    def display_name(self) -> str:
        return "DeepSeek Search / Fetch"

    def is_available(self) -> bool:
        # Cheap, no network — runs on every `hermes tools` paint.
        return bool(get_provider_env("DEEPSEEK_API_KEY"))

    def supports_search(self) -> bool:
        return True

    def supports_extract(self) -> bool:
        return True

    def search(self, query: str, limit: int = 5) -> Dict[str, Any]:
        api_key = get_provider_env("DEEPSEEK_API_KEY")
        if not api_key:
            return {"success": False, "error": _MISSING_KEY}
        count = max(1, min(int(limit or 5), 50))  # vendor serves up to 50 (verified)
        try:
            logger.info("DeepSeek search: '%s' (count=%d)", query, count)
            data = _post("search", {"query": query, "count": count}, api_key)
        except ValueError as exc:
            logger.warning("DeepSeek search failed: %s", exc)
            return {"success": False, "error": f"DeepSeek search failed: {exc}"}

        results = data.get("results") or []
        web = [
            {
                "title": item.get("title") or "",
                "url": item.get("url") or "",
                "description": item.get("summary") or item.get("snippet") or "",
                "position": idx + 1,
            }
            for idx, item in enumerate(results)
        ]
        return {"success": True, "data": {"web": web}}

    def extract(self, urls: List[str], **kwargs: Any) -> List[Dict[str, Any]]:
        """Fetch each URL concurrently; one bad page never fails the batch. Order follows ``urls``."""
        if not urls:
            return []
        api_key = get_provider_env("DEEPSEEK_API_KEY")
        if not api_key:
            return [{"url": u, "title": "", "content": "", "error": _MISSING_KEY} for u in urls]
        def _one(url: str) -> Dict[str, Any]:
            if _interrupt_requested():
                return {"url": url, "title": "", "content": "", "error": "Interrupted"}
            try:
                logger.info("DeepSeek fetch: %s", url)
                page = _post("fetch", {"url": url}, api_key, timeout=_FETCH_TIMEOUT)
            except Exception as exc:  # per-URL failure, never raise
                return {"url": url, "title": "", "content": "", "error": str(exc)}

            title = page.get("title") or ""
            content = page.get("content") or ""
            if not content:
                return {
                    "url": url,
                    "title": title,
                    "content": "",
                    "error": "DeepSeek returned no extractable Markdown body "
                    "(JS-rendered page or blocked by the target site)",
                }
            return {
                "url": url,
                "title": title,
                "content": content,
                "raw_content": content,
                "metadata": {"sourceURL": url, "title": title},
            }

        if len(urls) == 1:
            return [_one(urls[0])]
        with ThreadPoolExecutor(max_workers=min(_CONCURRENCY, len(urls))) as pool:
            return list(pool.map(_one, urls))  # map preserves input order

    def get_setup_schema(self) -> Optional[Dict[str, Any]]:
        return {
            "name": self.display_name,
            "env": ["DEEPSEEK_API_KEY"],
            "url": "https://platform.deepseek.com",
            "description": (
                "DeepSeek 自研搜索引擎 + 服务端网页抓取。同一把模型 API key，"
                "5 元 / 1000 次成功请求，各端点 5 QPS。服务端发起请求，"
                "不受本机 DNS / 代理干扰；但只抓静态 HTML —— 反爬站点"
                "（知乎 / X / NYT 实测）返回 404，且只输出 Markdown（无 HTML 版本）。"
            ),
        }


def _demo() -> None:  # offline self-check: no network, no key. Run: python provider.py
    prov = DeepSeekWebSearchProvider()
    G = globals()
    real_post, real_env = G["_post"], G["get_provider_env"]
    _real_interrupt = G["_interrupt_requested"]
    try:
        G["get_provider_env"] = lambda _n: ""
        assert prov.search("q")["success"] is False, "missing key must fail search"
        assert "DEEPSEEK_API_KEY" in prov.extract(["u1"])[0]["error"], "missing key must fail per URL"
    finally:
        G["get_provider_env"] = real_env

    fetched: List[str] = []

    def fake_post(path, payload, api_key, timeout=_TIMEOUT):
        if path == "search":
            assert timeout == _TIMEOUT, "search keeps the long timeout"
            return {
                "results": [
                    {"title": "t1", "url": "u1", "summary": "s1"},
                    {"title": "t2", "url": "u2", "snippet": "s2"},
                    {"url": "u3"},
                ]
            }
        assert timeout == _FETCH_TIMEOUT, "fetch uses the short timeout"
        fetched.append(payload["url"])
        if payload["url"] == "boom":
            raise ValueError("HTTP 404: blocked")
        if payload["url"] == "empty":
            return {"title": "e", "content": ""}
        return {"title": payload["url"], "content": f"body of {payload['url']}"}

    G["_post"] = fake_post
    try:
        hits = prov.search("q", limit=3)["data"]["web"]
        assert [h["position"] for h in hits] == [1, 2, 3], "position is 1-based in order"
        assert hits[1]["description"] == "s2", "description falls back to snippet"
        assert hits[2]["description"] == ""

        urls = ["u1", "boom", "empty", "u2"]
        out = prov.extract(urls, format="html")
        assert [o["url"] for o in out] == urls, "batch order must follow input"
        assert out[0]["content"] == "body of u1"
        assert out[0]["metadata"]["sourceURL"] == "u1", "cache keys off sourceURL"
        assert out[1]["error"] == "HTTP 404: blocked", "per-URL failure must not raise"
        assert out[2]["error"].startswith("DeepSeek returned no extractable")
        assert sorted(fetched) == sorted(urls), "every URL fetched exactly once"

        G["_interrupt_requested"] = lambda: True
        try:
            before = len(fetched)
            assert prov.extract(["a", "b"])[0]["error"] == "Interrupted"
            assert len(fetched) == before, "interrupted batch must not fetch"
        finally:
            G["_interrupt_requested"] = _real_interrupt
    finally:
        G["_post"] = real_post
    print("demo ok: search mapping, per-URL errors, order, timeouts, interrupt")


if __name__ == "__main__":
    _demo()
