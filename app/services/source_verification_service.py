"""
Source Verification Service - Phase 1.5

Validates credibility of research sources using multi-factor scoring:
- Domain authority (DataForSEO)
- Domain type (.gov, .edu, research journals)
- Content freshness (publish date)
- Internal citations (backlink verification)
- Content quality (Gemini Flash)

Extracts factual claims and maps them to verified sources for citation injection.
"""

import json
import logging
import re
from datetime import datetime, timedelta
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from ..models import DomainCredibilityCache, FactCitation, VerifiedSource
from ..settings import GEMINI_API_KEY
from ..domain_tiers import get_domain_tier_score

logger = logging.getLogger(__name__)

# Constants for domain categorization
# Note: AUTHORITATIVE_DOMAINS, ACADEMIC_DOMAINS, and MAJOR_PUBLISHERS removed
# Replaced with tiered domain system in domain_tiers.py

SOCIAL_MEDIA_DOMAINS = {
    "facebook.com", "twitter.com", "x.com", "linkedin.com", "instagram.com",
    "youtube.com", "tiktok.com", "reddit.com", "pinterest.com", "snapchat.com",
}


# --- Helper Functions ---

def extract_domain(url: str) -> str:
    """Extract domain from URL (e.g., 'https://example.com/path' -> 'example.com')."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        # Remove 'www.' prefix
        if domain.startswith("www."):
            domain = domain[4:]
        return domain
    except Exception as e:
        logger.warning(f"Failed to parse URL {url}: {e}")
        return ""


def is_authoritative_domain(domain: str) -> bool:
    """Check if domain is Tier 1 (authoritative)."""
    tier_level, _ = get_domain_tier_score(domain)
    return tier_level == 1


def is_academic_domain(domain: str) -> bool:
    """Check if domain is Tier 1 or has academic TLD."""
    if domain.endswith(".edu") or ".ac." in domain:
        return True
    tier_level, _ = get_domain_tier_score(domain)
    return tier_level == 1


def is_major_publisher(domain: str) -> bool:
    """Check if domain is Tier 3+ (quality publications)."""
    tier_level, _ = get_domain_tier_score(domain)
    return tier_level >= 3


def extract_publish_date(content: str, source_url: str = "") -> datetime | None:
    """
    Extract publish date from article content using enhanced regex patterns.
    Looks for common date formats in first 5000 chars (increased from 2000).
    Falls back to URL pattern matching if content extraction fails.
    Returns None if not found.

    Hybrid Approach (March 2026): Improved to capture more date formats.
    """
    # Enhanced date patterns covering more metadata formats
    patterns = [
        # Metadata patterns (high confidence)
        r"published[:\s]+(\d{4})-(\d{2})-(\d{2})",  # published: 2024-03-15
        r"date[:\s]+(\d{4})-(\d{2})-(\d{2})",  # date: 2024-03-15
        r"updated[:\s]+(\d{4})-(\d{2})-(\d{2})",  # updated: 2024-03-15
        r"last[\s-]modified[:\s]+(\d{4})-(\d{2})-(\d{2})",  # last-modified: 2024-03-15

        # ISO 8601 formats
        r"(\d{4})-(\d{2})-(\d{2})T\d{2}:\d{2}",  # 2024-03-15T14:30
        r"(\d{4})-(\d{2})-(\d{2})",  # 2024-03-15

        # Natural language formats
        r"(\w+ \d{1,2}, \d{4})",  # March 15, 2024
        r"(\d{1,2} \w+ \d{4})",  # 15 March 2024

        # Alternative formats
        r"(\d{1,2}/\d{1,2}/\d{4})",  # 03/15/2024 or 15/03/2024
        r"(\d{4}\.\d{2}\.\d{2})",  # 2024.03.15
    ]

    # Search in first 5000 chars (increased from 2000 to catch more metadata)
    search_text = content[:5000].lower()

    for pattern in patterns:
        match = re.search(pattern, search_text)
        if match:
            try:
                date_str = match.group(0)
                # Try parsing with dateutil (handles multiple formats)
                from dateutil import parser
                parsed_date = parser.parse(date_str, fuzzy=True)

                # Sanity check: reject dates in the future or before 2000
                if datetime(2000, 1, 1) <= parsed_date <= datetime.now():
                    return parsed_date
            except Exception:
                continue

    # Fallback: Extract date from URL path (e.g., /2024/03/15/article-title)
    if source_url:
        url_date_pattern = r"/(\d{4})/(\d{2})/(\d{2})/"
        url_match = re.search(url_date_pattern, source_url)
        if url_match:
            try:
                year, month, day = map(int, url_match.groups())
                url_date = datetime(year, month, day)
                if datetime(2000, 1, 1) <= url_date <= datetime.now():
                    return url_date
            except Exception:
                pass

    return None


def extract_urls_from_content(content: str) -> list[str]:
    """
    Extract URLs from article content (markdown links and HTML anchors).
    Returns list of unique URLs.
    """
    urls = []

    # Markdown links: [text](url)
    markdown_pattern = r'\[([^\]]+)\]\((https?://[^\)]+)\)'
    markdown_urls = re.findall(markdown_pattern, content)
    urls.extend([url for _, url in markdown_urls])

    # HTML anchors: <a href="url">
    html_pattern = r'<a[^>]+href=["\']+(https?://[^"\']+)["\']+'
    html_urls = re.findall(html_pattern, content)
    urls.extend(html_urls)

    # Plain URLs
    plain_pattern = r'https?://[^\s<>"]+(?:[^\s<>"]|(?<=\w)/)*'
    plain_urls = re.findall(plain_pattern, content)
    urls.extend(plain_urls)

    # Remove duplicates and clean
    unique_urls = list(set(urls))
    return [url.strip().rstrip(".,;:)") for url in unique_urls]


# --- Domain Tier Scoring (Replaces DataForSEO) ---

def get_domain_tier_score_wrapper(domain: str) -> dict:
    """
    Get tier-based credibility score for domain.
    Returns dict compatible with old domain_authority format.
    Cost: $0.00 (no API calls)

    Returns:
        dict: {
            "tier_level": int (1-4, or 0 for unknown),
            "domain_authority": int (40/30/20/10/0 points)
        }
    """
    tier_level, score = get_domain_tier_score(domain)
    logger.info(f"[TIER] {domain} → Tier {tier_level} (Score: {score})")

    return {
        "tier_level": tier_level,
        "domain_authority": score,  # Keep same field name for compatibility
    }


# --- Backlink Verification ---

async def extract_internal_citations(content: str, source_url: str, db: Session) -> list[dict]:
    """
    Extract and validate citations found within source content.
    Checks if cited sources are themselves credible.
    Returns: [{url, domain, is_credible}]
    """
    citation_urls = extract_urls_from_content(content)
    source_domain = extract_domain(source_url)

    citations = []
    for url in citation_urls[:10]:  # Limit to 10 citations per source
        domain = extract_domain(url)

        # Skip self-references and social media
        if domain == source_domain or not domain:
            continue
        if domain in SOCIAL_MEDIA_DOMAINS:
            continue

        # Quick credibility check (uses tier scoring)
        is_credible = False
        if is_authoritative_domain(domain):
            is_credible = True
        else:
            tier_info = get_domain_tier_score_wrapper(domain)
            if tier_info["domain_authority"] >= 20:  # Tier 3+ considered credible
                is_credible = True

        citations.append({
            "url": url,
            "domain": domain,
            "is_credible": is_credible,
        })

    return citations


# --- Content Quality Assessment ---

async def assess_content_quality(content: str) -> dict:
    """
    Use Gemini Flash to assess content quality.
    Returns: {score: 0.0-1.0, reasoning: str}
    Cost: ~$0.0001 per assessment
    """
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=GEMINI_API_KEY)

        prompt = f"""
