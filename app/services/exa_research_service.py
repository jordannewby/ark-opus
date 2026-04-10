"""
Exa Research API Service

Replaces the source verification + fact extraction + fact verification pipeline
with a single Exa Research API call that autonomously discovers, cross-references,
and returns verified facts from authoritative sources.
"""

import asyncio
import json
import logging
import time
from typing import Optional
from urllib.parse import urlparse

import httpx
from sqlalchemy.orm import Session

from ..models import FactCitation, VerifiedSource
from ..settings import (
    EXA_API_KEY,
    EXA_RESEARCH_TIMEOUT,
    EXA_RESEARCH_MODEL,
    EXA_RESEARCH_SUBMIT_RETRIES,
    EXA_RESEARCH_SUBMIT_BASE_DELAY,
    ORIGINAL_SOURCE_TRACING_ENABLED,
    ORIGINAL_SOURCE_MAX_LOOKUPS,
)
from ..domain_tiers import get_domain_tier_score
from .source_verification_service import detect_citation_laundering, KNOWN_RESEARCH_ORGS

logger = logging.getLogger(__name__)

_EXA_RESEARCH_URL = "https://api.exa.ai/research/v1"

# Schema for structured fact output from Research API
# Constraints: max 8 root fields, max depth 2, max 10 total properties
_OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["facts"],
    "properties": {
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["fact_text", "source_url", "source_title", "anchor", "fact_type"],
                "properties": {
                    "fact_text": {"type": "string"},
                    "source_url": {"type": "string"},
                    "source_title": {"type": "string"},
                    "anchor": {"type": "string"},
                    "fact_type": {
                        "type": "string",
                        "enum": ["statistic", "benchmark", "case_study", "expert_quote", "finding"],
                    },
                },
            },
        }
    },
}

# Map fact_type values from Research API to what writer/psychology expect
_FACT_TYPE_MAP = {
    "statistic": "statistic",
    "benchmark": "benchmark",
    "case_study": "case_study",
    "expert_quote": "expert_quote",
    "finding": "statistic",  # Map "finding" to existing enum value
}

# Map domain tier to credibility score
# Tier 0 gets 55.0 (above 45.0 threshold) because Research API already cross-referenced
_TIER_CREDIBILITY = {1: 85.0, 2: 72.0, 3: 58.0, 4: 50.0, 0: 55.0}


class ExaResearchError(Exception):
    """Raised when the Exa Research API fails, times out, or returns invalid data."""
    pass


