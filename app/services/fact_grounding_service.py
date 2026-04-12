"""
Fact Grounding Agent — Phase 1.7 Pre-Writer Source Verification

Verifies Exa Research API facts against actual source page content before
they enter the writer's citation pool. Replaces the self-fulfilling loop
where fact_text was stored as "source content" and verified against itself.

Pipeline position: After Phase 1.5 (Exa Research), before Phase 2 (Psychology).

Steps:
  1. Fetch real page content via Exa /contents
  2. GLM-5 AI Analyst verifies each fact against real content
  3. Filter rejected facts, enrich survivors with exact quotes + full context
  4. Trace secondary citations to primary sources
  5. Check version currency for versioned documents
  6. Tag conflatable facts with methodology context
"""

import asyncio
import json
import logging
import re
from urllib.parse import urlparse, urlunparse

from sqlalchemy.orm import Session

from ..exa_client import exa_contents, exa_search
from ..glm_client import call_glm5_with_retry
from ..security import sanitize_external_content
from ..domain_tiers import get_domain_tier_score
from ..settings import (
    FACT_GROUNDING_CONTENT_MAX_CHARS,
    FACT_GROUNDING_CORROBORATION_ENABLED,
    FACT_GROUNDING_GLM5_TEMPERATURE,
    FACT_GROUNDING_MAX_CORROBORATION_SEARCHES,
    FACT_GROUNDING_MAX_PRIMARY_LOOKUPS,
    FACT_GROUNDING_VERSION_CURRENCY_MAX,
    GLM5_MODEL,
)
from .source_verification_service import KNOWN_RESEARCH_ORGS, score_fact_consensus

logger = logging.getLogger(__name__)


# --- Step 1: Fetch Real Source Content ---

async def _fetch_source_content(source_urls: list[str]) -> dict[str, str]:
    """
    Batch-fetch actual page content for Exa source URLs via /contents endpoint.

    Returns: {url: clean_text} for successfully fetched pages.
    Cost: ~$0.005-0.008 per article (5-8 URLs in one batched call)
    """
    if not source_urls:
        return {}

    # Deduplicate
    unique_urls = list(set(source_urls))
    logger.info(
        f"[FACT-GROUND] Step 1: Fetching real content for {len(unique_urls)} source URLs"
    )

    try:
        payload = {
            "ids": unique_urls,
            "text": {"maxCharacters": FACT_GROUNDING_CONTENT_MAX_CHARS},
        }
        result = await exa_contents(payload, timeout=30)
        results = result.get("results", [])

        content_map = {}
        for item in results:
            url = item.get("url", "")
            text = item.get("text", "")
            if url and text and len(text.strip()) > 100:
                stripped = text.strip()
                content_map[_normalize_url_key(url)] = stripped
                if len(stripped) >= FACT_GROUNDING_CONTENT_MAX_CHARS - 100:
                    logger.warning(
                        f"[FACT-GROUND] Source content near/at max chars "
                        f"({len(stripped)}/{FACT_GROUNDING_CONTENT_MAX_CHARS}) "
                        f"for {url[:80]} — facts beyond truncation point may "
                        f"be falsely rejected"
                    )

        fetched = len(content_map)
        missed = len(unique_urls) - fetched
        if missed:
            logger.warning(
                f"[FACT-GROUND] Exa /contents returned no usable content for "
                f"{missed}/{len(unique_urls)} URLs"
            )
        logger.info(
            f"[FACT-GROUND] Step 1 complete: {fetched}/{len(unique_urls)} sources fetched"
        )
        return content_map

    except Exception as e:
        logger.error(f"[FACT-GROUND] Step 1 failed (Exa /contents): {e}")
        return {}


# --- Step 2: GLM-5 AI Analyst ---

_VERIFICATION_PROMPT_TEMPLATE = """You are a senior research analyst. You have the ACTUAL CONTENT of a source page and CLAIMS that were reportedly extracted from it. Your job: read the page and verify each claim like a human fact-checker would.

SOURCE: {title}
URL: {url}

ACTUAL PAGE CONTENT:
{content}

CLAIMS ATTRIBUTED TO THIS SOURCE:
{claims_block}

For each claim, determine:

1. PRESENT — Is this specific claim actually stated on this page?
   If yes: provide the EXACT VERBATIM QUOTE from the page that contains this data point. Copy the sentence or passage word-for-word.
   If no: mark as not_found. Do not guess or infer — if the exact number is not on this page, it is not present.

2. COMPLETE — Does the claim include the full context from the source?
   - List any qualifying words in the source but MISSING from the claim (e.g., "enterprise," "custom-built," "at any level").
   - Note any conditional distinctions the claim omits (e.g., source says "92% at any level, 47% very concerned" but claim only states 92%).
   - Note methodology context (sample size, time period, geographic scope).

3. PRIMARY — Is this page the ORIGINAL source of the data, or does it attribute the data to another study, report, organization, or researcher?
   Look for phrases like "according to [Name]," "[Study] found," "[Org] reports," "[Author] et al." If found, name the primary source.

4. VERSION — Is a specific version, edition, or year mentioned for this data?
   (e.g., "v5," "E2023," "2025 edition," "FY2024," "third annual")

Return JSON:
{{
  "verifications": [
    {{
      "claim_index": 0,
      "present": true,
      "exact_quote": "verbatim text from page",
      "missing_qualifiers": ["enterprise", "custom-built"],
      "missing_context": "description of omitted context",
      "methodology_note": "survey of 500 CISOs",
      "is_secondary_citation": false,
      "primary_source_name": null,
      "version_info": null
    }}
  ]
}}"""


