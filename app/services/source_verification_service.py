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

from ..models import FactCitation, VerifiedSource
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
                # Allow up to 30 days in the future (timezone/pre-dating tolerance)
                if datetime(2000, 1, 1) <= parsed_date <= datetime.now() + timedelta(days=30):
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
                # Allow up to 30 days in the future (timezone/pre-dating tolerance)
                if datetime(2000, 1, 1) <= url_date <= datetime.now() + timedelta(days=30):
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
    logger.info(f"[TIER] {domain} -> Tier {tier_level} (Score: {score})")

    return {
        "tier_level": tier_level,
        "domain_authority": score,  # Keep same field name for compatibility
    }


# --- DataForSEO Domain Authority Lookup ---

async def fetch_domain_authority(domains: list[str], mcp_session) -> dict[str, dict]:
    """
    Batch-fetch domain authority metrics via DataForSEO Labs Domain Rank Overview.
    Returns: {domain: {top10_keywords, etv, total_keywords}}
    Cost: ~$0.0001 per domain
    """
    if not mcp_session or not domains:
        return {}

    try:
        result = await mcp_session.call_tool("domain_rank_overview", {"targets": domains[:10]})

        result_text = None
        if hasattr(result, 'content') and result.content:
            if isinstance(result.content, list) and len(result.content) > 0:
                result_text = result.content[0].text
            elif hasattr(result.content, 'text'):
                result_text = result.content.text
        elif hasattr(result, 'text'):
            result_text = result.text

        if not result_text:
            logger.warning("[AUTHORITY] Empty response from MCP")
            return {}

        data = json.loads(result_text)
        summaries = data.get("summaries", [])

        authority_map = {}
        for s in summaries:
            target = s.get("target", "")
            if target:
                authority_map[target] = {
                    "top10_keywords": s.get("top10_keywords", 0),
                    "etv": s.get("etv", 0),
                    "total_keywords": s.get("total_keywords", 0),
                }
                logger.info(f"[AUTHORITY] {target} -> Top10: {s.get('top10_keywords', 0)}, ETV: {s.get('etv', 0)}")

        return authority_map

    except Exception as e:
        logger.warning(f"[AUTHORITY] Fetch failed (non-critical): {e}")
        return {}


# --- SERP Ranking Cross-Reference ---

async def fetch_serp_ranking_urls(keyword: str, mcp_session) -> dict[str, int]:
    """
    Fetch SERP results for keyword and return URL->position map.
    Sources appearing in top SERP results get a credibility boost.
    Cost: $0.002 per query (uses existing MCP tool)
    """
    if not mcp_session or not keyword:
        return {}

    try:
        result = await mcp_session.call_tool("serp_organic_live_advanced", {
            "keyword": keyword,
            "location_code": 2840,
            "language_code": "en",
            "depth": 20,
        })

        result_text = None
        if hasattr(result, 'content') and result.content:
            if isinstance(result.content, list) and len(result.content) > 0:
                result_text = result.content[0].text
            elif hasattr(result.content, 'text'):
                result_text = result.content.text
        elif hasattr(result, 'text'):
            result_text = result.text

        if not result_text:
            return {}

        serp_data = json.loads(result_text)
        url_positions = {}

        tasks = serp_data.get("tasks", [])
        if tasks and tasks[0].get("result"):
            items = tasks[0]["result"][0].get("items", [])
            for item in items:
                if item.get("type") == "organic":
                    url = item.get("url", "")
                    rank_position = item.get("rank_absolute", item.get("rank_group", 99))
                    if url:
                        # Map by domain for flexible matching
                        domain = extract_domain(url)
                        if domain and domain not in url_positions:
                            url_positions[domain] = rank_position

        logger.info(f"[SERP] Fetched {len(url_positions)} ranking domains for '{keyword}'")
        return url_positions

    except Exception as e:
        logger.warning(f"[SERP] Ranking fetch failed (non-critical): {e}")
        return {}


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
            model="gemini-2.5-pro",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.3,
                response_mime_type="application/json"
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