You are a content quality assessment specialist. Evaluate the following article content.

CONTENT (first 4000 chars):
{content[:4000]}

Assess content quality on these criteria:
1. Depth: Does it provide substantive analysis or just surface-level info?
2. Evidence: Are claims backed by data, examples, or expert quotes?
3. Structure: Is it well-organized with clear sections?
4. Authority: Does the author demonstrate subject matter expertise?

Return JSON:
{{
  "score": 0.8,  // 0.0-1.0
  "reasoning": "Brief explanation of score"
}}

Only return the JSON, no other text.
"""

        # Use new async SDK with JSON response mode
        response = await client.aio.models.generate_content(
            model="gemini-2.5-flash",  # Current stable model (matches briefing_agent, feedback_service)
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.3,
                response_mime_type="application/json"  # Force JSON response
            )
        )

        # Parse JSON with error handling
        try:
            result = json.loads(response.text)
        except json.JSONDecodeError as e:
            logger.error(f"[GEMINI] Invalid JSON response: {response.text[:200]}")
            return {"score": 0.5, "reasoning": "JSON parse error"}

        logger.info(f"[GEMINI] Content quality score: {result.get('score', 0.5)}")

        return {
            "score": result.get("score", 0.5),
            "reasoning": result.get("reasoning", ""),
        }

    except Exception as e:
        logger.error(f"[GEMINI] Content quality assessment failed: {e}")
        # Fallback: neutral score
        return {"score": 0.5, "reasoning": "Assessment failed"}


# --- Credibility Scoring ---

async def calculate_credibility_score(
    source: dict,
    domain_metrics: dict,
    citations: list[dict],
    content_quality: dict
) -> float:
    """
    Multi-factor credibility scoring algorithm (Tier-Based, Rebalanced for Content Quality).
    Returns score 0.0-100.0. Minimum threshold: 60.0 to pass verification.

    REBALANCED FACTORS (Hybrid Approach - March 2026):
    - Content Quality (40 pts max) - PRIMARY SIGNAL - Gemini Flash assessment
    - Domain Tier (30 pts max) - Curated domain lists (195 domains)
    - Content Freshness (20 pts max) - Publish date recency
    - Internal Citations (10 pts max) - Backlink credibility

    Rationale: Domain authority is binary (195 domains = <0.001% coverage),
    so content quality becomes the most reliable credibility signal.
    """
    score = 0.0
    breakdown = {}  # For debugging

    # Factor 1: Domain Tier Score (30 points max, was 40)
    # Tier wrapper returns 0/10/20/30/40, normalize to 0-30 range
    raw_domain_score = domain_metrics.get("domain_authority", 0)
    domain_points = (raw_domain_score / 40.0) * 30.0  # Scale 0-40 to 0-30
    score += domain_points
    breakdown["domain"] = round(domain_points, 1)

    # Factor 2: Content Freshness (20 points max, unchanged)
    publish_date = extract_publish_date(source.get("content", ""), source.get("url", ""))
    freshness_points = 0.0
    if publish_date:
        days_old = (datetime.now() - publish_date).days
        if days_old <= 365:
            freshness_points = 20.0
        elif days_old <= 730:
            freshness_points = 13.0
        elif days_old <= 1095:
            freshness_points = 7.0
    score += freshness_points
    breakdown["freshness"] = round(freshness_points, 1)

    # Factor 3: Internal Citation Quality (10 points max, was 20)
    citation_points = 0.0
    if citations:
        credible_citation_count = sum(1 for c in citations if c.get("is_credible"))
        citation_points = min(10.0, credible_citation_count * 3.33)  # 3+ credible citations = max
    score += citation_points
    breakdown["citations"] = round(citation_points, 1)

    # Factor 4: Content Quality Signals (40 points max, was 20) - PRIMARY
    quality_score = content_quality.get("score", 0.5)
    quality_points = quality_score * 40.0  # Doubled weight
    score += quality_points
    breakdown["quality"] = round(quality_points, 1)

    final_score = min(100.0, score)

    # Log breakdown for debugging
    logger.debug(
        f"[SCORE BREAKDOWN] Total: {final_score:.1f}/100 "
        f"(Domain: {breakdown['domain']}, Quality: {breakdown['quality']}, "
        f"Freshness: {breakdown['freshness']}, Citations: {breakdown['citations']})"
    )

    return final_score


# --- Fact Extraction ---

async def extract_facts_from_source(source: dict) -> list[dict]:
    """
    Uses Gemini 2.0 Flash to extract verifiable factual claims.
    Returns: [{fact_text, fact_type, citation_anchor, confidence}]
    Cost: ~$0.0001 per source
    """
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=GEMINI_API_KEY)

        prompt = f"""