async def _verify_facts_against_source(
    source_url: str,
    source_title: str,
    source_content: str,
    claimed_facts: list[dict],
) -> list[dict]:
    """
    GLM-5 with deep thinking reads the actual source page and verifies
    each claimed fact. One call per source URL, queued through GLM_SEMAPHORE.

    Returns list of verification dicts (one per claimed fact).
    Cost: ~$0.0001 per source
    """
    if not claimed_facts or not source_content:
        return []

    # Build numbered claims block
    claims_lines = []
    for i, fact in enumerate(claimed_facts):
        claims_lines.append(f'{i}. "{fact.get("fact_text", "")}"')
    claims_block = "\n".join(claims_lines)

    # Sanitize external content per security rules
    safe_content = sanitize_external_content(
        source_content, max_chars=FACT_GROUNDING_CONTENT_MAX_CHARS
    )

    prompt = _VERIFICATION_PROMPT_TEMPLATE.format(
        title=sanitize_external_content(source_title, max_chars=200),
        url=sanitize_external_content(source_url, max_chars=500),
        content=safe_content,
        claims_block=sanitize_external_content(claims_block, max_chars=3000),
    )

    payload = {
        "model": GLM5_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "You are a fact verification specialist. Output valid JSON ONLY.",
            },
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
        "temperature": FACT_GROUNDING_GLM5_TEMPERATURE,
        "thinking": {"type": "enabled"},
    }

    try:
        data = await call_glm5_with_retry(payload)
        content_text = (
            data.get("choices", [{}])[0].get("message", {}).get("content", "")
        )
        parsed = json.loads(content_text) if content_text else {}
        verifications = parsed.get("verifications", [])

        logger.info(
            f"[FACT-GROUND] Step 2: Verified {len(verifications)} claims "
            f"against {source_url[:80]}"
        )
        return verifications

    except (json.JSONDecodeError, KeyError, IndexError) as e:
        logger.error(
            f"[FACT-GROUND] Step 2: GLM-5 response parse error for "
            f"{source_url[:80]}: {e}"
        )
        return []
    except Exception as e:
        logger.error(
            f"[FACT-GROUND] Step 2: GLM-5 verification failed for "
            f"{source_url[:80]}: {e}"
        )
        return []


# --- Step 3: Filter and Enrich ---

def _apply_verification_results(
    facts: list[dict],
    fact_citations: list,
    verification_map: dict[str, list[dict]],
    source_content_map: dict[str, str],
) -> dict:
    """
    Apply GLM-5 verification results to FactCitation records.

    - Reject facts where present=false
    - Enrich survivors with exact_quote and full context
    - Tag secondary citations and version info for Steps 4-5

    Returns: {
        verified_citations: list[FactCitation],
        rejected: list[dict],
        enriched_count: int,
        secondary_facts: list[tuple[FactCitation, dict]],
        versioned_facts: list[tuple[FactCitation, dict]],
    }
    """
    verified = []
    rejected = []
    enriched_count = 0
    secondary_facts = []
    versioned_facts = []

    # Build normalized URL -> facts mapping (Exa facts grouped by source_url)
    url_to_exa_facts: dict[str, list[dict]] = {}
    for fact in facts:
        url = fact.get("source_url", "")
        url_to_exa_facts.setdefault(_normalize_url_key(url), []).append(fact)

    # Build (fact_text, normalized_url) -> FactCitation mapping for DB updates
    # Composite key prevents collision when the same fact appears from multiple sources
    fact_key_to_citation: dict[tuple[str, str], object] = {}
    for fc in fact_citations:
        key = (fc.fact_text, _normalize_url_key(fc.source_url))
        fact_key_to_citation[key] = fc

    for norm_url, url_facts in url_to_exa_facts.items():
        verifications = verification_map.get(norm_url, [])
        source_text = source_content_map.get(norm_url, "")

        for i, fact in enumerate(url_facts):
            fact_key = (fact.get("fact_text", ""), norm_url)
            fc = fact_key_to_citation.get(fact_key)
            if not fc:
                continue

            # Find matching verification result
            ver = None
            for v in verifications:
                if v.get("claim_index") == i:
                    ver = v
                    break

            if ver is None:
                # No verification result — keep with reduced confidence
                fc.grounding_method = "exa_unverified"
                fc.confidence_score = min(fc.confidence_score, 0.60)
                fc.composite_score = (fc.confidence_score * 100 + (fc.source_credibility or 55)) / 2
                verified.append(fc)
                continue

            # Check if fact is present in source
            if not ver.get("present", False):
                # REJECT — fact not found in actual source content
                fc.verification_status = "rejected_not_in_source"
                fc.is_verified = False
                fc.is_grounded = False
                fc.grounding_method = "fact_grounding_rejected"
                rejected.append({
                    "fact_text": fc.fact_text[:200],
                    "source_url": fc.source_url,
                    "reason": "Fact not found in actual source page content",
                })
                logger.warning(
                    f"[FACT-GROUND] REJECTED: '{fc.fact_text[:80]}...' "
                    f"not found at {fc.source_url[:80]}"
                )
                continue

            # Fact is present — enrich with exact quote
            exact_quote = ver.get("exact_quote")
            if exact_quote and source_text:
                # Deterministic guard: verify key numbers from quote appear in raw content
                quote_numbers = set(re.findall(r'\d+(?:\.\d+)?', exact_quote))
                significant_nums = {n for n in quote_numbers if len(n) >= 2}
                if not significant_nums or any(n in source_text for n in significant_nums):
                    # Quote checks out — use it as the enriched fact_text
                    enriched_text = exact_quote.strip()

                    # Append methodology note if present
                    methodology = ver.get("methodology_note")
                    if methodology:
                        enriched_text += f" ({sanitize_external_content(methodology, max_chars=200)})"

                    # Append missing context if present
                    missing_ctx = ver.get("missing_context")
                    if missing_ctx:
                        enriched_text += (
                            f" [Full context: {sanitize_external_content(missing_ctx, max_chars=300)}]"
                        )

                    fc.fact_text = enriched_text
                    enriched_count += 1
                else:
                    # Quote numbers don't match source — don't trust the quote
                    logger.warning(
                        f"[FACT-GROUND] Quote numbers mismatch for "
                        f"'{fc.fact_text[:60]}...' — keeping original fact_text"
                    )

            # Update grounding status
            fc.grounding_method = "fact_grounding_verified"
            fc.is_grounded = True
            fc.is_verified = True

            # Track core text length for annotation-aware truncation (Change 3a)
            fc._core_text_len = len(fc.fact_text)

            # Tag secondary citations for Step 4
            if ver.get("is_secondary_citation"):
                primary_name = ver.get("primary_source_name", "")
                if primary_name:
                    fc.confidence_score = min(fc.confidence_score, 0.70)
                    fc.composite_score = (fc.confidence_score * 100 + (fc.source_credibility or 55)) / 2
                    secondary_facts.append((fc, ver))
                    logger.info(
                        f"[FACT-GROUND] Secondary citation: '{fc.fact_text[:60]}...' "
                        f"cites {primary_name} via {fc.source_url[:60]}"
                    )

            # Tag versioned facts for Step 5
            if ver.get("version_info"):
                versioned_facts.append((fc, ver))

            verified.append(fc)

    # DB changes are committed by the orchestrator after all steps complete

    logger.info(
        f"[FACT-GROUND] Step 3 complete: {len(verified)} verified, "
        f"{len(rejected)} rejected, {enriched_count} enriched, "
        f"{len(secondary_facts)} secondary, {len(versioned_facts)} versioned"
    )

    return {
        "verified_citations": verified,
        "rejected": rejected,
        "enriched_count": enriched_count,
        "secondary_facts": secondary_facts,
        "versioned_facts": versioned_facts,
    }