async def detect_content_integrity(content: str) -> dict:
    """
    Adversarial trustworthiness check via Gemini Flash.
    Assesses 5 dimensions that distinguish genuine analysis from promotional/spam content.
    Returns: {integrity_score: 0.0-1.0, scores: dict, flags: [str]}
    Cost: ~$0.0001 per call (4000 chars to Gemini Flash)
    """
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=GEMINI_API_KEY)

        prompt = f"""You are a content integrity analyst. Today's date is {datetime.now().strftime('%B %d, %Y')}. Evaluate this article's TRUSTWORTHINESS, not its writing quality. A well-written advertisement is still untrustworthy.

CONTENT (first 4000 chars):
{content[:4000]}

Score each dimension 0.0-1.0:

1. promotional_intent: Is this trying to sell a product, service, or brand?
   1.0 = purely informational/educational with no commercial agenda
   0.5 = mentions products but primarily educational
   0.0 = blatant advertisement or company blog pushing their own tools

2. claim_sourcing: Does the article cite external evidence for its claims?
   1.0 = most claims reference specific studies, reports, or named experts
   0.5 = some claims sourced, others asserted without evidence
   0.0 = all claims are unsupported assertions ("many experts believe...")

3. specificity: Are claims specific and verifiable, or vague generalizations?
   1.0 = specific numbers, dates, named organizations, verifiable facts
   0.5 = mix of specific and vague claims
   0.0 = entirely vague ("companies are increasingly...", "many businesses...")

4. originality: Is this original analysis or a generic rehash?
   1.0 = unique perspective, original research, or novel analysis
   0.5 = synthesizes existing information with some original framing
   0.0 = generic advice anyone could write, no unique insight

5. editorial_standards: Does this show editorial rigor?
   1.0 = clear author attribution, methodology, sources section, publication context
   0.5 = some editorial signals (author name OR date OR sources)
   0.0 = anonymous, undated, no sources, no editorial oversight visible

Return JSON:
{{
  "scores": {{
    "promotional_intent": 0.8,
    "claim_sourcing": 0.7,
    "specificity": 0.6,
    "originality": 0.5,
    "editorial_standards": 0.7
  }},
  "integrity_score": 0.66,
  "flags": ["optional list of red flags found"]
}}

The integrity_score MUST be the average of all 5 dimension scores.
Only return the JSON, no other text."""

        response = await client.aio.models.generate_content(
            model="gemini-2.5-pro",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.3,
                response_mime_type="application/json"
            )
        )

        try:
            result = json.loads(response.text)
        except json.JSONDecodeError:
            logger.error(f"[INTEGRITY] Invalid JSON response: {response.text[:200]}")
            return {"integrity_score": 0.5, "scores": {}, "flags": ["JSON parse error"]}

        integrity_score = result.get("integrity_score", 0.5)
        # Validate: recalculate average if scores dict is present
        scores = result.get("scores", {})
        if scores and len(scores) == 5:
            calculated_avg = sum(scores.values()) / 5
            # Use calculated average if Gemini's reported average is off
            if abs(calculated_avg - integrity_score) > 0.1:
                integrity_score = calculated_avg

        logger.info(f"[INTEGRITY] Score: {integrity_score:.2f} | Flags: {result.get('flags', [])}")

        return {
            "integrity_score": round(integrity_score, 3),
            "scores": scores,
            "flags": result.get("flags", []),
        }

    except Exception as e:
        logger.error(f"[INTEGRITY] Content integrity check failed: {e}")
        return {"integrity_score": 0.5, "scores": {}, "flags": ["Assessment failed"]}


# --- Credibility Scoring ---

