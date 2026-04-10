"""
URL Liveness Validation Service

Async HEAD-first, GET-fallback validation for source URLs.
Runs at ingestion time (Phase 1 + Phase 1.5) to catch dead, redirected,
or fabricated URLs before they enter the pipeline.

Edge cases:
  - 403 (paywalled): treated as "live" — many authoritative sources (gartner.com,
    mckinsey.com) return 403 for direct access but the URL is valid.
  - 301/302 redirects: followed (httpx default). If final URL domain differs from
    original, the redirect is logged.
  - Timeouts: treated as "unknown" — URL is kept. Network transients should not
    block the pipeline.
"""

import asyncio
import logging
from urllib.parse import urlparse
from typing import Optional

import httpx

from ..settings import URL_VALIDATION_TIMEOUT, URL_VALIDATION_CONCURRENCY

logger = logging.getLogger(__name__)

_VALIDATION_SEM: Optional[asyncio.Semaphore] = None

# Status codes considered "live" — URL exists even if content is restricted
_LIVE_STATUS_CODES = set(range(200, 400)) | {403, 405, 429}


def _get_semaphore() -> asyncio.Semaphore:
    """Lazy-init semaphore (must be created inside an event loop)."""
    global _VALIDATION_SEM
    if _VALIDATION_SEM is None:
        _VALIDATION_SEM = asyncio.Semaphore(URL_VALIDATION_CONCURRENCY)
    return _VALIDATION_SEM


async def validate_url(
    url: str,
    timeout: Optional[int] = None,
) -> dict:
    """
    Check if a URL is live and accessible.

    Strategy: HEAD first (cheap), fallback to GET with stream=True (don't download body).

    Returns:
        {
            "url": str,           # original URL
            "is_live": bool,
            "final_url": str | None,   # after redirects
            "status_code": int | None,
            "redirected": bool,
            "error": str | None,
        }
    """
    timeout_s = timeout or URL_VALIDATION_TIMEOUT
    result = {
        "url": url,
        "is_live": False,
        "final_url": None,
        "status_code": None,
        "redirected": False,
        "error": None,
    }

    sem = _get_semaphore()
    async with sem:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_s),
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; ArkOpus/1.0; +https://arkopus.com)"},
        ) as client:
            # Try HEAD first (lightweight)
            try:
                resp = await client.head(url)
                result["status_code"] = resp.status_code
                result["final_url"] = str(resp.url)
                result["redirected"] = str(resp.url).rstrip("/") != url.rstrip("/")

                if resp.status_code in _LIVE_STATUS_CODES:
                    result["is_live"] = True
                    return result

                # Some servers reject HEAD — fall through to GET
                if resp.status_code == 405:
                    pass  # Method Not Allowed, try GET
                elif resp.status_code >= 400:
                    result["error"] = f"HEAD returned {resp.status_code}"
                    return result
            except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError):
                pass  # Fall through to GET
            except Exception as e:
                result["error"] = f"HEAD failed: {type(e).__name__}: {e}"
                # Fall through to GET as last resort

            # Fallback: GET with stream=True (don't download full body)
            try:
                async with client.stream("GET", url) as resp:
                    result["status_code"] = resp.status_code
                    result["final_url"] = str(resp.url)
                    result["redirected"] = str(resp.url).rstrip("/") != url.rstrip("/")
                    result["is_live"] = resp.status_code in _LIVE_STATUS_CODES

                    if not result["is_live"]:
                        result["error"] = f"GET returned {resp.status_code}"
            except httpx.TimeoutException:
                # Timeout = unknown, treat as live (don't block pipeline)
                result["is_live"] = True
                result["error"] = "Timeout (treated as live)"
            except (httpx.ConnectError, httpx.ReadError) as e:
                result["error"] = f"Connection failed: {type(e).__name__}"
            except Exception as e:
                result["error"] = f"GET failed: {type(e).__name__}: {e}"

    return result


async def batch_validate_urls(
    urls: list,
    timeout: Optional[int] = None,
) -> dict:
    """
    Validate multiple URLs concurrently with semaphore limiting.

    Returns: {url: validation_result}
    """
    if not urls:
        return {}

    tasks = [validate_url(url, timeout) for url in urls]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    validated = {}
    for url, result in zip(urls, results):
        if isinstance(result, Exception):
            logger.error(f"[URL-VALIDATE] Exception validating {url}: {result}")
            validated[url] = {
                "url": url,
                "is_live": True,  # Don't block on exceptions
                "final_url": None,
                "status_code": None,
                "redirected": False,
                "error": f"Exception: {result}",
            }
        else:
            validated[url] = result

    live_count = sum(1 for r in validated.values() if r["is_live"])
    dead_count = len(validated) - live_count
    logger.info(f"[URL-VALIDATE] Batch complete: {live_count} live, {dead_count} dead out of {len(urls)} URLs")

    return validated