# --- Step 3.5: Cross-Source Corroboration ---

_SYNDICATION_DOMAINS = {
    "prnewswire.com", "businesswire.com", "globenewswire.com",
    "pr.com", "accesswire.com", "newswire.com",
}

# Statistical claim pattern: percentages or dollar amounts
_STAT_CLAIM_PATTERN = re.compile(r'\d+(?:\.\d+)?%|\$[\d,]+\.?\d*')


def _number_in_context(
    content: str, target_number: str, key_terms: set[str], window: int = 100,
) -> bool:
    """
    Check if target_number appears near key_terms in the content.
    Requires the number within ~100 words of at least 2 key terms.
    Pure Python — no LLM cost.
    """
    content_lower = content.lower()
    for match in re.finditer(re.escape(target_number), content_lower):
        start = max(0, match.start() - window * 6)  # ~6 chars per word
        end = min(len(content_lower), match.end() + window * 6)
        context_window = content_lower[start:end]
        matching_terms = sum(1 for t in key_terms if t in context_window)
        if matching_terms >= 2:
            return True
    return False


async def _search_corroboration(
    uncorroborated_facts: list,
    max_searches: int,
) -> dict:
    """
    For uncorroborated statistical facts, search Exa for independent
    confirmation from different sources.

    Returns: {id(fc): {"corroborated": bool, "count": int, "has_authoritative": bool}}
    """
    from .source_verification_service import _extract_numbers, _extract_key_terms
    from ..domain_tiers import get_domain_tier_score

    results_map: dict[int, dict] = {}
    if not uncorroborated_facts:
        return results_map

    # Limit to max_searches
    candidates = uncorroborated_facts[:max_searches]

    # Phase 1: Build search queries and run Exa searches in parallel
    search_tasks = []
    search_meta = []  # Parallel list: (fc, numbers, key_terms, source_domain)

    for fc in candidates:
        numbers = _extract_numbers(fc.fact_text)
        key_terms = _extract_key_terms(fc.fact_text)
        source_domain = _extract_domain(fc.source_url)

        # Build keyword search query: quoted number + key terms
        # Pick the most significant number (longest = most specific)
        stat_numbers = sorted(numbers, key=len, reverse=True)
        if not stat_numbers:
            continue
        primary_num = stat_numbers[0]

        # Pick top 2 key terms by length (longer = more specific)
        sorted_terms = sorted(key_terms, key=len, reverse=True)[:2]
        query_parts = [f'"{primary_num}"'] + [f'"{t}"' for t in sorted_terms]
        query = " ".join(query_parts)

        exclude_domains = [source_domain] if source_domain else []

        search_payload = {
            "query": query,
            "type": "keyword",  # Keyword search respects exact quoted strings
            "numResults": 3,
        }
        if exclude_domains:
            search_payload["excludeDomains"] = exclude_domains

        search_tasks.append(exa_search(search_payload, timeout=15))
        search_meta.append((fc, numbers, key_terms, source_domain))

    if not search_tasks:
        return results_map

    logger.info(
        f"[FACT-GROUND] Step 3.5b: Searching corroboration for "
        f"{len(search_tasks)} uncorroborated facts"
    )

    search_results = await asyncio.gather(*search_tasks, return_exceptions=True)

    # Phase 2: Collect all unique URLs to fetch in batched exa_contents calls
    all_urls_to_fetch: list[str] = []
    url_to_fact_indices: dict[str, list[int]] = {}  # url -> indices into search_meta

    for idx, (search_result, meta) in enumerate(zip(search_results, search_meta)):
        if isinstance(search_result, Exception):
            logger.warning(
                f"[FACT-GROUND] Step 3.5b: Search failed for "
                f"'{meta[0].fact_text[:60]}...': {search_result}"
            )
            continue

        results = search_result.get("results", [])
        for r in results:
            url = r.get("url", "")
            if not url:
                continue
            domain = _extract_domain(url)
            # Skip syndication domains
            if domain in _SYNDICATION_DOMAINS:
                continue
            # Skip same domain as original source
            if domain == meta[3]:
                continue

            if url not in url_to_fact_indices:
                url_to_fact_indices[url] = []
                all_urls_to_fetch.append(url)
            url_to_fact_indices[url].append(idx)

    if not all_urls_to_fetch:
        logger.info("[FACT-GROUND] Step 3.5b: No corroboration URLs to fetch")
        return results_map

    # Batched content fetch (1-2 calls via exa_contents, Semaphore(20))
    content_map: dict[str, str] = {}
    try:
        # Batch in chunks of 10 URLs
        for batch_start in range(0, len(all_urls_to_fetch), 10):
            batch_urls = all_urls_to_fetch[batch_start:batch_start + 10]
            contents_payload = {
                "ids": batch_urls,
                "text": {"maxCharacters": FACT_GROUNDING_CONTENT_MAX_CHARS},
            }
            contents_result = await exa_contents(contents_payload, timeout=20)
            for item in contents_result.get("results", []):
                url = item.get("url", "")
                text = item.get("text", "")
                if url and text and len(text.strip()) > 100:
                    content_map[url] = text.strip()
    except Exception as e:
        logger.error(f"[FACT-GROUND] Step 3.5b: Content fetch failed: {e}")

    # Phase 3: Check each fact against fetched content
    corroborated_count = 0

    for idx, (fc, numbers, key_terms, source_domain) in enumerate(search_meta):
        corroborating_domains: set[str] = set()
        has_authoritative = False

        # Find URLs that were fetched for this fact's search results
        if isinstance(search_results[idx], Exception):
            continue

        results = search_results[idx].get("results", [])
        for r in results:
            url = r.get("url", "")
            domain = _extract_domain(url)
            if domain in _SYNDICATION_DOMAINS or domain == source_domain:
                continue
            if domain in corroborating_domains:
                continue  # Domain dedup

            content = content_map.get(url, "")
            if not content:
                continue

            # Number-in-context check: key number near key terms
            stat_numbers = sorted(numbers, key=len, reverse=True)
            found_in_context = False
            for num in stat_numbers[:2]:  # Check top 2 numbers
                if _number_in_context(content, num.lower(), key_terms):
                    found_in_context = True
                    break

            if found_in_context:
                corroborating_domains.add(domain)
                tier_level, _ = get_domain_tier_score(domain)
                if tier_level in (1, 2):
                    has_authoritative = True

        corr_count = len(corroborating_domains)
        results_map[id(fc)] = {
            "corroborated": corr_count > 0,
            "count": corr_count,
            "has_authoritative": has_authoritative,
        }

        if corr_count > 0:
            corroborated_count += 1
            logger.info(
                f"[FACT-GROUND] Step 3.5b: '{fc.fact_text[:60]}...' corroborated "
                f"by {corr_count} independent source(s) "
                f"(authoritative: {has_authoritative})"
            )

    logger.info(
        f"[FACT-GROUND] Step 3.5b complete: {corroborated_count}/{len(candidates)} "
        f"facts found independent corroboration"
    )
    return results_map