You are a fact extraction specialist. Extract ONLY verifiable factual claims from the following article.

SOURCE: {source['title']}
URL: {source['url']}

CONTENT:
{source.get('content', '')[:8000]}

Extract facts in the following categories:
1. STATISTICS: Specific numbers, percentages, dollar amounts
   Examples:
   - "67% of SMBs experienced a cyberattack in 2023"
   - "The average cost of a data breach is $4.35 million"
   - "Healthcare organizations face 3x more attacks than other sectors"

2. BENCHMARKS: Industry standards, thresholds, measurements
   Examples:
   - "Average churn rate of 5-7% for SaaS companies"
   - "Industry standard is 99.9% uptime"
   - "Typical response time under 200ms"

3. CASE_STUDIES: Real-world outcomes, company examples with specific results
   Examples:
   - "Shopify reduced page load time by 40% using edge caching"
   - "Acme Corp saved $500K annually after implementing automation"
   - "Netflix achieved 10x scale using microservices architecture"

4. EXPERT_QUOTES: Direct quotes from named experts, organizations, or studies
   Examples:
   - "According to Gartner analyst Jane Doe: 'Cloud adoption will reach 85% by 2025'"
   - "Security expert Bruce Schneier states: 'MFA reduces account takeovers by 99%'"
   - "Research from MIT found that..."

