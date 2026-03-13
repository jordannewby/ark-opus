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

logger = logging.getLogger(__name__)

# Constants for domain categorization
AUTHORITATIVE_DOMAINS = {
    # Government
    ".gov", ".mil",
    # Education
    ".edu", ".ac.uk", ".edu.au",
    # International organizations
    "who.int", "un.org", "oecd.org", "worldbank.org",
}

ACADEMIC_DOMAINS = {
    # Research journals
    "nature.com", "science.org", "sciencedirect.com", "springer.com",
    "ieee.org", "acm.org", "arxiv.org", "pubmed.gov", "nih.gov",
    # Academic publishers
    "wiley.com", "elsevier.com", "oxford.ac.uk", "cambridge.org",
}

MAJOR_PUBLISHERS = {
    # News
    "nytimes.com", "wsj.com", "ft.com", "economist.com", "reuters.com", "bloomberg.com",
    # Business/Tech
    "hbr.org", "mckinsey.com", "bcg.com", "gartner.com", "forrester.com",
    "techcrunch.com", "wired.com", "arstechnica.com",
    # Research orgs
    "pewresearch.org", "gallup.com", "statista.com",
}

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
    """Check if domain is authoritative (.gov, .edu, UN/WHO, etc.)."""
    for auth_domain in AUTHORITATIVE_DOMAINS:
        if domain.endswith(auth_domain) or domain == auth_domain:
            return True
    return False


def is_academic_domain(domain: str) -> bool:
    """Check if domain is academic (research journals, publishers)."""
    for acad_domain in ACADEMIC_DOMAINS:
        if acad_domain in domain:
            return True
    return False


def is_major_publisher(domain: str) -> bool:
    """Check if domain is a major publisher (NYT, WSJ, HBR, etc.)."""
    for pub_domain in MAJOR_PUBLISHERS:
        if pub_domain in domain:
            return True
    return False


def extract_publish_date(content: str) -> datetime | None:
    """
    Extract publish date from article content using regex patterns.
    Looks for common date formats in first 2000 chars.
    Returns None if not found.
    """
    # Common date patterns in article metadata/content
    patterns = [
        r"published[:\s]+(\d{4})-(\d{2})-(\d{2})",  # published: 2024-03-15
        r"(\d{4})-(\d{2})-(\d{2})",  # ISO format 2024-03-15
        r"(\w+ \d{1,2}, \d{4})",  # March 15, 2024
        r"(\d{1,2} \w+ \d{4})",  # 15 March 2024
    ]

    search_text = content[:2000].lower()

    for pattern in patterns:
        match = re.search(pattern, search_text)
        if match:
            try:
                date_str = match.group(0)
                # Try parsing with dateutil
                from dateutil import parser
                return parser.parse(date_str, fuzzy=True)
            except Exception:
                continue

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


# --- Domain Authority Fetching ---

def get_cached_domain_authority(domain: str, db: Session) -> int | None:
    """
    Get cached domain authority score for domain.
    Returns None if not cached or cache expired (>7 days).
    """
    cache_ttl_days = 7

    cached = db.query(DomainCredibilityCache).filter_by(domain=domain).first()
    if not cached:
        return None

    # Check if cache expired
    if cached.created_at < datetime.now() - timedelta(days=cache_ttl_days):
        return None

    return cached.domain_authority