# --- Step 4 Helper: GLM-5 Primary Source Verification ---

_PRIMARY_VERIFICATION_PROMPT = """You are a senior research analyst comparing an intermediate claim against a primary source.

INTERMEDIATE CLAIM (from {intermediate_domain}):
"{fact_text}"

PRIMARY SOURCE CONTENT (from {primary_source_name}):
{primary_content}

Questions:
1. Does this primary source contain data about the same metric/topic as the claim?
2. If yes: what specific number does the primary source report for this metric?
3. Does the primary source's number CONFIRM or CONTRADICT the intermediate claim's number?

Return JSON:
{{
  "same_topic": true | false,
  "primary_number": "94.4%" | null,
  "primary_quote": "exact quote from primary source" | null,
  "verdict": "confirmed" | "contradicted" | "not_found" | "different_metric"
}}"""


async def _verify_primary_with_glm5(
    fact_text: str,
    intermediate_domain: str,
    primary_source_name: str,
    primary_content: str,
) -> dict:
    """
    GLM-5 second opinion when regex number comparison fails.
    Only called when regex flags a mismatch — acts as a semantic check
    for format variations ("94.4%" vs "94.4 percent") and incidental matches.

    Returns: {"verdict": str, "primary_number": str|None, "primary_quote": str|None}
    """
    # Sanitize all external inputs per security rules
    safe_fact = sanitize_external_content(fact_text, max_chars=500)
    safe_domain = sanitize_external_content(intermediate_domain, max_chars=200)
    safe_source_name = sanitize_external_content(primary_source_name, max_chars=200)
    safe_content = sanitize_external_content(
        primary_content, max_chars=FACT_GROUNDING_CONTENT_MAX_CHARS
    )

    prompt = _PRIMARY_VERIFICATION_PROMPT.format(
        intermediate_domain=safe_domain,
        fact_text=safe_fact,
        primary_source_name=safe_source_name,
        primary_content=safe_content,
    )

    payload = {
        "model": GLM5_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "You are a fact verification specialist. Output valid JSON ONLY.",
            },
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
        "temperature": FACT_GROUNDING_GLM5_TEMPERATURE,
        "thinking": {"type": "enabled"},
    }

    try:
        data = await call_glm5_with_retry(payload)
        content_text = (
            data.get("choices", [{}])[0].get("message", {}).get("content", "")
        )
        parsed = json.loads(content_text) if content_text else {}

        verdict = parsed.get("verdict", "not_found")
        primary_number = parsed.get("primary_number")
        primary_quote = parsed.get("primary_quote")

        # Deterministic quote guard: verify GLM-5 didn't fabricate the quote
        if verdict == "confirmed" and primary_quote:
            quote_nums = set(re.findall(r'\d+(?:\.\d+)?', primary_quote))
            sig_nums = {n for n in quote_nums if len(n) >= 2}
            if sig_nums and not any(n in primary_content for n in sig_nums):
                # GLM-5 fabricated the quote — don't trust "confirmed"
                logger.warning(
                    f"[FACT-GROUND] Step 4 GLM-5: Quote guard triggered — "
                    f"quote numbers {sig_nums} not in primary source. "
                    f"Falling back to not_found."
                )
                verdict = "not_found"
                primary_quote = None

        logger.info(
            f"[FACT-GROUND] Step 4 GLM-5: verdict={verdict} for "
            f"'{fact_text[:60]}...' against {primary_source_name[:60]}"
        )

        return {
            "verdict": verdict,
            "primary_number": primary_number,
            "primary_quote": primary_quote,
        }

    except (json.JSONDecodeError, KeyError, IndexError) as e:
        logger.error(
            f"[FACT-GROUND] Step 4 GLM-5: Parse error for "
            f"'{fact_text[:60]}...': {e}"
        )
        return {"verdict": "not_found", "primary_number": None, "primary_quote": None}
    except Exception as e:
        logger.error(
            f"[FACT-GROUND] Step 4 GLM-5: Failed for "
            f"'{fact_text[:60]}...': {e}"
        )
        return {"verdict": "not_found", "primary_number": None, "primary_quote": None}


# --- Step 4: Trace Secondary Citations to Primary Sources ---