async def calculate_credibility_score(
    source: dict,
    domain_metrics: dict,
    citations: list[dict],
    content_quality: dict,
    content_integrity: dict | None = None,
    backlinks_authority: dict | None = None,
    serp_position: int | None = None,
) -> float:
    """
    9-factor credibility scoring algorithm with spam penalty.
    Returns score 0.0-100.0. Minimum threshold: 45.0 to pass verification.

    FACTORS (March 2026 v2 — enhanced with DataForSEO + SERP):
    - Content Integrity (25 pts) - "is this trustworthy?" (Gemini)
    - Content Quality (15 pts) - "is this well-written?" (Gemini)
    - Domain Tier + Authority (20 pts) - Curated tiers + DataForSEO Domain Rank fallback
    - Content Freshness (15 pts) - Exa publishedDate primary, regex fallback
    - SERP Ranking (10 pts) - Source domain appears in top SERP results (DataForSEO)
    - Internal Citations (5 pts) - Backlink credibility
    - Author Attribution (5 pts) - Exa author field (E-E-A-T signal)
    - Topical Relevance (5 pts) - Exa search score
    - Spam Penalty (-10 pts) - DataForSEO spam score deduction
    """
    score = 0.0
    breakdown = {}

    # Factor 1: Content Integrity — "is this trustworthy?" (25 pts max)
    if content_integrity:
        integrity = content_integrity.get("integrity_score", 0.5)
    else:
        integrity = 0.5
    integrity_points = integrity * 25.0
    score += integrity_points
    breakdown["integrity"] = round(integrity_points, 1)

    # Factor 2: Content Quality — "is this well-written?" (15 pts max)
    quality_score = content_quality.get("score", 0.5)
    quality_points = quality_score * 15.0
    score += quality_points
    breakdown["quality"] = round(quality_points, 1)

    # Factor 3: Domain Tier + DataForSEO Authority (20 pts max)
    raw_domain_score = domain_metrics.get("domain_authority", 0)
    tier_level = domain_metrics.get("tier_level", 0)

    if tier_level > 0:
        # Known domain — use curated tier score (scaled 0-40 to 0-20)
        domain_points = (raw_domain_score / 40.0) * 20.0
    elif backlinks_authority:
        # Unknown domain — use DataForSEO Labs top10 keyword count as authority proxy
        top10 = backlinks_authority.get("top10_keywords", 0)
        if top10 >= 10000:
            domain_points = 16.0  # Major authority (nist.gov-level)
        elif top10 >= 1000:
            domain_points = 12.0  # Strong authority (krebsonsecurity-level)
        elif top10 >= 100:
            domain_points = 8.0   # Moderate authority
        elif top10 >= 10:
            domain_points = 5.0   # Some presence
        else:
            domain_points = 2.0   # Minimal but exists
    else:
        domain_points = 0.0

    score += domain_points
    breakdown["domain"] = round(domain_points, 1)

    # Factor 4: Content Freshness (15 pts max)
    publish_date = None
    exa_date_str = source.get("published_date")
    if exa_date_str:
        try:
            clean_date = exa_date_str.replace("Z", "+00:00") if exa_date_str.endswith("Z") else exa_date_str
            publish_date = datetime.fromisoformat(clean_date).replace(tzinfo=None)
            # Allow up to 30 days in the future (timezone/pre-dating tolerance)
            if not (datetime(2000, 1, 1) <= publish_date <= datetime.now() + timedelta(days=30)):
                publish_date = None
        except Exception:
            publish_date = None

    if not publish_date:
        publish_date = extract_publish_date(source.get("content", ""), source.get("url", ""))

    freshness_points = 0.0
    if publish_date:
        days_old = (datetime.now() - publish_date).days
        if days_old <= 365:
            freshness_points = 15.0
        elif days_old <= 730:
            freshness_points = 10.0
        elif days_old <= 1095:
            freshness_points = 5.0
    score += freshness_points
    breakdown["freshness"] = round(freshness_points, 1)

    # Factor 5: SERP Ranking (10 pts max) — source domain ranks for target keyword
    serp_points = 0.0
    if serp_position is not None:
        if serp_position <= 5:
            serp_points = 10.0
        elif serp_position <= 10:
            serp_points = 7.0
        elif serp_position <= 20:
            serp_points = 4.0
    score += serp_points
    breakdown["serp"] = round(serp_points, 1)

    # Factor 6: Internal Citation Quality (5 pts max)
    citation_points = 0.0
    if citations:
        credible_citation_count = sum(1 for c in citations if c.get("is_credible"))
        citation_points = min(5.0, credible_citation_count * 1.67)
    score += citation_points
    breakdown["citations"] = round(citation_points, 1)

    # Factor 7: Author Attribution (5 pts) — E-E-A-T signal
    has_author = bool(source.get("author"))
    author_points = 5.0 if has_author else 0.0
    score += author_points
    breakdown["author"] = round(author_points, 1)

    # Factor 8: Topical Relevance (5 pts) — Exa neural search score
    exa_score = source.get("exa_score")
    relevance_points = min(5.0, (float(exa_score) if exa_score else 0) * 5.0)
    score += relevance_points
    breakdown["relevance"] = round(relevance_points, 1)

    final_score = max(0.0, min(100.0, score))

    # Log full breakdown for debugging
    logger.info(
        f"[SCORE] {final_score:.1f}/100 "
        f"(Integrity:{breakdown['integrity']} Quality:{breakdown['quality']} "
        f"Domain:{breakdown['domain']} Fresh:{breakdown['freshness']} "
        f"SERP:{breakdown['serp']} Cite:{breakdown['citations']} "
        f"Author:{breakdown['author']} Relevance:{breakdown['relevance']})"
    )

    return final_score