async def get_domain_authority(domain: str, mcp_session, db: Session) -> dict:
    """
    Fetch domain authority metrics from DataForSEO backlinks API.
    Returns: {domain_authority: int, referring_domains: int}
    Cost: ~$0.002 per domain (cached for 7 days)
    """
    # Check cache first
    cached_da = get_cached_domain_authority(domain, db)
    if cached_da is not None:
        logger.info(f"[CACHE HIT] Domain authority for {domain}: {cached_da}")
        cached_entry = db.query(DomainCredibilityCache).filter_by(domain=domain).first()
        return {
            "domain_authority": cached_entry.domain_authority,
            "referring_domains": cached_entry.referring_domains,
        }

    # Fetch from DataForSEO
    try:
        logger.info(f"[DATAFORSEO] Fetching domain authority for {domain}...")

        # Call backlinks_domain_summary tool via MCP
        result = await mcp_session.call_tool(
            "backlinks_domain_summary",
            arguments={"target": domain}
        )

        # Parse result
        # Expected structure: {"rank": int, "backlinks": int, "referring_domains": int}
        result_data = result.content[0].text if hasattr(result, 'content') else result
        if isinstance(result_data, str):
            result_data = json.loads(result_data)

        # Extract metrics (DataForSEO rank is 0-100, we map to domain authority)
        rank = result_data.get("rank", 0)
        referring_domains = result_data.get("referring_domains", 0)

        # Map rank to domain authority (0-100 scale)
        domain_authority = min(100, int(rank))

        # Cache the result
        cache_entry = DomainCredibilityCache(
            domain=domain,
            domain_authority=domain_authority,
            referring_domains=referring_domains,
            is_authoritative=is_authoritative_domain(domain),
            is_academic=is_academic_domain(domain),
        )
        db.merge(cache_entry)
        db.commit()

        logger.info(f"[DATAFORSEO] {domain} → DA: {domain_authority}, Referring Domains: {referring_domains}")

        return {
            "domain_authority": domain_authority,
            "referring_domains": referring_domains,
        }

    except Exception as e:
        logger.warning(f"[DATAFORSEO] Failed to fetch domain authority for {domain}: {e}")
        # Return default values on error
        return {
            "domain_authority": None,
            "referring_domains": 0,
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

        # Quick credibility check (uses cached domain authority)
        is_credible = False
        if is_authoritative_domain(domain):
            is_credible = True
        else:
            cached_da = get_cached_domain_authority(domain, db)
            if cached_da and cached_da > 50:
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
        import google.generativeai as genai

        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-2.0-flash-exp")

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

        response = model.generate_content(prompt)
        result = json.loads(response.text)

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
    Multi-factor credibility scoring algorithm.
    Returns score 0.0-100.0. Minimum threshold: 60.0 to pass verification.

    Factors:
    - Domain Authority (40 pts max)
    - Domain Type (20 pts max)
    - Content Freshness (15 pts max)
    - Internal Citations (15 pts max)
    - Content Quality (10 pts max)
    """
    score = 0.0

    # Factor 1: Domain Authority (40 points max)
    if domain_metrics.get("domain_authority"):
        da = domain_metrics["domain_authority"]
        score += min(40.0, da * 0.4)  # DA of 100 = 40 points

    # Factor 2: Domain Type (20 points max)
    domain = extract_domain(source["url"])
    if is_authoritative_domain(domain):
        score += 20.0
    elif is_academic_domain(domain):
        score += 15.0
    elif is_major_publisher(domain):
        score += 10.0

    # Factor 3: Content Freshness (15 points max)
    publish_date = extract_publish_date(source.get("content", ""))
    if publish_date:
        days_old = (datetime.now() - publish_date).days
        if days_old <= 365:
            score += 15.0
        elif days_old <= 730:
            score += 10.0
        elif days_old <= 1095:
            score += 5.0

    # Factor 4: Internal Citation Quality (15 points max)
    if citations:
        credible_citation_count = sum(1 for c in citations if c.get("is_credible"))
        score += min(15.0, credible_citation_count * 5.0)  # 3+ credible citations = max

    # Factor 5: Content Quality Signals (10 points max)
    score += content_quality.get("score", 0.5) * 10.0  # Returns 0.0-1.0

    return min(100.0, score)


# --- Fact Extraction ---

async def extract_facts_from_source(source: dict) -> list[dict]:
    """
    Uses Gemini 2.5 Flash to extract verifiable factual claims.
    Returns: [{fact_text, fact_type, citation_anchor, confidence}]
    Cost: ~$0.0001 per source
    """
    try:
        import google.generativeai as genai

        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-2.0-flash-exp")

        prompt = f"""
You are a fact extraction specialist. Extract ONLY verifiable factual claims from the following article.

SOURCE: {source['title']}
URL: {source['url']}

CONTENT:
{source.get('content', '')[:8000]}

Extract facts in the following categories:
1. STATISTICS: Specific numbers, percentages, dollar amounts (e.g., "67% of SMBs report...")
2. BENCHMARKS: Industry standards, thresholds, measurements (e.g., "Average churn rate of 5-7%")
3. CASE_STUDIES: Real-world outcomes, company examples (e.g., "Shopify reduced load time by 40%")
4. EXPERT_QUOTES: Direct quotes from named experts (e.g., "According to Gartner analyst Jane Doe...")

Return JSON array:
[
  {{
    "fact_text": "Exact claim extracted verbatim",
    "fact_type": "statistic|benchmark|case_study|expert_quote",
    "citation_anchor": "How to reference this (e.g., 'According to Harvard Business Review 2024')",
    "confidence": 0.9
  }}
]

RULES:
- Extract ONLY claims that are specific and verifiable
- Do NOT extract opinions, generalizations, or vague statements
- Include the year if mentioned
- confidence: 0.0-1.0 based on how clearly the source states this fact
- Return empty array [] if no factual claims found

Only return the JSON array, no other text.
"""

        response = model.generate_content(prompt)
        facts = json.loads(response.text)

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
            if fact.get("confidence", 0) < 0.7:
                continue  # Only store high-confidence facts

            citation = FactCitation(
                verified_source_id=source_row.id,
                research_run_id=research_run_id,
                fact_text=fact["fact_text"],
                fact_type=fact["fact_type"],
                source_url=source_row.url,
                source_title=source_row.title,
                citation_anchor=fact["citation_anchor"],
                confidence_score=fact["confidence"],
            )
            db.add(citation)

        db.commit()

    logger.info(f"[FACTS] Linked facts to {len(verified_sources)} verified sources")


# --- Main Entry Point ---

async def verify_sources(
    elite_competitors: list[dict],
    mcp_session,
    db: Session,
    profile_name: str = "default"
) -> dict:
    """
    Main source verification pipeline.

    Input: elite_competitors from ResearchAgent [{title, url, content}]
    Output: {verified_sources: list[VerifiedSource], rejected_sources: list[dict]}

    Process:
    1. For each source, fetch domain authority (cached if available)
    2. Extract internal citations and verify credibility
    3. Assess content quality via Gemini Flash
    4. Calculate multi-factor credibility score
    5. Save to VerifiedSource table if score >= 60.0
    """
    verified_sources = []
    rejected_sources = []

    for i, source in enumerate(elite_competitors):
        domain = extract_domain(source["url"])

        logger.info(f"[VERIFY {i+1}/{len(elite_competitors)}] Processing {domain}...")

        # Step 1: Get domain authority
        domain_metrics = await get_domain_authority(domain, mcp_session, db)

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
        publish_date = extract_publish_date(source.get("content", ""))
        freshness_score = None
        if publish_date:
            days_old = (datetime.now() - publish_date).days
            freshness_score = max(0.0, 1.0 - (days_old / 1095.0))  # Decays over 3 years

        verified_source = VerifiedSource(
            research_run_id=0,  # Will be set when integrated into main.py
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