async def _trace_and_verify_primary_sources(
    secondary_facts: list[tuple],
    source_content_map: dict[str, str],
) -> int:
    """
    For facts flagged as secondary citations, trace to the primary source
    and verify numbers match. Uses existing KNOWN_RESEARCH_ORGS for domain
    lookup, falls back to Exa search.

    Returns count of facts where primary source was traced.
    Cost: ~$0.002-0.003 (1-3 Exa search + contents calls)
    """
    if not secondary_facts:
        return 0

    traced_count = 0
    lookups_done = 0

    for fc, ver in secondary_facts:
        if lookups_done >= FACT_GROUNDING_MAX_PRIMARY_LOOKUPS:
            logger.info(
                f"[FACT-GROUND] Step 4: Max primary lookups reached "
                f"({FACT_GROUNDING_MAX_PRIMARY_LOOKUPS})"
            )
            break

        primary_name = ver.get("primary_source_name", "").strip()
        if not primary_name:
            continue

        # Look up canonical domains for the primary source org
        primary_key = primary_name.lower().split(" et al")[0].split(",")[0].strip()
        canonical_domains = KNOWN_RESEARCH_ORGS.get(primary_key, [])

        primary_url = None
        primary_content = None

        try:
            if canonical_domains:
                # Known org — search constrained to canonical domains
                search_payload = {
                    "query": fc.fact_text[:200],
                    "type": "neural",
                    "numResults": 3,
                    "includeDomains": canonical_domains,
                }
                search_result = await exa_search(search_payload, timeout=15)
                results = search_result.get("results", [])
                if results:
                    primary_url = results[0].get("url", "")
            else:
                # Unknown org — broader search with primary source name + key numbers
                fact_numbers = re.findall(r'\d+(?:\.\d+)?%?', fc.fact_text)
                key_nums = " ".join(fact_numbers[:3]) if fact_numbers else ""
                query = f'"{sanitize_external_content(primary_name, max_chars=100)}" {key_nums}'.strip()
                search_payload = {
                    "query": query,
                    "type": "neural",
                    "numResults": 3,
                }
                search_result = await exa_search(search_payload, timeout=15)
                results = search_result.get("results", [])
                if results:
                    primary_url = results[0].get("url", "")

            lookups_done += 1

            if not primary_url:
                logger.debug(
                    f"[FACT-GROUND] Step 4: No primary source found for "
                    f"'{primary_name}'"
                )
                # Keep fact with secondary annotation
                fc.fact_text += (
                    f" (Cited via {_extract_domain(fc.source_url)}; "
                    f"originally from {sanitize_external_content(primary_name, max_chars=100)})"
                )
                continue

            # Fetch primary source content
            contents_payload = {
                "ids": [primary_url],
                "text": {"maxCharacters": FACT_GROUNDING_CONTENT_MAX_CHARS},
            }
            contents_result = await exa_contents(contents_payload, timeout=15)
            primary_results = contents_result.get("results", [])
            if primary_results:
                primary_content = primary_results[0].get("text", "")

            if not primary_content:
                fc.fact_text += (
                    f" (Cited via {_extract_domain(fc.source_url)}; "
                    f"originally from {sanitize_external_content(primary_name, max_chars=100)})"
                )
                continue

            # Compare numbers between intermediate and primary
            # Fast path: regex pre-filter. GLM-5 fallback when regex flags mismatch.
            intermediate_numbers = set(re.findall(r'\d+(?:\.\d+)?', fc.fact_text))
            primary_numbers = set(re.findall(r'\d+(?:\.\d+)?', primary_content))
            significant_intermediate = {
                n for n in intermediate_numbers if len(n) >= 2
            }

            regex_match = (
                not significant_intermediate
                or bool(significant_intermediate & primary_numbers)
            )

            if regex_match:
                # Regex says numbers match — fast path, no GLM-5 needed
                fc.confidence_score = min(0.90, fc.confidence_score + 0.10)
                fc.composite_score = (fc.confidence_score * 100 + (fc.source_credibility or 55)) / 2
                fc.fact_text += (
                    f" (Primary source: "
                    f"{sanitize_external_content(primary_name, max_chars=100)} — verified)"
                )
                logger.info(
                    f"[FACT-GROUND] Step 4: Primary source confirmed (regex) for "
                    f"'{fc.fact_text[:60]}...' at {primary_url[:80]}"
                )
            else:
                # Regex says mismatch — GLM-5 second opinion
                logger.info(
                    f"[FACT-GROUND] Step 4: Regex mismatch for "
                    f"'{fc.fact_text[:60]}...' — invoking GLM-5 second opinion"
                )
                glm5_result = await _verify_primary_with_glm5(
                    fact_text=fc.fact_text,
                    intermediate_domain=_extract_domain(fc.source_url),
                    primary_source_name=primary_name,
                    primary_content=primary_content,
                )
                verdict = glm5_result.get("verdict", "not_found")
                glm5_primary_number = glm5_result.get("primary_number")

                if verdict == "confirmed":
                    # GLM-5 confirms — format variation, not a real mismatch
                    fc.confidence_score = min(0.90, fc.confidence_score + 0.10)
                    fc.composite_score = (fc.confidence_score * 100 + (fc.source_credibility or 55)) / 2
                    fc.fact_text += (
                        f" (Primary source: "
                        f"{sanitize_external_content(primary_name, max_chars=100)} — verified)"
                    )
                    logger.info(
                        f"[FACT-GROUND] Step 4: Primary source confirmed (GLM-5) for "
                        f"'{fc.fact_text[:60]}...'"
                    )
                elif verdict == "contradicted" and glm5_primary_number:
                    # GLM-5 found a different number — correct the fact
                    logger.warning(
                        f"[FACT-GROUND] Step 4: GLM-5 contradiction — "
                        f"primary reports {glm5_primary_number} vs "
                        f"intermediate {significant_intermediate}"
                    )
                    fc.verification_status = "rejected_stale_secondary"
                    fc.is_verified = False
                    fc.confidence_score = 0.30
                    fc.composite_score = (fc.confidence_score * 100 + (fc.source_credibility or 55)) / 2
                    fc.fact_text += (
                        f" [WARNING: Primary source '{sanitize_external_content(primary_name, max_chars=100)}' "
                        f"reports {sanitize_external_content(str(glm5_primary_number), max_chars=50)} "
                        f"— data may be outdated or inaccurate]"
                    )
                elif verdict == "contradicted":
                    # Contradicted but no extractable number — reduce confidence, don't hard-reject
                    fc.verification_status = "suspect"
                    fc.confidence_score = max(0.40, fc.confidence_score - 0.20)
                    fc.composite_score = (fc.confidence_score * 100 + (fc.source_credibility or 55)) / 2
                    fc.fact_text += (
                        f" [WARNING: Primary source '{sanitize_external_content(primary_name, max_chars=100)}' "
                        f"may contradict this claim — verify independently]"
                    )
                elif verdict == "different_metric":
                    # Primary source measures something else — keep fact unchanged
                    fc.fact_text += (
                        f" (Cited via {_extract_domain(fc.source_url)}; "
                        f"originally from {sanitize_external_content(primary_name, max_chars=100)})"
                    )
                else:
                    # not_found — keep fact with secondary annotation
                    fc.fact_text += (
                        f" (Cited via {_extract_domain(fc.source_url)}; "
                        f"originally from {sanitize_external_content(primary_name, max_chars=100)})"
                    )

            # Store primary content in source_content_map (normalized key)
            source_content_map[_normalize_url_key(primary_url)] = primary_content
            traced_count += 1

        except Exception as e:
            logger.error(
                f"[FACT-GROUND] Step 4: Trace failed for "
                f"'{primary_name}': {e}"
            )
            fc.fact_text += (
                f" (Cited via {_extract_domain(fc.source_url)}; "
                f"originally from {sanitize_external_content(primary_name, max_chars=100)})"
            )

    # DB changes are committed by the orchestrator after all steps complete

    logger.info(f"[FACT-GROUND] Step 4 complete: {traced_count} primary sources traced")
    return traced_count