# --- Borderline Rescue ---

def calculate_rescue_bonus(source: dict, content_integrity: dict | None) -> float:
    """
    Borderline rescue for sources scoring 35.0-44.9.
    Only applies when promotional_intent >= 0.6 (non-salesy).

    Three supplementary signals (max +8 pts, $0 cost):
    - Content depth (word count): >2000w +3, >1500w +2, >1000w +1
    - Technical content (code blocks): +3 if found
    - External reference density: 5+ domains +2, 3+ domains +1
    """
    if not content_integrity:
        return 0.0

    scores = content_integrity.get("scores", {})
    promotional_intent = scores.get("promotional_intent", 0.0)

    if promotional_intent < 0.6:
        logger.info(f"[RESCUE] Skipped -- promotional_intent {promotional_intent:.2f} < 0.6")
        return 0.0

    content = source.get("content", "")
    bonus = 0.0
    reasons = []

    # Signal 1: Content depth (word count)
    word_count = len(content.split())
    if word_count > 2000:
        bonus += 3.0
        reasons.append(f"depth:{word_count}w(+3)")
    elif word_count > 1500:
        bonus += 2.0
        reasons.append(f"depth:{word_count}w(+2)")
    elif word_count > 1000:
        bonus += 1.0
        reasons.append(f"depth:{word_count}w(+1)")

    # Signal 2: Technical content (code blocks)
    code_patterns = [r'<pre\b', r'<code\b', r'```']
    has_code = any(re.search(p, content) for p in code_patterns)
    if has_code:
        bonus += 3.0
        reasons.append("code_blocks(+3)")

    # Signal 3: External reference density
    all_urls = extract_urls_from_content(content)
    source_domain = extract_domain(source.get("url", ""))
    external_domains = set()
    for url in all_urls:
        domain = extract_domain(url)
        if domain and domain != source_domain:
            external_domains.add(domain)

    if len(external_domains) >= 5:
        bonus += 2.0
        reasons.append(f"ext_refs:{len(external_domains)}(+2)")
    elif len(external_domains) >= 3:
        bonus += 1.0
        reasons.append(f"ext_refs:{len(external_domains)}(+1)")

    if bonus > 0:
        logger.info(f"[RESCUE] Bonus: +{bonus:.0f} pts | {', '.join(reasons)}")

    return min(8.0, bonus)


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
- Extract facts that include SPECIFIC NUMBERS, PERCENTAGES, DOLLAR AMOUNTS, or DIRECT QUOTES about the topic
- Do NOT extract vague claims like "many companies" or "recent studies show"
- Do NOT extract opinions, predictions, or subjective statements
- NEVER extract article metadata: publication dates, update dates, reading times ("X min read"), word counts, author names, or bylines
- NEVER extract navigation text, headers, footers, or boilerplate content
- Include the YEAR if mentioned in the claim
- confidence: 0.6-1.0 based on how clearly stated and verifiable (be generous if fact is clear)
- Return empty array [] if no specific factual claims about the topic exist