def _extract_domain(url: str) -> str:
    """Extract domain from URL."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path.split("/")[0]
        if domain.startswith("www."):
            domain = domain[4:]
        return domain.lower()
    except Exception:
        return ""


def _build_instructions(keyword: str, niche: str) -> str:
    """Build Research API instructions string (max 4096 chars)."""
    niche_context = f' in the {niche} industry' if niche and niche != "default" else ""
    return (
        f'Find verified, data-backed factual claims about "{keyword}"{niche_context}. '
        f"CRITICAL: For every fact, the source_url MUST point to the ORIGINAL publisher — "
        f"not a blog or news site that quotes or summarizes it. "
        f"If a blog cites a Gartner report, return the Gartner URL, not the blog URL. "
        f"If the original is behind a paywall and only accessible via a third party, "
        f"return the third-party URL but note it in the source_title. "
        f"Focus on: statistics with exact percentages or dollar amounts from named "
        f"research firms (Gartner, Forrester, McKinsey, IDC, Deloitte, Ponemon, SANS), "
        f"benchmarks from industry reports, real case studies with named companies and "
        f"specific outcomes, and direct expert findings with attribution. "
        f"Prefer sources from the last 2 years. "
        f"Return 8-15 high-confidence facts with full source URLs."
    )


async def resolve_original_source(
    fact_text: str,
    claimed_org: str,
    canonical_domains: list,
) -> Optional[dict]:
    """
    Attempt to find the original source URL for a laundered citation.

    When Exa returns a fact like "Gartner reports 67%..." but the source_url is
    a third-party blog, this function searches Exa for the same fact constrained
    to the original publisher's domain(s).

    Returns: {"original_url": str, "original_title": str} or None
    Cost: 1 Exa /search call (~$0.001)
    """
    if not canonical_domains or not fact_text:
        return None

    try:
        from ..exa_client import exa_search

        # Extract key terms from the fact for a targeted search
        # Use first 200 chars to stay focused
        query = fact_text[:200]

        payload = {
            "query": query,
            "type": "neural",
            "numResults": 3,
            "includeDomains": canonical_domains,
        }

        result = await exa_search(payload, timeout=15)
        results = result.get("results", [])

        if results:
            best = results[0]
            original_url = best.get("url", "")
            original_title = best.get("title", "")
            if original_url:
                logger.info(
                    f"[SOURCE-TRACE] Resolved original source for '{claimed_org}': "
                    f"{original_url} (title: {original_title[:80]})"
                )
                return {"original_url": original_url, "original_title": original_title}

        logger.debug(f"[SOURCE-TRACE] No original source found for '{claimed_org}' on {canonical_domains}")
        return None

    except Exception as e:
        logger.warning(f"[SOURCE-TRACE] Failed to resolve original source for '{claimed_org}': {e}")
        return None


async def research_facts(
    keyword: str,
    niche: str,
    model: Optional[str] = None,
) -> dict:
    """
    Call Exa Research API to discover and verify facts for a keyword+niche.
    Submits async task, polls until completion, returns parsed facts.

    Args:
        keyword: SEO keyword to research
        niche: Industry niche (e.g., "cybersecurity", "default")
        model: Override Research API model (default: EXA_RESEARCH_MODEL)

    Returns:
        {
            "facts": [{"fact_text", "source_url", "source_title", "anchor", "fact_type"}],
            "research_id": str,
            "cost_dollars": float,
            "num_searches": int,
            "num_pages": int,
        }

    Raises:
        ExaResearchError: On timeout, API error, or invalid response
    """
    if not EXA_API_KEY:
        raise ExaResearchError("EXA_API_KEY is missing.")

    if model is None:
        model = EXA_RESEARCH_MODEL

    instructions = _build_instructions(keyword, niche)
    headers = {"x-api-key": EXA_API_KEY, "Content-Type": "application/json"}

    # Submit research task
    submit_payload = {
        "instructions": instructions,
        "model": model,
        "outputSchema": _OUTPUT_SCHEMA,
    }

    logger.info(f"[RESEARCH-API] Submitting research for '{keyword}' (niche: {niche}, model: {model})")

    submit_data = None
    for attempt in range(EXA_RESEARCH_SUBMIT_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(_EXA_RESEARCH_URL, headers=headers, json=submit_payload)
                resp.raise_for_status()
                submit_data = resp.json()
                break
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (429, 500, 502, 503) and attempt < EXA_RESEARCH_SUBMIT_RETRIES:
                delay = EXA_RESEARCH_SUBMIT_BASE_DELAY * (2 ** attempt)
                logger.warning(f"[RESEARCH-API] Submit attempt {attempt+1} failed ({e.response.status_code}), retrying in {delay}s")
                await asyncio.sleep(delay)
                continue
            raise ExaResearchError(f"Research API submit failed ({e.response.status_code}): {e.response.text[:200]}")
        except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError) as e:
            if attempt < EXA_RESEARCH_SUBMIT_RETRIES:
                delay = EXA_RESEARCH_SUBMIT_BASE_DELAY * (2 ** attempt)
                logger.warning(f"[RESEARCH-API] Submit attempt {attempt+1} failed ({e!r}), retrying in {delay}s")
                await asyncio.sleep(delay)
                continue
            raise ExaResearchError(f"Research API submit failed after {EXA_RESEARCH_SUBMIT_RETRIES} retries: {e!r}")
        except Exception as e:
            raise ExaResearchError(f"Research API submit failed: {e!r}")

    research_id = submit_data.get("researchId")
    if not research_id:
        raise ExaResearchError(f"No researchId in response: {submit_data}")

    logger.info(f"[RESEARCH-API] Task submitted: {research_id}")

    # Poll until completion
    completed_data = await _poll_research(research_id, timeout_seconds=EXA_RESEARCH_TIMEOUT)

    # Parse results
    cost_info = completed_data.get("costDollars", {})
    cost_dollars = cost_info.get("total", 0)
    num_searches = cost_info.get("numSearches", 0)
    num_pages = cost_info.get("numPages", 0)

    logger.info(
        f"[RESEARCH-API] Completed: {research_id} "
        f"(cost: ${cost_dollars:.3f}, searches: {num_searches}, pages: {num_pages})"
    )

    # Extract structured facts from output
    output = completed_data.get("output", {})
    facts = _parse_research_output(output)

    logger.info(f"[RESEARCH-API] Extracted {len(facts)} verified facts")

    return {
        "facts": facts,
        "research_id": research_id,
        "cost_dollars": cost_dollars,
        "num_searches": num_searches,
        "num_pages": num_pages,
    }


async def _poll_research(research_id: str, timeout_seconds: int = 120) -> dict:
    """Poll GET /research/v1/{researchId} until completed or failed."""
    poll_url = f"{_EXA_RESEARCH_URL}/{research_id}"
    headers = {"x-api-key": EXA_API_KEY}
    start = time.monotonic()
    interval = 3.0  # Start at 3s, back off to 10s max

    async with httpx.AsyncClient(timeout=15) as client:
        while (time.monotonic() - start) < timeout_seconds:
            try:
                resp = await client.get(poll_url, headers=headers)
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                logger.warning(f"[RESEARCH-API] Poll error (will retry): {e}")
                await asyncio.sleep(interval)
                interval = min(interval * 1.5, 10.0)
                continue

            status = data.get("status")
            if status == "completed":
                return data
            elif status in ("failed", "canceled"):
                error_msg = data.get("error", "unknown error")
                raise ExaResearchError(f"Research task {status}: {error_msg}")

            # Still pending/running — wait and retry
            elapsed = round(time.monotonic() - start, 1)
            logger.debug(f"[RESEARCH-API] Polling... status={status}, elapsed={elapsed}s")
            await asyncio.sleep(interval)
            interval = min(interval * 1.5, 10.0)

    raise ExaResearchError(f"Research task timed out after {timeout_seconds}s (id: {research_id})")


def _parse_research_output(output: dict) -> list[dict]:
    """Extract structured facts from Research API output."""
    # Try parsed JSON first (if outputSchema was honored)
    parsed = output.get("parsed")
    if parsed and isinstance(parsed, dict):
        facts = parsed.get("facts", [])
        if facts:
            return _validate_facts(facts)

    # Fallback: parse output.content as JSON
    content = output.get("content", "")
    if content:
        try:
            parsed_content = json.loads(content) if isinstance(content, str) else content
            if isinstance(parsed_content, dict):
                facts = parsed_content.get("facts", [])
                if facts:
                    return _validate_facts(facts)
        except (json.JSONDecodeError, TypeError):
            logger.warning("[RESEARCH-API] Could not parse output.content as JSON")

    logger.warning(f"[RESEARCH-API] No structured facts in output: {str(output)[:200]}")
    return []


def _validate_facts(facts: list) -> list[dict]:
    """Validate and clean facts from Research API output."""
    valid = []
    for fact in facts:
        if not isinstance(fact, dict):
            continue
        # Require minimum fields
        fact_text = fact.get("fact_text", "").strip()
        source_url = fact.get("source_url", "").strip()
        if not fact_text or not source_url:
            continue
        valid.append({
            "fact_text": fact_text,
            "source_url": source_url,
            "source_title": fact.get("source_title", "").strip() or "Unknown Source",
            "anchor": fact.get("anchor", "").strip() or fact_text[:50],
            "fact_type": fact.get("fact_type", "finding"),
        })
    return valid


async def create_citations_from_research(
    research_result: dict,
    research_run_id: int,
    profile_name: str,
    db: Session,
) -> dict:
    """
    Convert Exa Research API facts into VerifiedSource + FactCitation DB rows.
    Preserves the DB contract that writer_service.py and cross_reference_claims() depend on.

    Args:
        research_result: Output from research_facts()
        research_run_id: ID of the current research run
        profile_name: User profile name
        db: SQLAlchemy session

    Returns:
        {
            "verified_sources": list[VerifiedSource],
            "fact_citations": list[FactCitation],
            "fact_categories": dict,
        }
    """
    facts = research_result.get("facts", [])
    if not facts:
        logger.warning("[RESEARCH-API] No facts to store")
        return {
            "verified_sources": [],
            "fact_citations": [],
            "fact_categories": {"distribution": {}, "total_facts": 0, "dominant_type": "unknown",
                                "has_stats": False, "has_case_studies": False, "has_expert_quotes": False},
        }

    # Group facts by source URL
    facts_by_url: dict[str, list[dict]] = {}
    for fact in facts:
        url = fact["source_url"]
        facts_by_url.setdefault(url, []).append(fact)

    # Create VerifiedSource rows (one per unique URL)
    url_to_source: dict[str, VerifiedSource] = {}
    all_sources = []

    for url, url_facts in facts_by_url.items():
        domain = _extract_domain(url)
        tier_level, _ = get_domain_tier_score(domain)
        credibility = _TIER_CREDIBILITY.get(tier_level, 55.0)

        source = VerifiedSource(
            research_run_id=research_run_id,
            profile_name=profile_name,
            url=url,
            title=url_facts[0]["source_title"],
            domain=domain,
            credibility_score=credibility,
            domain_authority=None,
            publish_date=None,
            freshness_score=None,
            internal_citations_count=0,
            has_credible_citations=False,
            citation_urls_json="[]",
            is_academic=domain.endswith((".edu", ".ac.uk")),
            is_authoritative_domain=(tier_level in (1, 2)),
            content_snippet=None,
            verification_passed=True,
            rejection_reason=None,
        )
        db.add(source)
        db.flush()  # Get ID for FK
        url_to_source[url] = source
        all_sources.append(source)

    # Create FactCitation rows (one per fact) with citation laundering detection + original source tracing
    all_citations = []
    laundered_count = 0
    source_trace_lookups = 0

    for fact in facts:
        source = url_to_source[fact["source_url"]]
        tier_level, _ = get_domain_tier_score(source.domain)

        # Citation laundering check: flag "Gartner says X" from random-blog.com
        laundering = detect_citation_laundering(
            fact["fact_text"], source.domain, fact.get("anchor", "")
        )
        is_laundered = laundering.get("is_laundered", False)
        if is_laundered:
            laundered_count += 1
            logger.warning(
                f"[RESEARCH-API] Citation laundering detected: "
                f"'{fact['fact_text'][:80]}...' claims {laundering['claimed_org']} "
                f"but source is {source.domain}"
            )

            # Attempt to resolve to original source (e.g., find actual Gartner URL)
            if ORIGINAL_SOURCE_TRACING_ENABLED and source_trace_lookups < ORIGINAL_SOURCE_MAX_LOOKUPS:
                claimed_org = laundering.get("claimed_org", "")
                canonical_domains = KNOWN_RESEARCH_ORGS.get(claimed_org, [])
                if canonical_domains:
                    source_trace_lookups += 1
                    original = await resolve_original_source(
                        fact["fact_text"], claimed_org, canonical_domains
                    )
                    if original:
                        # Substitute URL and clear laundered flag
                        fact["source_url"] = original["original_url"]
                        fact["source_title"] = original["original_title"]
                        is_laundered = False
                        laundered_count -= 1
                        # Re-evaluate domain tier for the original source
                        new_domain = _extract_domain(original["original_url"])
                        tier_level, _ = get_domain_tier_score(new_domain)
                        logger.info(
                            f"[SOURCE-TRACE] Substituted original source: "
                            f"{source.domain} -> {new_domain} for '{claimed_org}'"
                        )

        # Tier-aware confidence: Tier 1-2 get higher confidence, unknown domains lower
        if is_laundered:
            confidence = 0.40  # Laundered citations are suspect
            verification_status = "suspect"
        elif tier_level in (1, 2):
            confidence = 0.90
            verification_status = "trusted"
        elif tier_level in (3, 4):
            confidence = 0.75
            verification_status = "corroborated"
        else:
            confidence = 0.60  # Unknown domain — Research API cross-referenced but unverified tier
            verification_status = "corroborated"

        credibility = source.credibility_score
        composite = (confidence * 100 + credibility) / 2

        fact_type = _FACT_TYPE_MAP.get(fact.get("fact_type", "finding"), "statistic")

        citation = FactCitation(
            verified_source_id=source.id,
            research_run_id=research_run_id,
            fact_text=fact["fact_text"],
            fact_type=fact_type,
            source_url=fact["source_url"],
            source_title=fact["source_title"],
            citation_anchor=fact["anchor"],
            confidence_score=confidence,
            source_credibility=credibility,
            composite_score=composite,
            is_grounded=not is_laundered,
            grounding_method="exa_research",
            is_verified=not is_laundered,
            verification_status=verification_status,
            consensus_count=1,
            corroboration_url=None,
        )
        db.add(citation)
        all_citations.append(citation)

    if laundered_count:
        logger.warning(f"[RESEARCH-API] {laundered_count}/{len(facts)} facts flagged as citation laundering")

    db.commit()

    # Build fact_categories dict for psychology agent
    fact_type_counts: dict[str, int] = {}
    for fc in all_citations:
        ft = fc.fact_type or "unknown"
        fact_type_counts[ft] = fact_type_counts.get(ft, 0) + 1

    fact_categories = {
        "distribution": fact_type_counts,
        "total_facts": len(all_citations),
        "dominant_type": max(fact_type_counts, key=fact_type_counts.get) if fact_type_counts else "unknown",
        "has_stats": fact_type_counts.get("statistic", 0) > 0,
        "has_case_studies": fact_type_counts.get("case_study", 0) > 0,
        "has_expert_quotes": fact_type_counts.get("expert_quote", 0) > 0,
    }

    logger.info(
        f"[RESEARCH-API] Stored {len(all_citations)} facts from "
        f"{len(all_sources)} sources (types: {fact_type_counts})"
    )

    return {
        "verified_sources": all_sources,
        "fact_citations": all_citations,
        "fact_categories": fact_categories,
    }