Return JSON array:
[
  {{
    "fact_text": "Exact claim extracted verbatim (include numbers, percentages, names, years)",
    "fact_type": "statistic|benchmark|case_study|expert_quote",
    "citation_anchor": "How to reference this (e.g., 'Source Name 2024', 'Gartner 2024', 'Company Blog')",
    "confidence": 0.9
  }}
]

CRITICAL RULES:
- Extract facts that include SPECIFIC NUMBERS, PERCENTAGES, DOLLAR AMOUNTS, or DIRECT QUOTES
- Do NOT extract vague claims like "many companies" or "recent studies show"
- Do NOT extract opinions, predictions, or subjective statements
- Include the YEAR if mentioned in the claim
- confidence: 0.6-1.0 based on how clearly stated and verifiable (be generous if fact is clear)
- Return empty array [] ONLY if absolutely no specific factual claims exist

WHAT TO EXTRACT: Any claim with a specific number, percentage, dollar amount, or attributable quote.
WHAT TO SKIP: Vague generalizations, opinions, predictions without data, author's personal views.

Only return the JSON array, no other text.
"""

        # Use new async SDK with JSON response mode
        response = await client.aio.models.generate_content(
            model="gemini-2.5-flash",  # Current stable model (matches briefing_agent, feedback_service)
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.3,
                response_mime_type="application/json"  # Force JSON array response
            )
        )

        # Parse JSON with error handling
        try:
            facts = json.loads(response.text)
            if not isinstance(facts, list):
                logger.warning(f"[GEMINI] Expected list, got {type(facts)}")
                facts = []
        except json.JSONDecodeError as e:
            logger.error(f"[GEMINI] Invalid JSON response for {source['url']}: {response.text[:200]}")
            return []

        logger.info(f"[GEMINI] Extracted {len(facts)} facts from {source['url']}")

        return facts

    except Exception as e:
        logger.error(f"[GEMINI] Fact extraction failed for {source['url']}: {e}")
        return []


# --- Database Storage ---

async def link_facts_to_sources(verified_sources: list, research_run_id: int, db: Session):
    """
    Extracts facts from each verified source and stores in FactCitation table.
    Only processes sources with credibility_score >= 60.0.
    """
    for source_row in verified_sources:
        if source_row.credibility_score < 60.0:
            continue  # Skip low-credibility sources

        source_dict = {
            "title": source_row.title,
            "url": source_row.url,
            "content": source_row.content_snippet,
        }

        facts = await extract_facts_from_source(source_dict)

        for fact in facts:
            # Lowered threshold from 0.7 to 0.6 (March 2026) to capture more facts
            if fact.get("confidence", 0) < 0.6:
                continue  # Only store moderate-to-high confidence facts

            # Calculate composite score: combines fact confidence with source credibility
            source_cred = source_row.credibility_score
            fact_conf = fact["confidence"]
            composite = (fact_conf * 100 + source_cred) / 2

            citation = FactCitation(
                verified_source_id=source_row.id,
                research_run_id=research_run_id,
                fact_text=fact["fact_text"],
                fact_type=fact["fact_type"],
                source_url=source_row.url,
                source_title=source_row.title,
                citation_anchor=fact["citation_anchor"],
                confidence_score=fact_conf,
                source_credibility=source_cred,
                composite_score=composite,
            )
            db.add(citation)

        db.commit()

    logger.info(f"[FACTS] Linked facts to {len(verified_sources)} verified sources")


# --- Main Entry Point ---

async def verify_sources(
    elite_competitors: list[dict],
    db: Session,
    profile_name: str = "default",
    research_run_id: int = 0
) -> dict:
    """
    Main source verification pipeline (Tier-Based, $0 cost).

    Input: elite_competitors from ResearchAgent [{title, url, content}]
    Output: {verified_sources: list[VerifiedSource], rejected_sources: list[dict]}

    Process:
    1. For each source, get domain tier score (no API calls)
    2. Extract internal citations and verify credibility
    3. Assess content quality via Gemini Flash
    4. Calculate multi-factor credibility score
    5. Save to VerifiedSource table if score >= 60.0

    Args:
        elite_competitors: List of sources from research phase
        db: Database session
        profile_name: Workspace identifier
        research_run_id: ID of the research run (defaults to 0 for standalone use)
    """
    verified_sources = []
    rejected_sources = []

    # Deduplicate by URL to prevent constraint violations
    seen_urls = set()
    unique_sources = []
    duplicate_count = 0
    for source in elite_competitors:
        url = source.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_sources.append(source)
        else:
            duplicate_count += 1
            logger.info(f"[DEDUP] Skipping duplicate URL: {url}")

    elite_competitors = unique_sources
    logger.info(f"[DEDUP] Processing {len(elite_competitors)} unique URLs (removed {duplicate_count} duplicates)")

    for i, source in enumerate(elite_competitors):
        domain = extract_domain(source["url"])

        logger.info(f"[VERIFY {i+1}/{len(elite_competitors)}] Processing {domain}...")

        # Step 1: Get domain tier score (no API cost)
        domain_metrics = get_domain_tier_score_wrapper(domain)

        # Step 2: Extract internal citations
        citations = await extract_internal_citations(source.get("content", ""), source["url"], db)

        # Step 3: Assess content quality
        content_quality = await assess_content_quality(source.get("content", ""))

        # Step 4: Calculate credibility score
        credibility_score = await calculate_credibility_score(
            source, domain_metrics, citations, content_quality
        )

        # Step 5: Determine verification status
        verification_passed = credibility_score >= 60.0
        rejection_reason = None if verification_passed else f"Score {credibility_score:.1f} < 60.0 threshold"

        # Step 6: Save to database
        publish_date = extract_publish_date(source.get("content", ""), source.get("url", ""))
        freshness_score = None
        if publish_date:
            days_old = (datetime.now() - publish_date).days
            freshness_score = max(0.0, 1.0 - (days_old / 1095.0))  # Decays over 3 years

        verified_source = VerifiedSource(
            research_run_id=research_run_id,  # Passed from caller (main.py)
            profile_name=profile_name,
            url=source["url"],
            title=source["title"],
            domain=domain,
            credibility_score=credibility_score,
            domain_authority=domain_metrics.get("domain_authority"),
            publish_date=publish_date,
            freshness_score=freshness_score,
            internal_citations_count=len(citations),
            has_credible_citations=any(c.get("is_credible") for c in citations),
            citation_urls_json=json.dumps([c["url"] for c in citations]),
            is_academic=is_academic_domain(domain),
            is_authoritative_domain=is_authoritative_domain(domain),
            content_snippet=source.get("content", "")[:500],  # Store first 500 chars
            verification_passed=verification_passed,
            rejection_reason=rejection_reason,
        )

        db.add(verified_source)
        db.commit()
        db.refresh(verified_source)

        if verification_passed:
            verified_sources.append(verified_source)
            logger.info(f"[VERIFIED] {domain} → Score: {credibility_score:.1f}/100")
        else:
            rejected_sources.append({
                "url": source["url"],
                "domain": domain,
                "score": credibility_score,
                "reason": rejection_reason,
            })
            logger.warning(f"[REJECTED] {domain} → {rejection_reason}")

    return {
        "verified_sources": verified_sources,
        "rejected_sources": rejected_sources,
    }