WHAT TO EXTRACT: Claims about the subject matter with specific numbers, percentages, dollar amounts, or attributable quotes.
WHAT TO SKIP: Article metadata (dates, "X min read", author info), vague generalizations, opinions, predictions without data.

Only return the JSON array, no other text.
"""

        # Use new async SDK with JSON response mode
        response = await client.aio.models.generate_content(
            model="gemini-2.5-pro",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.3,
                response_mime_type="application/json"
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

        # Post-filter: strip metadata that Gemini sometimes extracts despite prompt instructions
        _metadata_patterns = re.compile(
            r'(min read|published on|updated on|last modified|posted on|written by|author:|byline)',
            re.IGNORECASE
        )
        filtered = [f for f in facts if not _metadata_patterns.search(f.get("fact_text", ""))]
        if len(filtered) < len(facts):
            logger.info(f"[GEMINI] Filtered {len(facts) - len(filtered)} metadata entries from {source['url']}")
        facts = filtered

        logger.info(f"[GEMINI] Extracted {len(facts)} facts from {source['url']}")

        return facts

    except Exception as e:
        logger.error(f"[GEMINI] Fact extraction failed for {source['url']}: {e}")
        return []


# --- Cross-Source Fact Consensus ---

def _extract_numbers(text: str) -> set[str]:
    """Extract all numbers/percentages/dollar amounts from text for comparison."""
    return set(re.findall(r'\$?[\d,]+\.?\d*%?', text))


def _extract_key_terms(text: str) -> set[str]:
    """Extract significant terms (3+ chars, not stopwords) for comparison."""
    stopwords = {"the", "and", "for", "that", "with", "this", "from", "are", "was", "were",
                 "has", "have", "had", "not", "but", "can", "will", "more", "than", "also",
                 "their", "they", "been", "which", "about", "into", "over", "such"}
    words = re.findall(r'[a-zA-Z]{3,}', text.lower())
    return {w for w in words if w not in stopwords}


def score_fact_consensus(all_citations: list) -> dict[int, int]:
    """
    For each fact, count how many OTHER sources independently cite similar claims.

    Similarity heuristic (no LLM needed):
    1. Extract all numbers from fact_text (percentages, dollars, counts)
    2. Extract key terms (proper nouns, technical terms)
    3. Two facts are "similar" if they share 1+ number AND 2+ key terms
    4. Facts from the SAME source don't count as corroboration

    Returns: {fact_citation.id: consensus_count}
    """
    if not all_citations:
        return {}

    # Pre-compute number and term sets for each citation
    parsed = []
    for cite in all_citations:
        parsed.append({
            "id": cite.id,
            "source_url": cite.source_url,
            "numbers": _extract_numbers(cite.fact_text),
            "terms": _extract_key_terms(cite.fact_text),
        })

    consensus_map = {}
    for i, a in enumerate(parsed):
        count = 1  # Counts itself
        for j, b in enumerate(parsed):
            if i == j:
                continue
            # Must be from a different source
            if a["source_url"] == b["source_url"]:
                continue
            # Similarity: share 1+ number AND 2+ key terms
            shared_numbers = a["numbers"] & b["numbers"]
            shared_terms = a["terms"] & b["terms"]
            if len(shared_numbers) >= 1 and len(shared_terms) >= 2:
                count += 1
        consensus_map[a["id"]] = count

    return consensus_map


# --- Database Storage ---

async def link_facts_to_sources(verified_sources: list, research_run_id: int, db: Session, elite_competitors: list[dict] | None = None):
    """
    Extracts facts from each verified source and stores in FactCitation table.
    Only processes sources with credibility_score >= 45.0.
    After extraction, runs cross-source consensus scoring to boost corroborated facts.
    """
    # Build URL -> full content mapping for fact extraction
    full_content_map = {}
    if elite_competitors:
        for comp in elite_competitors:
            url = comp.get("url", "")
            if url:
                full_content_map[url] = comp.get("content", "")

    all_new_citations = []

    for source_row in verified_sources:
        if source_row.credibility_score < 45.0:
            continue

        full_content = full_content_map.get(source_row.url, "") or source_row.content_snippet or ""

        source_dict = {
            "title": source_row.title,
            "url": source_row.url,
            "content": full_content,
        }

        facts = await extract_facts_from_source(source_dict)

        for fact in facts:
            if fact.get("confidence", 0) < 0.6:
                continue

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
            db.flush()  # Get the ID assigned before consensus scoring
            all_new_citations.append(citation)

    # --- Cross-source consensus scoring ---
    if all_new_citations:
        consensus_map = score_fact_consensus(all_new_citations)

        boosted = 0
        for citation in all_new_citations:
            count = consensus_map.get(citation.id, 1)
            citation.consensus_count = count
            # Adjust composite score based on consensus
            if count >= 3:
                citation.composite_score = min(100.0, citation.composite_score * 1.3)
                boosted += 1
            elif count >= 2:
                citation.composite_score = min(100.0, citation.composite_score * 1.15)
                boosted += 1
            elif count == 1:
                citation.composite_score = citation.composite_score * 0.85

        if boosted:
            logger.info(f"[CONSENSUS] {boosted}/{len(all_new_citations)} facts corroborated by multiple sources")

    db.commit()
    logger.info(f"[FACTS] Linked {len(all_new_citations)} facts to {len(verified_sources)} verified sources")


# --- Main Entry Point ---

async def verify_sources(
    elite_competitors: list[dict],
    db: Session,
    profile_name: str = "default",
    research_run_id: int = 0,
    mcp_session=None,
    keyword: str = "",
) -> dict:
    """
    Main source verification pipeline (9-factor scoring + spam penalty).

    Input: elite_competitors from ResearchAgent [{title, url, content, published_date, author, exa_score}]
    Output: {verified_sources: list[VerifiedSource], rejected_sources: list[dict]}

    Process:
    1. Deduplicate sources by URL
    2. Pre-compute local signals (domain tier, citations) -- free, instant
    3. Fetch DataForSEO backlinks authority + SERP rankings -- parallel, ~$0.04
    4. Batch Gemini calls (quality + integrity) via asyncio.gather -- parallel
    5. Calculate 9-factor credibility score per source (with spam penalty)
    6. Save to VerifiedSource table if score >= 45.0
    """
    import asyncio

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

    # --- Phase 1: Pre-compute local signals (free, instant) ---
    local_signals = []
    for source in elite_competitors:
        domain = extract_domain(source["url"])
        domain_metrics = get_domain_tier_score_wrapper(domain)
        citations = await extract_internal_citations(source.get("content", ""), source["url"], db)
        local_signals.append({
            "domain": domain,
            "domain_metrics": domain_metrics,
            "citations": citations,
        })

    # --- Phase 1.5: Fetch DataForSEO signals in parallel (backlinks + SERP) ---
    all_domains = list({ls["domain"] for ls in local_signals if ls["domain"]})
    # Also include parent domains for subdomain lookups (nvlpubs.nist.gov -> nist.gov)
    parent_domains = set()
    for d in all_domains:
        if d.count(".") >= 2:
            parent_domains.add(".".join(d.split(".")[-2:]))
    authority_targets = list(set(all_domains) | parent_domains)

    backlinks_map = {}
    serp_rankings = {}

    if mcp_session:
        try:
            backlinks_map = await fetch_domain_authority(authority_targets, mcp_session)
        except Exception as e:
            logger.warning(f"[VERIFY] Domain authority fetch failed (non-critical): {e}")
        try:
            if keyword:
                serp_rankings = await fetch_serp_ranking_urls(keyword, mcp_session)
        except Exception as e:
            logger.warning(f"[VERIFY] SERP fetch failed (non-critical): {e}")

    # --- Phase 2: Batch Gemini calls in parallel (quality + integrity) ---
    content_list = [s.get("content", "") for s in elite_competitors]

    # Fire all Gemini calls at once -- 2 calls per source, all sources in parallel
    quality_tasks = [assess_content_quality(content) for content in content_list]
    integrity_tasks = [detect_content_integrity(content) for content in content_list]

    logger.info(f"[VERIFY] Launching {len(quality_tasks) + len(integrity_tasks)} parallel Gemini calls...")
    all_results = await asyncio.gather(*quality_tasks, *integrity_tasks, return_exceptions=True)

    # Split results: first N are quality, next N are integrity
    n = len(elite_competitors)
    quality_results = []
    integrity_results = []
    for i in range(n):
        qr = all_results[i]
        ir = all_results[n + i]
        quality_results.append(qr if not isinstance(qr, Exception) else {"score": 0.5, "reasoning": "Error"})
        integrity_results.append(ir if not isinstance(ir, Exception) else {"integrity_score": 0.5, "scores": {}, "flags": ["Error"]})

    # --- Phase 3: Score and persist ---
    for i, source in enumerate(elite_competitors):
        domain = local_signals[i]["domain"]
        domain_metrics = local_signals[i]["domain_metrics"]
        citations = local_signals[i]["citations"]
        content_quality = quality_results[i]
        content_integrity = integrity_results[i]

        # Lookup DataForSEO signals for this domain (with parent domain fallback)
        bl_authority = backlinks_map.get(domain)
        serp_pos = serp_rankings.get(domain)

        # Subdomain fallback: nvlpubs.nist.gov -> nist.gov
        if (not bl_authority or not serp_pos) and domain.count(".") >= 2:
            parts = domain.split(".")
            parent = ".".join(parts[-2:])  # e.g., nist.gov
            if not bl_authority:
                bl_authority = backlinks_map.get(parent)
            if not serp_pos:
                serp_pos = serp_rankings.get(parent)

        # Calculate 9-factor credibility score (with spam penalty)
        credibility_score = await calculate_credibility_score(
            source, domain_metrics, citations, content_quality,
            content_integrity=content_integrity,
            backlinks_authority=bl_authority,
            serp_position=serp_pos,
        )

        # Borderline rescue: sources scoring 35.0-44.9 get supplementary signal check
        if 35.0 <= credibility_score < 45.0:
            rescue_bonus = calculate_rescue_bonus(source, content_integrity)
            if rescue_bonus > 0:
                original_score = credibility_score
                credibility_score = min(100.0, credibility_score + rescue_bonus)
                if credibility_score >= 45.0:
                    logger.info(
                        f"[RESCUED] {extract_domain(source['url'])} "
                        f"rescued from {original_score:.1f} to {credibility_score:.1f} "
                        f"(+{rescue_bonus:.0f} borderline bonus)"
                    )

        verification_passed = credibility_score >= 45.0
        rejection_reason = None if verification_passed else f"Score {credibility_score:.1f} < 45.0 threshold"

        # Resolve publish date: Exa primary, regex fallback
        publish_date = None
        exa_date_str = source.get("published_date")
        if exa_date_str:
            try:
                clean_date = exa_date_str.replace("Z", "+00:00") if exa_date_str.endswith("Z") else exa_date_str
                publish_date = datetime.fromisoformat(clean_date).replace(tzinfo=None)
                # Allow up to 30 days in the future (timezone/pre-dating tolerance)
                if not (datetime(2000, 1, 1) <= publish_date <= datetime.now() + timedelta(days=30)):
                    publish_date = None
            except Exception:
                publish_date = None
        if not publish_date:
            publish_date = extract_publish_date(source.get("content", ""), source.get("url", ""))

        freshness_score = None
        if publish_date:
            days_old = (datetime.now() - publish_date).days
            freshness_score = max(0.0, 1.0 - (days_old / 1095.0))

        verified_source = VerifiedSource(
            research_run_id=research_run_id,
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
            content_snippet=source.get("content", "")[:2000],  # Increased from 500 for better fallback
            verification_passed=verification_passed,
            rejection_reason=rejection_reason,
        )

        db.add(verified_source)
        db.commit()
        db.refresh(verified_source)

        if verification_passed:
            verified_sources.append(verified_source)
            logger.info(f"[VERIFIED] {domain} -> Score: {credibility_score:.1f}/100")
        else:
            rejected_sources.append({
                "url": source["url"],
                "domain": domain,
                "score": credibility_score,
                "reason": rejection_reason,
            })
            logger.warning(f"[REJECTED] {domain} -> {rejection_reason}")

    return {
        "verified_sources": verified_sources,
        "rejected_sources": rejected_sources,
    }