# --- Step 5: Version Currency Check ---

_VERSION_PATTERN = re.compile(
    r'(?:v(?:ersion)?\s*\d|E\d{4}|\d{4}\s+(?:edition|report|survey|study)|'
    r'(?:1st|2nd|3rd|\d+th)\s+(?:edition|annual)|FY\d{4})',
    re.IGNORECASE,
)


async def _check_version_currency(
    versioned_facts: list[tuple],
    all_citations: list,
    source_content_map: dict[str, str],
) -> int:
    """
    For facts referencing versioned documents, search Exa for newer editions.
    Updates fact_text and source_url if newer version found with extractable data.

    Returns count of facts updated with newer version data.
    Cost: ~$0.001-0.003 (1-3 Exa searches)
    """
    # Collect candidates: GLM-5 tagged + regex fallback
    candidates = []
    seen_urls = set()

    # Primary: GLM-5 tagged from Step 2
    for fc, ver in versioned_facts:
        if fc.source_url not in seen_urls:
            candidates.append((fc, ver.get("version_info", "")))
            seen_urls.add(fc.source_url)

    # Fallback: regex scan remaining citations
    for fc in all_citations:
        if fc.source_url in seen_urls:
            continue
        text_to_scan = f"{fc.fact_text} {fc.source_title}"
        if _VERSION_PATTERN.search(text_to_scan):
            candidates.append((fc, _VERSION_PATTERN.search(text_to_scan).group()))
            seen_urls.add(fc.source_url)

    if not candidates:
        logger.info("[FACT-GROUND] Step 5: No versioned documents detected")
        return 0

    updated_count = 0
    checks_done = 0

    for fc, version_hint in candidates:
        if checks_done >= FACT_GROUNDING_VERSION_CURRENCY_MAX:
            break

        try:
            # Extract document title for search
            doc_title = fc.source_title or ""
            source_domain = _extract_domain(fc.source_url)

            # Search for newer version
            query = f'"{sanitize_external_content(doc_title, max_chars=100)}" latest'
            search_payload = {
                "query": query,
                "type": "neural",
                "numResults": 3,
            }
            if source_domain:
                search_payload["includeDomains"] = [source_domain]

            search_result = await exa_search(search_payload, timeout=15)
            results = search_result.get("results", [])
            checks_done += 1

            if not results:
                continue

            # Check if any result is newer
            best = results[0]
            newer_url = best.get("url", "")
            newer_title = best.get("title", "")

            if newer_url and newer_url != fc.source_url and newer_title:
                # Annotate the fact with version context
                fc.fact_text += (
                    f" (As of {sanitize_external_content(str(version_hint), max_chars=50)}"
                    f" — a newer edition may exist: "
                    f"{sanitize_external_content(newer_title[:100], max_chars=100)})"
                )
                updated_count += 1
                logger.info(
                    f"[FACT-GROUND] Step 5: Version update for "
                    f"'{fc.source_title[:60]}' — newer: '{newer_title[:60]}'"
                )

        except Exception as e:
            logger.error(
                f"[FACT-GROUND] Step 5: Version check failed for "
                f"'{fc.source_title[:60]}': {e}"
            )

    # DB changes are committed by the orchestrator after all steps complete

    logger.info(f"[FACT-GROUND] Step 5 complete: {updated_count} version annotations added")
    return updated_count


# --- Step 6: Conflict Tagging ---

