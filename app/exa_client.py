"""
Exa API Client with Rate Limiting + Retry Logic

Provides centralized wrappers for all Exa API calls with:
- Layer 1 (Proactive): Per-endpoint semaphores to stay under QPS limits
- Layer 2 (Proactive): Inter-request delay for /search to sustain ~8 QPS
- Layer 3 (Reactive): Exponential backoff retry on 429 and network errors

Exa rate limits:
- /search: 10 QPS
- /findSimilar: 10 QPS
- /contents: 100 QPS
"""

import asyncio
import logging
import time
from typing import Optional

import httpx

from .settings import (
    EXA_API_KEY,
    EXA_TIMEOUT,
    EXA_SEARCH_CONCURRENCY,
    EXA_CONTENTS_CONCURRENCY,
    EXA_MAX_RETRIES,
    EXA_RETRY_BASE_DELAY,
    EXA_INTER_REQUEST_DELAY,
)

logger = logging.getLogger(__name__)

# Per-endpoint semaphores
_SEARCH_SEM = asyncio.Semaphore(EXA_SEARCH_CONCURRENCY)
_CONTENTS_SEM = asyncio.Semaphore(EXA_CONTENTS_CONCURRENCY)

# Inter-request delay tracking for /search (shared with /findSimilar)
_search_delay_lock = asyncio.Lock()
_last_search_time = 0.0

_EXA_BASE = "https://api.exa.ai"


async def _call_exa(
    endpoint: str,
    payload: dict,
    semaphore: asyncio.Semaphore,
    enforce_delay: bool = False,
    max_retries: Optional[int] = None,
    timeout: Optional[int] = None,
) -> dict:
    """
    Internal: rate-limited Exa API call with retry.

    Args:
        endpoint: Exa endpoint path (e.g., "/search", "/contents", "/findSimilar")
        payload: Request JSON body
        semaphore: Per-endpoint concurrency limiter
        enforce_delay: If True, enforce inter-request delay (for /search endpoints)
        max_retries: Override default retry count
        timeout: Override default timeout
    """
    global _last_search_time

    if max_retries is None:
        max_retries = EXA_MAX_RETRIES
    if timeout is None:
        timeout = EXA_TIMEOUT

    if not EXA_API_KEY:
        raise ValueError("EXA_API_KEY is missing.")

    headers = {
        "x-api-key": EXA_API_KEY,
        "Content-Type": "application/json",
    }

    url = f"{_EXA_BASE}{endpoint}"

    async with semaphore:
        # Enforce inter-request delay for search endpoints
        if enforce_delay:
            async with _search_delay_lock:
                elapsed = time.monotonic() - _last_search_time
                if elapsed < EXA_INTER_REQUEST_DELAY:
                    await asyncio.sleep(EXA_INTER_REQUEST_DELAY - elapsed)
                _last_search_time = time.monotonic()

        for attempt in range(max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.post(url, headers=headers, json=payload)
                    resp.raise_for_status()
                    return resp.json()

            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                is_retryable = (
                    status in (429, 500, 502, 503)
                    or "rate limit" in str(e).lower()
                    or "too many requests" in str(e).lower()
                )

                if is_retryable and attempt < max_retries:
                    delay = EXA_RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning(
                        f"[EXA-RETRY] HTTP {status} on {endpoint}, retrying in {delay}s "
                        f"(attempt {attempt + 1}/{max_retries})"
                    )
                    await asyncio.sleep(delay)
                    continue

                raise

            except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError) as e:
                if attempt < max_retries:
                    delay = EXA_RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning(
                        f"[EXA-RETRY] Network error on {endpoint} ({type(e).__name__}), "
                        f"retrying in {delay}s (attempt {attempt + 1}/{max_retries})"
                    )
                    await asyncio.sleep(delay)
                    continue

                raise

            except Exception as e:
                logger.error(f"[EXA] Unexpected error on {endpoint}: {e}")
                raise

    raise RuntimeError(f"Exa {endpoint} call failed after {max_retries} retries")


async def exa_search(payload: dict, timeout: Optional[int] = None) -> dict:
    """
    Rate-limited Exa /search call.

    Semaphore(8) + 0.12s inter-request delay + retry on 429/network errors.

    Args:
        payload: Full search request body (query, type, num_results, etc.)
        timeout: Override default timeout in seconds

    Returns:
        Parsed JSON response from Exa /search
    """
    return await _call_exa(
        endpoint="/search",
        payload=payload,
        semaphore=_SEARCH_SEM,
        enforce_delay=True,
        timeout=timeout,
    )


async def exa_contents(payload: dict, timeout: Optional[int] = None) -> dict:
    """
    Rate-limited Exa /contents call.

    Semaphore(20) + retry on 429/network errors. No inter-request delay
    (100 QPS limit is generous).

    Args:
        payload: Full contents request body (ids, text, etc.)
        timeout: Override default timeout in seconds

    Returns:
        Parsed JSON response from Exa /contents
    """
    return await _call_exa(
        endpoint="/contents",
        payload=payload,
        semaphore=_CONTENTS_SEM,
        enforce_delay=False,
        timeout=timeout,
    )


async def exa_find_similar(payload: dict, timeout: Optional[int] = None) -> dict:
    """
    Rate-limited Exa /findSimilar call.

    Shares the /search semaphore and delay (same 10 QPS limit).

    Args:
        payload: Full findSimilar request body (url, num_results, etc.)
        timeout: Override default timeout in seconds

    Returns:
        Parsed JSON response from Exa /findSimilar
    """
    return await _call_exa(
        endpoint="/findSimilar",
        payload=payload,
        semaphore=_SEARCH_SEM,
        enforce_delay=True,
        timeout=timeout,
    )
