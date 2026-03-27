"""
GLM-5 API Client with Retry Logic

Provides a wrapper for GLM-5 API calls with exponential backoff retry logic
to handle rate limiting (429) and transient network errors.
"""

import asyncio
import logging
from typing import Optional

import httpx

from .settings import (
    ZAI_API_KEY,
    GLM5_API_URL,
    GLM5_TIMEOUT,
    GLM5_MAX_RETRIES,
    GLM5_RETRY_BASE_DELAY,
    GLM5_CONCURRENCY_LIMIT,
)

logger = logging.getLogger(__name__)

# Module-level semaphore to enforce GLM-5's concurrency limit of 2 simultaneous requests
GLM_SEMAPHORE = asyncio.Semaphore(GLM5_CONCURRENCY_LIMIT)


async def call_glm5_with_retry(
    payload: dict,
    max_retries: Optional[int] = None,
    timeout: Optional[int] = None,
) -> dict:
    """
    Call GLM-5 API with concurrency limiting and exponential backoff retry logic.

    Dual-layer protection:
    - Layer 1 (Proactive): Semaphore limits to 2 concurrent requests (prevents 429s)
    - Layer 2 (Reactive): Exponential backoff retries on transient errors

    Automatically retries on:
    - 429 rate limit errors
    - Network timeouts and connection errors

    Args:
        payload: Full API request payload (model, messages, temperature, etc.)
        max_retries: Maximum retry attempts (default: GLM5_MAX_RETRIES from settings)
        timeout: Request timeout in seconds (default: GLM5_TIMEOUT from settings)

    Returns:
        Parsed JSON response from GLM-5 API

    Raises:
        httpx.HTTPStatusError: On non-retryable HTTP errors or after exhausting retries
        Exception: On non-retryable errors or after exhausting retries
    """
    if max_retries is None:
        max_retries = GLM5_MAX_RETRIES
    if timeout is None:
        timeout = GLM5_TIMEOUT

    if not ZAI_API_KEY:
        raise ValueError("ZAI_API_KEY is missing.")

    headers = {
        "Authorization": f"Bearer {ZAI_API_KEY}",
        "Content-Type": "application/json",
        "Accept-Language": "en-US,en"
    }

    # Semaphore ensures max 2 concurrent GLM calls (GLM-5 API limit)
    async with GLM_SEMAPHORE:
        for attempt in range(max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.post(GLM5_API_URL, headers=headers, json=payload)
                    resp.raise_for_status()
                    return resp.json()

            except httpx.HTTPStatusError as e:
                # Check if it's a 429 rate limit error
                is_rate_limit = (
                    e.response.status_code == 429 or
                    "429" in str(e).lower() or
                    "rate limit" in str(e).lower() or
                    "too many requests" in str(e).lower()
                )

                if is_rate_limit and attempt < max_retries:
                    delay = GLM5_RETRY_BASE_DELAY * (2 ** attempt)  # 1s, 2s, 4s
                    logger.warning(
                        f"[GLM-5-RETRY] 429 rate limit, retrying in {delay}s "
                        f"(attempt {attempt + 1}/{max_retries})"
                    )
                    await asyncio.sleep(delay)
                    continue

                # Non-429 error or exhausted retries
                raise

            except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError) as e:
                # Retry on network errors
                if attempt < max_retries:
                    delay = GLM5_RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning(
                        f"[GLM-5-RETRY] Network error ({type(e).__name__}), retrying in {delay}s "
                        f"(attempt {attempt + 1}/{max_retries})"
                    )
                    await asyncio.sleep(delay)
                    continue

                # Exhausted retries
                raise

            except Exception as e:
                # Unexpected error - don't retry
                logger.error(f"[GLM-5] Unexpected error: {e}")
                raise

        # Should never reach here, but just in case
        raise RuntimeError(f"GLM-5 call failed after {max_retries} retries")