def _tag_conflatable_facts(fact_citations: list) -> None:
    """
    Detect facts with similar numbers from different sources that could be
    conflated by the writer. Tag each with methodology context.
    Modifies fact_citations in place.

    Cost: $0.00 (pure Python)
    """
    if len(fact_citations) < 2:
        return

    # Extract (number, fact_citation) pairs
    num_to_facts: dict[str, list] = {}
    for fc in fact_citations:
        numbers = re.findall(r'(\d+(?:\.\d+)?)\s*%', fc.fact_text)
        for num in numbers:
            num_to_facts.setdefault(num, []).append(fc)

    # Find numbers that appear in facts from different sources
    conflicts_tagged = 0
    tagged_objs: set[int] = set()  # Python object ids (fc.id may be None pre-flush)

    for num, fcs in num_to_facts.items():
        if len(fcs) < 2:
            continue

        # Group by source URL
        urls = {fc.source_url for fc in fcs}
        if len(urls) < 2:
            continue

        # Multiple sources have the same number — tag each
        for fc in fcs:
            if id(fc) in tagged_objs:
                continue
            if "(Note: This measures" not in fc.fact_text:
                fc.fact_text += (
                    " (Note: This measures a specific metric. "
                    "Do NOT combine with other statistics measuring different things.)"
                )
                tagged_objs.add(id(fc))
                conflicts_tagged += 1

    # Also check for similar-but-not-identical numbers (within 15%)
    all_nums: list[tuple[float, object]] = []
    for fc in fact_citations:
        if id(fc) in tagged_objs:
            continue
        numbers = re.findall(r'(\d+(?:\.\d+)?)\s*%', fc.fact_text)
        for num_str in numbers:
            try:
                all_nums.append((float(num_str), fc))
            except ValueError:
                continue

    # Sort by number value for efficient pairwise comparison
    all_nums.sort(key=lambda x: x[0])
    for i in range(len(all_nums)):
        for j in range(i + 1, len(all_nums)):
            val_a, fc_a = all_nums[i]
            val_b, fc_b = all_nums[j]

            if val_b - val_a > val_a * 0.15:
                break  # Numbers too far apart, stop inner loop

            if fc_a.source_url == fc_b.source_url:
                continue
            if id(fc_a) in tagged_objs and id(fc_b) in tagged_objs:
                continue

            # Similar numbers from different sources — tag both
            for fc in (fc_a, fc_b):
                if id(fc) not in tagged_objs and "(Note: This measures" not in fc.fact_text:
                    fc.fact_text += (
                        " (Note: This measures a specific metric. "
                        "Do NOT combine with other statistics measuring "
                        "different things.)"
                    )
                    tagged_objs.add(id(fc))
                    conflicts_tagged += 1

    if conflicts_tagged:
        logger.info(
            f"[FACT-GROUND] Step 6: Tagged {conflicts_tagged} facts with "
            f"conflict warnings"
        )


# --- Orchestrator ---

async def ground_facts(
    facts: list[dict],
    fact_citations: list,
    db: Session,
) -> dict:
    """
    Main entry point for Fact Grounding Agent (Phase 1.7).

    Verifies Exa Research facts against actual source content, rejects
    unverified facts, enriches survivors, traces secondary citations,
    checks version currency, and tags conflatable facts.

    Args:
        facts: Raw fact dicts from Exa Research API (research_result["facts"])
        fact_citations: FactCitation ORM objects from create_citations_from_research()
        db: SQLAlchemy session

    Returns: {
        verified_citations: list[FactCitation],
        source_content: dict[str, str],  -- real page content for source_content_map
        rejected_count: int,
        enriched_count: int,
        secondary_traced: int,
        version_updated: int,
    }
    """
    logger.info(
        f"[FACT-GROUND] Starting Phase 1.7: {len(facts)} facts from "
        f"{len(set(f.get('source_url', '') for f in facts))} sources"
    )

    # Flush DB to assign FactCitation IDs for consensus scoring (Step 3.5a)
    ids_available = False
    try:
        db.flush()
        ids_available = True
    except Exception as e:
        logger.warning(
            f"[FACT-GROUND] db.flush() failed (non-fatal): {e}. "
            f"Using object ids for consensus."
        )
        db.rollback()

    # Step 1: Fetch real source content (pass raw URLs to Exa, keys come back normalized)
    source_urls = list({f.get("source_url", "") for f in facts if f.get("source_url")})
    source_content = await _fetch_source_content(source_urls)

    if not source_content:
        logger.warning(
            "[FACT-GROUND] Step 1 returned no content — falling back to unverified"
        )
        # Tag all citations as unverified
        for fc in fact_citations:
            fc.grounding_method = "exa_unverified"
        try:
            db.commit()
        except Exception:
            db.rollback()
        return {
            "verified_citations": list(fact_citations),
            "source_content": {},
            "rejected_count": 0,
            "enriched_count": 0,
            "secondary_traced": 0,
            "version_updated": 0,
            "corroboration_count": 0,
        }

    # Step 2: GLM-5 AI Analyst — verify facts against real content (parallel, queued by semaphore)
    # Group facts by normalized source URL (matches source_content keys)
    facts_by_url: dict[str, list[dict]] = {}
    for fact in facts:
        url = fact.get("source_url", "")
        if url:
            facts_by_url.setdefault(_normalize_url_key(url), []).append(fact)

    verification_tasks = []
    verification_urls = []
    for norm_url, url_facts in facts_by_url.items():
        content = source_content.get(norm_url, "")
        if content:
            # Find title from facts
            title = url_facts[0].get("source_title") or url_facts[0].get("title") or "Unknown Source"
            verification_tasks.append(
                _verify_facts_against_source(norm_url, title, content, url_facts)
            )
            verification_urls.append(norm_url)

    # Run all verification calls (GLM_SEMAPHORE limits to 2 concurrent)
    verification_results = await asyncio.gather(
        *verification_tasks, return_exceptions=True
    )

    # Build verification map: url -> list of verification dicts
    verification_map: dict[str, list[dict]] = {}
    for url, result in zip(verification_urls, verification_results):
        if isinstance(result, Exception):
            logger.error(
                f"[FACT-GROUND] Step 2 exception for {url[:80]}: {result}"
            )
            verification_map[url] = []
        else:
            verification_map[url] = result

    # Step 3: Filter and enrich
    step3_result = _apply_verification_results(
        facts, fact_citations, verification_map, source_content
    )
    verified_citations = step3_result["verified_citations"]
    rejected = step3_result["rejected"]
    enriched_count = step3_result["enriched_count"]
    secondary_facts = step3_result["secondary_facts"]
    versioned_facts = step3_result["versioned_facts"]

    # Step 3.5: Cross-Source Corroboration
    corroboration_count = 0
    if FACT_GROUNDING_CORROBORATION_ENABLED and verified_citations:
        # Step 3.5a: In-pool consensus (free, pure Python)
        if ids_available:
            # Build source_tiers from verified citations
            source_tiers: dict[str, int] = {}
            for fc in verified_citations:
                domain = _extract_domain(fc.source_url)
                if domain and domain not in source_tiers:
                    tier_level, _ = get_domain_tier_score(domain)
                    source_tiers[domain] = tier_level

            consensus_map = score_fact_consensus(verified_citations, source_tiers)
            for fc in verified_citations:
                entry = consensus_map.get(fc.id, {"count": 1, "has_authoritative": False})
                fc.consensus_count = entry["count"]
                has_auth = entry["has_authoritative"]

                if entry["count"] >= 3 and has_auth:
                    fc.composite_score = min(100.0, (fc.composite_score or 50.0) * 1.3)
                elif entry["count"] >= 2 and has_auth:
                    fc.composite_score = min(100.0, (fc.composite_score or 50.0) * 1.15)
                elif entry["count"] == 1:
                    # Don't penalize facts tagged as secondary citations — they get
                    # verified in Step 4 via primary source tracing, not consensus.
                    is_secondary = any(fc is sf for sf, _ in secondary_facts)
                    if not is_secondary:
                        fc.composite_score = (fc.composite_score or 50.0) * 0.85

            pool_corroborated = sum(
                1 for fc in verified_citations if fc.consensus_count > 1
            )
            logger.info(
                f"[FACT-GROUND] Step 3.5a: In-pool consensus — "
                f"{pool_corroborated}/{len(verified_citations)} facts corroborated"
            )
        else:
            logger.info(
                "[FACT-GROUND] Step 3.5a skipped (no DB ids). "
                "Active corroboration still runs."
            )

        # Step 3.5b: Active corroboration search for uncorroborated statistical facts
        # Filter: consensus_count==1, has statistical claim, not secondary, not Tier 1-2
        uncorroborated = []
        for fc in verified_citations:
            if fc.consensus_count > 1:
                continue
            if not _STAT_CLAIM_PATTERN.search(fc.fact_text):
                continue
            # Skip secondary citations (Step 4 handles those)
            if any(fc is sf for sf, _ in secondary_facts):
                continue
            # Skip Tier 1-2 domains (authoritative enough to stand alone)
            domain = _extract_domain(fc.source_url)
            tier_level, _ = get_domain_tier_score(domain)
            if tier_level in (1, 2):
                continue
            uncorroborated.append(fc)

        if uncorroborated:
            corr_results = await _search_corroboration(
                uncorroborated, FACT_GROUNDING_MAX_CORROBORATION_SEARCHES
            )
            for fc in uncorroborated:
                entry = corr_results.get(id(fc))
                if not entry:
                    continue
                if entry["corroborated"]:
                    fc.consensus_count = (fc.consensus_count or 1) + entry["count"]
                    corroboration_count += 1
                    # Apply boost based on count + authoritative
                    if entry["count"] >= 2 and entry["has_authoritative"]:
                        fc.composite_score = min(100.0, (fc.composite_score or 50.0) * 1.3)
                    elif entry["has_authoritative"]:
                        fc.composite_score = min(100.0, (fc.composite_score or 50.0) * 1.15)
                else:
                    # No corroboration found — annotate (penalty already applied in 3.5a)
                    fc.fact_text += " (Single-source claim — no independent corroboration found)"

        logger.info(
            f"[FACT-GROUND] Step 3.5 complete: {corroboration_count} facts "
            f"found active corroboration"
        )

    # Step 4: Trace secondary citations to primary sources
    secondary_traced = await _trace_and_verify_primary_sources(
        secondary_facts, source_content
    )

    # Remove facts that were rejected during primary source tracing
    verified_citations = [
        fc for fc in verified_citations
        if fc.verification_status != "rejected_stale_secondary"
    ]

    # Step 5: Version currency check
    version_updated = await _check_version_currency(
        versioned_facts, verified_citations, source_content
    )

    # Step 6: Conflict tagging
    _tag_conflatable_facts(verified_citations)

    # Annotation-aware fact_text cap (Change 3a)
    # Trim only annotations beyond core text to keep fact data intact
    MAX_ENRICHED_FACT_TEXT = 600
    for fc in verified_citations:
        if len(fc.fact_text) > MAX_ENRICHED_FACT_TEXT:
            core_len = getattr(fc, '_core_text_len', len(fc.fact_text))
            core = fc.fact_text[:core_len]
            annotations = fc.fact_text[core_len:]
            remaining = MAX_ENRICHED_FACT_TEXT - len(core)
            if remaining > 20 and annotations:
                trimmed = annotations[:remaining]
                last_close = max(trimmed.rfind(')'), trimmed.rfind(']'))
                if last_close > 0:
                    fc.fact_text = core + trimmed[:last_close + 1]
                else:
                    fc.fact_text = core + trimmed.rstrip()
            elif len(core) <= MAX_ENRICHED_FACT_TEXT:
                fc.fact_text = core
            else:
                fc.fact_text = core[:MAX_ENRICHED_FACT_TEXT].rsplit('. ', 1)[0] + '.'

    # Final DB commit for all steps
    try:
        db.commit()
    except Exception as e:
        logger.error(f"[FACT-GROUND] Final DB commit failed: {e}")
        db.rollback()

    logger.info(
        f"[FACT-GROUND] Phase 1.7 complete: "
        f"{len(verified_citations)} verified, {len(rejected)} rejected, "
        f"{enriched_count} enriched, {secondary_traced} secondary traced, "
        f"{version_updated} version updated, {corroboration_count} corroborated"
    )

    return {
        "verified_citations": verified_citations,
        "source_content": source_content,
        "rejected_count": len(rejected),
        "enriched_count": enriched_count,
        "secondary_traced": secondary_traced,
        "version_updated": version_updated,
        "corroboration_count": corroboration_count,
    }


# --- Utilities ---

def _normalize_url_key(url: str) -> str:
    """
    URL normalization matching _normalize_url() in main.py exactly.
    Strips www prefix, query params, fragments, trailing slash.
    Keeps scheme so keys are consistent with source_content_map.
    """
    try:
        parsed = urlparse(url)
        netloc = parsed.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        path = parsed.path.rstrip("/") or "/"
        return urlunparse((parsed.scheme, netloc, path, "", "", ""))
    except Exception:
        return url


def _extract_domain(url: str) -> str:
    """Extract domain from URL, stripping www prefix."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path.split("/")[0]
        if domain.startswith("www."):
            domain = domain[4:]
        return domain.lower()
    except Exception:
        return ""
