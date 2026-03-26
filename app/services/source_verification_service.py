"""
Source Verification Service - Phase 1.5

Validates credibility of research sources using multi-factor scoring:
- Domain authority (DataForSEO)
- Domain type (.gov, .edu, research journals)
- Content freshness (publish date)
- Internal citations (backlink verification)
- Content quality (DeepSeek Reasoner)

Extracts factual claims and maps them to verified sources for citation injection.
"""

import json
import logging
import re
from datetime import datetime, timedelta
from urllib.parse import urlparse

import httpx
from sqlalchemy.orm import Session

from ..models import FactCitation, VerifiedSource
from ..settings import (
    DEEPSEEK_API_KEY, DEEPSEEK_REASONER_MODEL, DEEPSEEK_TIMEOUT, DEEPSEEK_REASONER_TIMEOUT,
    SOURCE_CREDIBILITY_THRESHOLD, SOURCE_THRESHOLD_DECAY, MAX_VERIFICATION_ITERATIONS,
    BLOG_DOMAIN_PENALTY, BLOG_PATH_PENALTY, UNSOURCED_CLAIMS_PENALTY,
)
from ..domain_tiers import get_domain_tier_score
from .research_service import mcp_call_with_retry

DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"

logger = logging.getLogger(__name__)

# Constants for domain categorization
# Note: AUTHORITATIVE_DOMAINS, ACADEMIC_DOMAINS, and MAJOR_PUBLISHERS removed
# Replaced with tiered domain system in domain_tiers.py

SOCIAL_MEDIA_DOMAINS = {
    "facebook.com", "twitter.com", "x.com", "linkedin.com", "instagram.com",
    "youtube.com", "tiktok.com", "reddit.com", "pinterest.com", "snapchat.com",
}


# --- Citation Laundering Detection ---

# Maps named research organizations to their canonical domains.
# When a fact says "Gartner reports X" but the source is nuconet.com,
# the fact is flagged as laundered through an intermediary.
KNOWN_RESEARCH_ORGS: dict[str, list[str]] = {
    # Analyst firms
    "gartner": ["gartner.com"],
    "forrester": ["forrester.com"],
    "idc": ["idc.com"],
    "mckinsey": ["mckinsey.com"],
    # Consulting / Big 4
    "deloitte": ["deloitte.com"],
    "pwc": ["pwc.com"],
    "ey": ["ey.com"],
    "kpmg": ["kpmg.com"],
    "accenture": ["accenture.com"],
    # Tech giants with research arms
    "salesforce": ["salesforce.com"],
    "ibm": ["ibm.com"],
    "microsoft": ["microsoft.com"],
    "google": ["google.com", "blog.google", "cloud.google.com", "deepmind.com"],
    "cisco": ["cisco.com"],
    "verizon": ["verizon.com", "verizonbusiness.com"],
    "hp": ["hp.com", "hpe.com"],
    "dell": ["dell.com"],
    "oracle": ["oracle.com"],
    "amazon": ["aws.amazon.com", "aboutamazon.com"],
    "meta": ["meta.com", "ai.meta.com", "engineering.fb.com"],
    # Cybersecurity vendors
    "crowdstrike": ["crowdstrike.com"],
    "palo alto": ["paloaltonetworks.com"],
    "mandiant": ["mandiant.com"],
    "rapid7": ["rapid7.com"],
    "splunk": ["splunk.com"],
    "sentinelone": ["sentinelone.com"],
    "sophos": ["sophos.com"],
    # Government / standards
    "nist": ["nist.gov", "nvd.nist.gov"],
    "cisa": ["cisa.gov"],
    "fbi": ["fbi.gov"],
    "sec": ["sec.gov"],
    "ftc": ["ftc.gov"],
    # Academic / research
    "stanford": ["stanford.edu", "hai.stanford.edu"],
    "mit": ["mit.edu"],
    "carnegie mellon": ["cmu.edu"],
    "harvard": ["harvard.edu"],
    "oxford": ["oxford.ac.uk"],
    # Industry-specific research
    "ponemon": ["ponemon.org"],
    "sans": ["sans.org"],
    "owasp": ["owasp.org"],
    "isaca": ["isaca.org"],
    # HR / SMB research
    "gusto": ["gusto.com"],
    # News / media (with research divisions)
    "pew": ["pewresearch.org"],
    "gallup": ["gallup.com"],
    "statista": ["statista.com"],
    # US government agencies
    "u.s. chamber": ["uschamber.com"],
    "us chamber": ["uschamber.com"],
    "chamber of commerce": ["uschamber.com"],
}

# Pre-compiled regex: match any known org name as a whole word (case-insensitive)
_ORG_PATTERN = re.compile(
    r'\b(' + '|'.join(re.escape(org) for org in sorted(KNOWN_RESEARCH_ORGS.keys(), key=len, reverse=True)) + r')\b',
    re.IGNORECASE,
)


def detect_citation_laundering(fact_text: str, source_domain: str, citation_anchor: str = "") -> dict:
    """
    Detect when a fact attributes a claim to a named research org but the
    source domain doesn't belong to that org.  Scans both fact_text AND
    citation_anchor (e.g. "Gartner 2024") for org name mentions.

    Example:
        fact_text: "40% of SMBs will use AI agents"
        citation_anchor: "Gartner 2024"
        source_domain: "nuconet.com"
        → is_laundered=True, claimed_org="gartner"

    Returns: {is_laundered: bool, claimed_org: str | None, source_domain: str}
    """
    combined_text = fact_text + (" " + citation_anchor if citation_anchor else "")
    matches = _ORG_PATTERN.findall(combined_text)
    if not matches:
        return {"is_laundered": False, "claimed_org": None, "source_domain": source_domain}

    source_domain_lower = source_domain.lower()

    for org_name in matches:
        org_key = org_name.lower()
        canonical_domains = KNOWN_RESEARCH_ORGS.get(org_key, [])
        if not canonical_domains:
            continue

        # Check if source domain matches any canonical domain for this org
        domain_match = False
        for canon in canonical_domains:
            if source_domain_lower == canon or source_domain_lower.endswith("." + canon):
                domain_match = True
                break

        if not domain_match:
            # The fact claims org X but the source is not org X's domain
            return {
                "is_laundered": True,
                "claimed_org": org_key,
                "source_domain": source_domain,
            }

    return {"is_laundered": False, "claimed_org": None, "source_domain": source_domain}


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


def validate_url_format(url: str, expected_domain: str) -> bool:
    """
    Validate URL has proper format and netloc matches expected domain.
    Catches spoofed URLs like 'nist.gov.fakesite.com' claiming Tier 1 status.
    """
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        if not parsed.netloc:
            return False
        actual = parsed.netloc.lower()
        if actual.startswith("www."):
            actual = actual[4:]
        return actual == expected_domain or actual.endswith("." + expected_domain)
    except Exception:
        return False


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

    Hybrid Approach (March 2026): Improved to capture more date formats + OpenGraph meta tags.
    """
    # Priority 1: Check OpenGraph meta tags (high confidence)
    og_patterns = [
        r'<meta\s+property=["\']article:published_time["\']\s+content=["\']([^"\']+)["\']',
        r'<meta\s+property=["\']og:published_time["\']\s+content=["\']([^"\']+)["\']',
        r'<meta\s+name=["\']publish[_-]?date["\']\s+content=["\']([^"\']+)["\']',
        r'<meta\s+name=["\']date["\']\s+content=["\']([^"\']+)["\']',
    ]

    search_text = content[:5000]
    for og_pattern in og_patterns:
        og_match = re.search(og_pattern, search_text, re.IGNORECASE)
        if og_match:
            try:
                date_str = og_match.group(1)
                clean_date = date_str.replace("Z", "+00:00") if date_str.endswith("Z") else date_str
                parsed_date = datetime.fromisoformat(clean_date).replace(tzinfo=None)
                if datetime(2000, 1, 1) <= parsed_date <= datetime.now() + timedelta(days=30):
                    return parsed_date
            except Exception:
                continue

    # Priority 2: Enhanced date patterns covering more metadata formats
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
        result = await mcp_call_with_retry(mcp_session, "domain_rank_overview", {"targets": domains[:10]})

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
        result = await mcp_call_with_retry(mcp_session, "serp_organic_live_advanced", {
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
    Use DeepSeek Reasoner to assess content quality.
    Returns: {score: 0.0-1.0, reasoning: str}
    Cost: ~$0.00005 per assessment
    """
    try:
        prompt = f"""You are a content quality assessment specialist. Evaluate the following article content.

CONTENT (first 4000 chars):
{content[:4000]}

Assess content quality on these criteria:
1. Depth: Does it provide substantive analysis or just surface-level info?
2. Evidence: Are claims backed by data, examples, or expert quotes?
3. Structure: Is it well-organized with clear sections?
4. Actionability: Does the content provide concrete takeaways, practical guidance, or implementable advice?

Return JSON:
{{
  "score": 0.8,
  "reasoning": "Brief explanation of score"
}}

Only return the JSON, no other text."""

        headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": DEEPSEEK_REASONER_MODEL,
            "messages": [
                {"role": "system", "content": "You output valid JSON ONLY."},
                {"role": "user", "content": prompt}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.3,
        }

        async with httpx.AsyncClient(timeout=DEEPSEEK_TIMEOUT) as client:
            resp = await client.post(DEEPSEEK_API_URL, headers=headers, json=payload)
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"].strip()

        # Parse JSON with error handling
        try:
            result = json.loads(text)
        except json.JSONDecodeError:
            logger.error(f"[DEEPSEEK] Invalid JSON response: {text[:200]}")
            return {"score": 0.5, "reasoning": "JSON parse error"}

        logger.info(f"[DEEPSEEK] Content quality score: {result.get('score', 0.5)}")

        return {
            "score": result.get("score", 0.5),
            "reasoning": result.get("reasoning", ""),
        }

    except Exception as e:
        logger.error(f"[DEEPSEEK] Content quality assessment failed: {e}")
        # Fallback: neutral score
        return {"score": 0.5, "reasoning": "Assessment failed"}


async def detect_content_integrity(content: str) -> dict:
    """
    Adversarial trustworthiness check via DeepSeek Reasoner.
    Assesses 5 dimensions that distinguish genuine analysis from promotional/spam content.
    Returns: {integrity_score: 0.0-1.0, scores: dict, flags: [str]}
    Cost: ~$0.00005 per call (4000 chars to DeepSeek Reasoner)
    """
    try:
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
   1.0 = clear methodology, sources section, publication date, structured format
   0.5 = some editorial signals (date OR sources OR structured sections)
   0.0 = undated, no sources, no methodology, no editorial oversight visible

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

        headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": DEEPSEEK_REASONER_MODEL,
            "messages": [
                {"role": "system", "content": "You output valid JSON ONLY."},
                {"role": "user", "content": prompt}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.3,
        }

        async with httpx.AsyncClient(timeout=DEEPSEEK_TIMEOUT) as client:
            resp = await client.post(DEEPSEEK_API_URL, headers=headers, json=payload)
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"].strip()

        try:
            result = json.loads(text)
        except json.JSONDecodeError:
            logger.error(f"[INTEGRITY] Invalid JSON response: {text[:200]}")
            return {"integrity_score": 0.5, "scores": {}, "flags": ["JSON parse error"]}

        integrity_score = result.get("integrity_score", 0.5)
        # Validate: recalculate average if scores dict is present
        scores = result.get("scores", {})
        if scores and len(scores) == 5:
            calculated_avg = sum(scores.values()) / 5
            # Use calculated average if reported average is off
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
    7-factor credibility scoring algorithm with spam penalty (SERP + Citations moved to rescue bonus).
    Returns score 0.0-85.0 (up to 100.0 with rescue bonus). Minimum threshold: 45.0 to pass verification (53% pass rate).

    FACTORS (March 2026 v2 — enhanced with DataForSEO + SERP):
    - Content Integrity (25 pts) - "is this trustworthy?" (DeepSeek)
    - Content Quality (15 pts) - "is this well-written?" (DeepSeek)
    - Domain Tier + Authority (20 pts) - Curated tiers + DataForSEO Domain Rank fallback
    - Content Freshness (15 pts) - Exa publishedDate primary, regex fallback
    - SERP Ranking (10 pts) - Source domain appears in top SERP results (DataForSEO)
    - Internal Citations (5 pts) - Backlink credibility
    - Author Attribution (5 pts) - Exa author field (E-E-A-T signal)
    - Topical Relevance (5 pts) - Exa search score
    - Spam Penalty (-10 pts) - DataForSEO spam score deduction
    """
    # Early exit: blocked domains get zero score immediately
    from ..domain_tiers import is_blocked_domain
    source_domain = domain_metrics.get("domain", "")
    if is_blocked_domain(source_domain):
        logger.warning(f"[BLOCKED] {source_domain} is a known SEO farm / hijacked domain. Score: 0.0")
        return 0.0

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

    # Factor 5: SERP Ranking — MOVED TO RESCUE BONUS (see calculate_rescue_bonus)
    # SERP matching is unreliable for niche topics - generic keywords don't reflect niche authority
    breakdown["serp"] = 0.0

    # Factor 6: Internal Citations — MOVED TO RESCUE BONUS (see calculate_rescue_bonus)
    # Citations are extracted AFTER initial verification, so always 0 during first pass
    breakdown["citations"] = 0.0

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

    # Blog domain penalty — corporate blogs are inherently promotional
    source_url = source.get("url", "")
    source_domain = domain_metrics.get("domain", "")
    blog_penalty = 0.0

    if source_domain.startswith("blog."):
        blog_penalty = BLOG_DOMAIN_PENALTY
        logger.info(f"[BLOG-PENALTY] {source_domain} is a blog subdomain: -{BLOG_DOMAIN_PENALTY} pts")
    elif "/blog/" in source_url or source_url.endswith("/blog"):
        blog_penalty = BLOG_PATH_PENALTY
        logger.info(f"[BLOG-PENALTY] {source_url} contains /blog/ path: -{BLOG_PATH_PENALTY} pts")

    score -= blog_penalty
    breakdown["blog_penalty"] = round(-blog_penalty, 1)

    # Unsourced claims penalty — Tier 0 domains must cite their own evidence
    unsourced_penalty = 0.0
    if tier_level == 0 and content_integrity:
        claim_sourcing = content_integrity.get("scores", {}).get("claim_sourcing", 0.5)
        if claim_sourcing < 0.4:
            unsourced_penalty = UNSOURCED_CLAIMS_PENALTY
            logger.info(
                f"[UNSOURCED] {source_domain} is Tier 0 with claim_sourcing={claim_sourcing:.2f}: "
                f"-{UNSOURCED_CLAIMS_PENALTY} pts (claims not backed by evidence)"
            )
    score -= unsourced_penalty
    breakdown["unsourced_penalty"] = round(-unsourced_penalty, 1)

    final_score = max(0.0, min(100.0, score))

    # Log full breakdown for debugging
    logger.info(
        f"[SCORE] {final_score:.1f}/100 "
        f"(Integrity:{breakdown['integrity']} Quality:{breakdown['quality']} "
        f"Domain:{breakdown['domain']} Fresh:{breakdown['freshness']} "
        f"SERP:{breakdown['serp']} Cite:{breakdown['citations']} "
        f"Author:{breakdown['author']} Relevance:{breakdown['relevance']} "
        f"BlogPen:{breakdown['blog_penalty']} UnsourcedPen:{breakdown['unsourced_penalty']})"
    )

    return final_score


# --- Borderline Rescue ---

def calculate_rescue_bonus(
    source: dict,
    content_integrity: dict | None,
    serp_position: int | None = None,
    citations: list[dict] | None = None
) -> float:
    """
    Borderline rescue for sources scoring 35.0-44.9.
    Only applies when promotional_intent >= 0.6 (non-salesy).

    Five supplementary signals (max +15 pts, mostly $0 cost):
    - Content depth (word count): >2000w +3, >1500w +2, >1000w +1
    - Technical content (code blocks): +3 if found
    - External reference density: 5+ domains +2, 3+ domains +1
    - SERP ranking: top 5 +10, top 10 +7, top 20 +4
    - Internal citations: +5 max (credible citations * 1.67)
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

    # Signal 4: SERP ranking (moved from main scoring - better suited as rescue signal)
    if serp_position is not None:
        if serp_position <= 5:
            bonus += 10.0
            reasons.append(f"SERP:top5(+10)")
        elif serp_position <= 10:
            bonus += 7.0
            reasons.append(f"SERP:top10(+7)")
        elif serp_position <= 20:
            bonus += 4.0
            reasons.append(f"SERP:top20(+4)")

    # Signal 5: Internal citations (moved from main scoring - extracted after initial verification)
    if citations:
        credible_count = sum(1 for c in citations if c.get("is_credible"))
        if credible_count > 0:
            cite_bonus = min(5.0, credible_count * 1.67)
            bonus += cite_bonus
            reasons.append(f"citations:{credible_count}(+{cite_bonus:.0f})")

    if bonus > 0:
        logger.info(f"[RESCUE] Bonus: +{bonus:.0f} pts | {', '.join(reasons)}")

    return min(15.0, bonus)


# --- Fact Extraction ---

async def extract_facts_from_source(source: dict) -> list[dict]:
    """
    Uses DeepSeek Reasoner to extract verifiable factual claims.
    Returns: [{fact_text, fact_type, citation_anchor, confidence}]
    Cost: ~$0.00005 per source
    """
    try:
        prompt = f"""You are a fact extraction specialist. Extract ONLY verifiable factual claims from the following article.

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

Return a JSON object with a "facts" key containing an array:
{{
  "facts": [
    {{
      "fact_text": "Exact claim extracted verbatim (include numbers, percentages, names, years)",
      "fact_type": "statistic|benchmark|case_study|expert_quote",
      "citation_anchor": "How to reference this (e.g., 'Source Name 2024', 'Gartner 2024', 'Company Blog')",
      "original_source": "Named study, report, or expert cited in the text (e.g., 'Gartner 2024 Report', 'Dr. Jane Smith'). Empty string if the text states the number without naming its origin.",
      "confidence": 0.9
    }}
  ]
}}

CRITICAL RULES:
- Extract facts that include SPECIFIC NUMBERS, PERCENTAGES, DOLLAR AMOUNTS, or DIRECT QUOTES about the topic
- Do NOT extract vague claims like "many companies" or "recent studies show"
- Do NOT extract opinions, predictions, or subjective statements
- NEVER extract article metadata: publication dates, update dates, reading times ("X min read"), word counts, author names, or bylines
- NEVER extract navigation text, headers, footers, or boilerplate content
- Include the YEAR if mentioned in the claim
- confidence scoring (be strict):
  - 0.8-0.9: Fact cites a named study, report, organization, or expert by name
  - 0.6-0.7: Fact states a specific number but does NOT name its origin
  - 0.5: Fact is a round number or rule-of-thumb with no attribution (e.g., "most companies spend 10-15%")
- Return {{"facts": []}} if no specific factual claims about the topic exist

WHAT TO EXTRACT: Claims about the subject matter with specific numbers, percentages, dollar amounts, or attributable quotes.
WHAT TO SKIP: Article metadata (dates, "X min read", author info), vague generalizations, opinions, predictions without data.

Only return the JSON, no other text."""

        headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": DEEPSEEK_REASONER_MODEL,
            "messages": [
                {"role": "system", "content": "You output valid JSON ONLY."},
                {"role": "user", "content": prompt}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.3,
        }

        async with httpx.AsyncClient(timeout=DEEPSEEK_REASONER_TIMEOUT) as client:
            resp = await client.post(DEEPSEEK_API_URL, headers=headers, json=payload)
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"].strip()

        # Parse JSON with error handling
        try:
            parsed = json.loads(text)
            # Handle both {"facts": [...]} and [...] formats
            if isinstance(parsed, dict):
                facts = next((v for v in parsed.values() if isinstance(v, list)), [])
            elif isinstance(parsed, list):
                facts = parsed
            else:
                logger.warning(f"[DEEPSEEK] Expected list/dict, got {type(parsed)}")
                facts = []
        except json.JSONDecodeError:
            logger.error(f"[DEEPSEEK] Invalid JSON response for {source['url']}: {text[:200]}")
            return []

        # Post-filter: strip metadata that LLMs sometimes extract despite prompt instructions
        _metadata_patterns = re.compile(
            r'(min read|published on|updated on|last modified|posted on|written by|author:|byline)',
            re.IGNORECASE
        )
        filtered = [f for f in facts if not _metadata_patterns.search(f.get("fact_text", ""))]
        if len(filtered) < len(facts):
            logger.info(f"[DEEPSEEK] Filtered {len(facts) - len(filtered)} metadata entries from {source['url']}")
        facts = filtered

        logger.info(f"[DEEPSEEK] Extracted {len(facts)} facts from {source['url']}")

        return facts

    except Exception as e:
        logger.error(f"[DEEPSEEK] Fact extraction failed for {source['url']}: {e}")
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


def score_fact_consensus(all_citations: list, source_tiers: dict | None = None) -> dict[int, dict]:
    """
    For each fact, count how many OTHER sources independently cite similar claims.

    Similarity heuristic (no LLM needed):
    1. Extract all numbers from fact_text (percentages, dollars, counts)
    2. Extract key terms (proper nouns, technical terms)
    3. Two facts are "similar" if they share 1+ number AND 2+ key terms
    4. Facts from the SAME source don't count as corroboration

    Returns: {fact_citation.id: {"count": N, "has_authoritative": bool}}
    """
    if not all_citations:
        return {}

    source_tiers = source_tiers or {}

    # Pre-compute number and term sets for each citation
    parsed = []
    for cite in all_citations:
        domain = extract_domain(cite.source_url)
        parsed.append({
            "id": cite.id,
            "source_url": cite.source_url,
            "domain": domain,
            "tier": source_tiers.get(domain, 0),
            "numbers": _extract_numbers(cite.fact_text),
            "terms": _extract_key_terms(cite.fact_text),
        })

    consensus_map = {}
    for i, a in enumerate(parsed):
        count = 1  # Counts itself
        has_authoritative = a["tier"] in (1, 2)
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
                if b["tier"] in (1, 2):
                    has_authoritative = True
        consensus_map[a["id"]] = {"count": count, "has_authoritative": has_authoritative}

    return consensus_map


# --- Database Storage ---

async def link_facts_to_sources(verified_sources: list, research_run_id: int, db: Session, elite_competitors: list[dict] | None = None, niche: str = ""):
    """
    Extracts facts from each verified source and stores in FactCitation table.
    Only processes sources with credibility_score >= 45.0.
    After extraction:
      1. Runs fact faithfulness check (free, pure Python)
      2. Runs independent Exa verification for Tier 3-4 statistical claims
      3. Runs cross-source consensus scoring to boost corroborated facts

    Returns: dict with ai_detection_summary and fact_verification_summary for SSE events
    """
    from .claim_verification_agent import verify_fact_faithfulness, batch_verify_facts

    # Build URL -> full content mapping for fact extraction
    full_content_map = {}
    if elite_competitors:
        for comp in elite_competitors:
            url = comp.get("url", "")
            if url:
                full_content_map[url] = comp.get("content", "")

    # Build domain -> tier mapping for verification decisions
    source_tiers = {}
    for source_row in verified_sources:
        tier_level, _ = get_domain_tier_score(source_row.domain)
        # Gap 4: Validate URL format for Tier 1-2 before granting trust
        if tier_level in (1, 2) and not validate_url_format(source_row.url, source_row.domain):
            logger.warning(f"[URL-VALIDATE] {source_row.url} domain mismatch for claimed Tier {tier_level} domain {source_row.domain}")
            tier_level = 0  # Demote to unknown
        source_tiers[source_row.domain] = tier_level

    all_new_citations = []
    all_facts_for_verification = []  # Collect facts for batch verification

    # --- Concurrent Fact Extraction ---
    extraction_tasks = []
    valid_sources = []
    import asyncio

    for source_row in verified_sources:
        if source_row.credibility_score < 45.0:
            continue

        full_content = full_content_map.get(source_row.url, "") or source_row.content_snippet or ""

        source_dict = {
            "title": source_row.title,
            "url": source_row.url,
            "content": full_content,
        }
        
        valid_sources.append((source_row, full_content))
        extraction_tasks.append(extract_facts_from_source(source_dict))

    # Run DeepSeek reasoning for all sources concurrently (Fixes 30+ minute stall)
    extracted_facts_results = []
    if extraction_tasks:
        logger.info(f"[FACTS] Starting concurrent fact extraction for {len(extraction_tasks)} sources...")
        extracted_facts_results = await asyncio.gather(*extraction_tasks, return_exceptions=True)

    for i, facts in enumerate(extracted_facts_results):
        source_row, full_content = valid_sources[i]
        
        if isinstance(facts, Exception):
            logger.error(f"[FACTS] DeepSeek extraction failed for {source_row.url}: {facts}")
            continue

        for fact in facts:
            if fact.get("confidence", 0) < 0.6:
                continue

            # --- Fact faithfulness check (free, pure Python) ---
            grounding = verify_fact_faithfulness(fact["fact_text"], full_content)

            source_cred = source_row.credibility_score
            fact_conf = fact["confidence"] * grounding["confidence_multiplier"]
            composite = (fact_conf * 100 + source_cred) / 2

            # Determine initial verification status based on source tier
            tier_level = source_tiers.get(source_row.domain, 0)
            if tier_level in (1, 2):
                verification_status = "trusted"
                is_verified = True
            else:
                verification_status = "not_checked"
                # Tier 3-4: only auto-verify if faithfulness grounding is very high
                is_verified = grounding["confidence_multiplier"] >= 0.9
                # Unattributed statistical claims from non-authoritative sources stay unverified
                if is_verified and not fact.get("original_source") and fact.get("fact_type") == "statistic":
                    is_verified = False

            # Gap 1 fix: Veto ungrounded facts regardless of tier
            if grounding["grounding_method"] == "none":
                is_verified = False
                if tier_level in (1, 2):
                    verification_status = "suspect"     # Trusted source, bad fact
                else:
                    verification_status = "ungrounded"  # Untrusted source, bad fact

            # --- Fix 1: Citation Laundering Detection ---
            # Catches facts like "Gartner reports 40%" sourced from nuconet.com
            laundering = detect_citation_laundering(fact["fact_text"], source_row.domain, fact.get("citation_anchor", ""))
            if laundering["is_laundered"]:
                is_verified = False
                verification_status = "laundered"
                composite = composite * 0.5  # Severe penalty
                logger.warning(
                    f"[LAUNDERING] Fact claims '{laundering['claimed_org']}' "
                    f"but source is {source_row.domain}: "
                    f"{fact['fact_text'][:80]}..."
                )

            # --- Fix 2: Tier 0 Authority Floor ---
            # Unknown domains must prove their claims via independent corroboration.
            # ALL fact types (stats, expert quotes, case studies, benchmarks) start untrusted.
            # Exa verification can resurrect statistical claims if a Tier 1-2 source corroborates.
            if tier_level == 0 and verification_status not in ("laundered", "ungrounded", "suspect"):
                is_verified = False
                verification_status = "untrusted_source"
                composite = composite * 0.6
                logger.info(
                    f"[AUTHORITY-FLOOR] {fact.get('fact_type', 'unknown')} from Tier 0 domain "
                    f"{source_row.domain} demoted: {fact['fact_text'][:80]}..."
                )

            # --- Fix 3: Known AI Hallucination Name Detection ---
            # Claude habitually generates "Sarah Chen" as its default expert name
            # across wildly different contexts. Flag expert quotes containing known
            # AI-default personas as suspect (zero-cost regex check).
            _AI_HALLUCINATION_NAMES = {
                "sarah chen", "marcus webb", "james chen", "emily zhang",
                "david kumar", "rachel torres", "michael chang",
            }
            combined_text = (fact["fact_text"] + " " + fact.get("citation_anchor", "")).lower()
            for halluc_name in _AI_HALLUCINATION_NAMES:
                if halluc_name in combined_text:
                    is_verified = False
                    verification_status = "suspect"
                    composite = composite * 0.3
                    logger.warning(
                        f"[HALLUCINATION] Known AI-default name '{halluc_name}' in fact from "
                        f"{source_row.domain}: {fact['fact_text'][:80]}..."
                    )
                    break

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
                is_grounded=grounding["is_grounded"],
                grounding_method=grounding["grounding_method"],
                is_verified=is_verified,
                verification_status=verification_status,
            )
            db.add(citation)
            db.flush()  # Get the ID assigned before consensus scoring
            all_new_citations.append(citation)

            # Track for batch verification
            all_facts_for_verification.append({
                "fact_text": fact["fact_text"],
                "source_url": source_row.url,
                "citation_index": len(all_new_citations) - 1,
            })

    # --- Independent fact verification via Exa (Tier 3-4 statistical claims) ---
    fact_verification_summary = {"verified": 0, "unverifiable": 0, "corrected": 0, "total_checked": 0}

    if all_facts_for_verification:
        try:
            verification_map = await batch_verify_facts(
                facts=all_facts_for_verification,
                source_tiers=source_tiers,
                niche=niche,
                max_searches=15,
            )

            # Apply verification results to citations
            for fact_idx, result in verification_map.items():
                citation = all_new_citations[fact_idx]
                status = result["status"]
                citation.verification_status = status
                citation.corroboration_url = result.get("corroboration_url")

                if status == "corroborated":
                    citation.is_verified = True
                    fact_verification_summary["verified"] += 1
                elif status == "corrected":
                    citation.is_verified = False
                    citation.composite_score = max(0.0, citation.composite_score * 0.7)
                    fact_verification_summary["corrected"] += 1
                elif status == "unverifiable":
                    citation.is_verified = False
                    citation.composite_score = max(0.0, citation.composite_score * 0.5)
                    fact_verification_summary["unverifiable"] += 1

                fact_verification_summary["total_checked"] += 1

            logger.debug(
                f"[FACT-BATCH] Applied verification: "
                f"{fact_verification_summary['verified']} corroborated, "
                f"{fact_verification_summary['corrected']} corrected, "
                f"{fact_verification_summary['unverifiable']} unverifiable"
            )

        except Exception as e:
            logger.error(f"[FACT-BATCH] Independent verification failed (non-critical): {e}")

    # --- Cross-source consensus scoring ---
    if all_new_citations:
        consensus_map = score_fact_consensus(all_new_citations, source_tiers)

        boosted = 0
        copypasta_flagged = 0
        for citation in all_new_citations:
            entry = consensus_map.get(citation.id, {"count": 1, "has_authoritative": False})
            count = entry["count"]
            has_auth = entry["has_authoritative"]
            citation.consensus_count = count
            # Adjust composite score based on consensus
            if count >= 3 and has_auth:
                citation.composite_score = min(100.0, citation.composite_score * 1.3)
                boosted += 1
            elif count >= 2 and has_auth:
                citation.composite_score = min(100.0, citation.composite_score * 1.15)
                boosted += 1
            elif count >= 3 and not has_auth:
                # Suspected viral copypasta — multiple low-tier sources, no authoritative corroboration
                copypasta_flagged += 1
            elif count == 1:
                citation.composite_score = citation.composite_score * 0.85

        if boosted:
            logger.info(f"[CONSENSUS] {boosted}/{len(all_new_citations)} facts corroborated by multiple sources")
        if copypasta_flagged:
            logger.warning(f"[CONSENSUS] {copypasta_flagged} facts flagged as suspected viral copypasta (no Tier 1-2 corroboration)")

    db.commit()
    logger.info(f"[FACTS] Linked {len(all_new_citations)} facts to {len(verified_sources)} verified sources")

    return {
        "total_facts": len(all_new_citations),
        "fact_verification": fact_verification_summary,
    }


# --- Main Entry Point ---

async def verify_sources(
    elite_competitors: list[dict],
    db: Session,
    profile_name: str = "default",
    research_run_id: int = 0,
    mcp_session=None,
    keyword: str = "",
    niche: str = "",
    min_score_threshold: float = 45.0,
) -> dict:
    """
    Main source verification pipeline (9-factor scoring + spam penalty).

    Input: elite_competitors from ResearchAgent [{title, url, content, published_date, author, exa_score}]
    Output: {verified_sources: list[VerifiedSource], rejected_sources: list[dict]}

    Process:
    1. Deduplicate sources by URL
    2. Pre-compute local signals (domain tier, citations) -- free, instant
    3. Fetch DataForSEO backlinks authority + SERP rankings -- parallel, ~$0.04
    4. Batch DeepSeek calls (quality + integrity) via asyncio.gather -- parallel
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

    # Gap 27b: Language safety net — reject sources with >20% non-Latin characters
    # This catches non-English content that slipped past research_service filters
    non_english_count = 0
    english_sources = []
    for source in elite_competitors:
        text_sample = (source.get("content", "") or "")[:2000]
        if text_sample and len(text_sample) >= 50:
            non_latin = sum(1 for c in text_sample if ord(c) > 0x024F and not c.isspace() and not c.isdigit())
            if (non_latin / len(text_sample)) > 0.20:
                non_english_count += 1
                logger.info(f"[LANG-FILTER] Rejected non-English source: {source.get('url', '')}")
                continue
        english_sources.append(source)
    if non_english_count > 0:
        logger.info(f"[LANG-FILTER] Removed {non_english_count} non-English sources in verify_sources()")
    elite_competitors = english_sources

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

    # --- Phase 2: Domain caching + Batch DeepSeek calls ---
    from ..models import DomainCredibilityCache
    from datetime import datetime, timedelta

    # Check cache for each domain (90-day TTL)
    quality_results = [None] * len(elite_competitors)
    integrity_results = [None] * len(elite_competitors)
    cache_hits = 0
    uncached_indices = []

    normalized_niche = niche.strip().lower().replace(" ", "-") if niche else "general"

    for i, source in enumerate(elite_competitors):
        domain = local_signals[i]["domain"]

        # Try cache lookup
        cache_entry = db.query(DomainCredibilityCache).filter_by(
            domain=domain,
            niche=normalized_niche
        ).first()

        if cache_entry:
            age_days = (datetime.now() - cache_entry.last_checked).days
            if age_days < 90:
                # Cache hit - use cached scores
                quality_results[i] = {"score": cache_entry.quality_score or 0.5}
                integrity_results[i] = {
                    "integrity_score": cache_entry.integrity_score or 0.5,
                    "scores": {},
                    "flags": []
                }
                cache_hits += 1
                logger.info(f"[CACHE-HIT] {domain} -> cached scores (age: {age_days}d)")
                continue

        # Cache miss - need to call DeepSeek
        uncached_indices.append(i)

    # Batch DeepSeek calls for uncached sources only
    from .claim_verification_agent import detect_ai_generated_content, compute_ai_detection_penalty
    ai_detection_results = [None] * len(elite_competitors)

    if uncached_indices:
        uncached_content = [elite_competitors[i].get("content", "") for i in uncached_indices]
        quality_tasks = [assess_content_quality(content) for content in uncached_content]
        integrity_tasks = [detect_content_integrity(content) for content in uncached_content]
        # AI detection is now deterministic (no LLM call) — compute inline
        ai_detect_results_uncached = [detect_ai_generated_content(content) for content in uncached_content]

        total_tasks = len(quality_tasks) + len(integrity_tasks)
        logger.info(f"[VERIFY] Cache: {cache_hits} hits, {len(uncached_indices)} misses. Launching {total_tasks} DeepSeek calls + {len(ai_detect_results_uncached)} deterministic AI detections...")
        all_results = await asyncio.gather(*quality_tasks, *integrity_tasks, return_exceptions=True)

        n = len(uncached_indices)
        # Assign results to uncached indices
        for idx, uncached_i in enumerate(uncached_indices):
            qr = all_results[idx]
            ir = all_results[n + idx]
            ar = ai_detect_results_uncached[idx]
            quality_results[uncached_i] = qr if not isinstance(qr, Exception) else {"score": 0.5, "reasoning": "Error"}
            integrity_results[uncached_i] = ir if not isinstance(ir, Exception) else {"integrity_score": 0.5, "scores": {}, "flags": ["Error"]}
            ai_detection_results[uncached_i] = ar
    else:
        logger.info(f"[VERIFY] Cache: {cache_hits} hits, 0 misses. No DeepSeek calls needed.")

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

        # Apply AI detection penalty (after scoring, before rescue)
        ai_result = ai_detection_results[i]
        if ai_result:
            tier_level = local_signals[i].get("domain_metrics", {}).get("tier_level", 0)
            ai_penalty = compute_ai_detection_penalty(ai_result, tier_level=tier_level)
            if ai_penalty != 0.0:
                original_ai_score = credibility_score
                credibility_score = max(0.0, credibility_score + ai_penalty)
                ai_prob = ai_result.get("ai_probability", 0.0)
                logger.info(
                    f"[AI-DETECT] {extract_domain(source['url'])} "
                    f"AI probability: {ai_prob:.2f} -> penalty: {ai_penalty} pts "
                    f"(score: {original_ai_score:.1f} -> {credibility_score:.1f})"
                )

        # Borderline rescue: sources scoring 35.0-44.9 get supplementary signal check
        if 35.0 <= credibility_score < 45.0:
            rescue_bonus = calculate_rescue_bonus(source, content_integrity, serp_pos, citations)
            if rescue_bonus > 0:
                original_score = credibility_score
                credibility_score = min(100.0, credibility_score + rescue_bonus)
                if credibility_score >= 45.0:
                    logger.info(
                        f"[RESCUED] {extract_domain(source['url'])} "
                        f"rescued from {original_score:.1f} to {credibility_score:.1f} "
                        f"(+{rescue_bonus:.0f} borderline bonus)"
                    )

        # Restored to 45.0 after fixing metadata extraction (freshness+relevance) and moving SERP+citations to rescue
        verification_passed = credibility_score >= min_score_threshold
        rejection_reason = None if verification_passed else f"Score {credibility_score:.1f} < {min_score_threshold} threshold"

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

        # Check if source already exists (prevent duplicate key error in iterative search)
        existing_source = db.query(VerifiedSource).filter_by(
            research_run_id=research_run_id,
            url=source["url"]
        ).first()

        if existing_source:
            # Source already saved - use existing entry
            verified_source = existing_source
            logger.info(f"[DEDUP] Skipping duplicate save: {source['url'][:60]}... (already in DB)")
        else:
            # New source - create and save
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
                content_snippet=source.get("content", "")[:4000],  # Increased for fact faithfulness checks
                verification_passed=verification_passed,
                rejection_reason=rejection_reason,
            )

            db.add(verified_source)
            db.commit()
            db.refresh(verified_source)

        # Update domain credibility cache
        cache_entry = db.query(DomainCredibilityCache).filter_by(
            domain=domain,
            niche=normalized_niche
        ).first()

        if cache_entry:
            # Update existing cache entry (rolling average)
            cache_entry.quality_score = (
                (cache_entry.quality_score * cache_entry.check_count + content_quality.get("score", 0.5))
                / (cache_entry.check_count + 1)
            )
            cache_entry.integrity_score = (
                (cache_entry.integrity_score * cache_entry.check_count + content_integrity.get("integrity_score", 0.5))
                / (cache_entry.check_count + 1)
            )
            cache_entry.check_count += 1
            cache_entry.last_checked = datetime.now()
        else:
            # Create new cache entry
            cache_entry = DomainCredibilityCache(
                domain=domain,
                niche=normalized_niche,
                tier_level=domain_metrics.get("tier_level", 0),
                base_score=domain_metrics.get("score", 0.0),
                quality_score=content_quality.get("score", 0.5),
                integrity_score=content_integrity.get("integrity_score", 0.5),
                check_count=1,
            )
            db.add(cache_entry)

        db.commit()

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


async def iterative_source_search(
    keyword: str,
    niche: str,
    profile_name: str,
    research_run_id: int,
    db: Session,
    mcp_session,
    research_agent,
    initial_sources: list,
    target_count: int = 3,
    max_iterations: int = 3,
    min_threshold: float = 45.0,  # Restored after metadata fixes
    threshold_decay: float = 5.0,
) -> dict:
    """
    Iteratively search for verified sources until target_count is reached.

    Cost control: max 3 iterations = max 45 total sources checked (15/iteration)
    Budget impact: +$0.011 worst case (3 iterations × 15 sources × $0.00025/source)

    Args:
        keyword: Search keyword
        niche: Content niche (normalized)
        profile_name: Multi-tenant identifier
        research_run_id: Database ID for this research run
        db: SQLAlchemy session
        mcp_session: MCP session for DataForSEO
        research_agent: ResearchAgent instance with search methods
        initial_sources: Already verified sources (from Phase 1)
        target_count: Minimum verified sources needed (default 3)
        max_iterations: Maximum search iterations (default 3)
        min_threshold: Starting credibility threshold (default 35.0)
        threshold_decay: How much to lower threshold each iteration (default 5.0)

    Returns:
        {
            verified_sources: list[VerifiedSource],
            rejected_sources: list[dict],
            iterations_used: int,
            final_threshold: float
        }
    """
    from datetime import datetime as dt_now, timedelta as td

    all_verified = list(initial_sources)  # Start with initial verified sources
    all_rejected = []
    seen_urls = {s.url for s in initial_sources}
    rejected_domains = set()
    current_threshold = min_threshold

    logger.info(f"[ITERATIVE-SEARCH] Starting with {len(all_verified)}/{target_count} sources, threshold={current_threshold}")

    iteration = 1
    while len(all_verified) < target_count and iteration <= max_iterations:
        logger.info(f"[ITERATIVE-SEARCH] Iteration {iteration}: {len(all_verified)}/{target_count} verified")

        # Dynamic strategy selection based on iteration
        new_sources = []

        if iteration == 1 and all_verified:
            # Strategy 1: FindSimilar using best source as seed
            best_source = max(all_verified, key=lambda s: s.credibility_score)
            logger.info(f"[ITERATIVE-SEARCH] Strategy: FindSimilar (seed: {best_source.url[:50]}...)")

            try:
                two_years_ago = (dt_now.now() - td(days=730)).strftime('%Y-%m-%d')
                from .research_service import EXA_EXCLUDE_DOMAINS

                similar_results = await research_agent.exa_find_similar(
                    url=best_source.url,
                    num_results=15,
                    exclude_domains=list(EXA_EXCLUDE_DOMAINS) + list(rejected_domains),
                    start_published_date=two_years_ago,
                )

                # Build metadata map from findSimilar results (preserves exa_score + published_date)
                url_metadata_map = {
                    r.get("url", ""): {
                        "score": r.get("exa_score"),
                        "published_date": r.get("published_date"),
                    }
                    for r in similar_results
                    if not r.get("error")
                }

                # Extract full text for verification
                similar_ids = [r.get("id") for r in similar_results if r.get("id") and not r.get("error")]
                if similar_ids:
                    similar_articles = await research_agent.exa_extract_full_text(similar_ids)
                    # Merge preserved metadata back into extracted articles
                    for article in similar_articles:
                        if not article.get("error"):
                            metadata = url_metadata_map.get(article.get("url", ""), {})
                            if not article.get("exa_score"):
                                article["exa_score"] = metadata.get("score")
                            if not article.get("published_date"):
                                article["published_date"] = metadata.get("published_date")
                    new_sources = [s for s in similar_articles if s.get("url") not in seen_urls and not s.get("error")]
            except Exception as e:
                logger.error(f"[ITERATIVE-SEARCH] FindSimilar failed: {e}")

        elif iteration == 2:
            # Strategy 2: Niche-filtered backfill (authoritative domains only)
            logger.info(f"[ITERATIVE-SEARCH] Strategy: Niche-filtered backfill")

            try:
                niche_results = await research_agent.niche_filtered_backfill(keyword, niche, list(rejected_domains))
                new_sources = [s for s in niche_results if s.get("url") not in seen_urls]
            except Exception as e:
                logger.error(f"[ITERATIVE-SEARCH] Niche backfill failed: {e}")

        else:
            # Strategy 3: Broad search (wider net)
            logger.info(f"[ITERATIVE-SEARCH] Strategy: Broad search fallback")

            try:
                broad_results = await research_agent.backfill_search(keyword, niche, list(rejected_domains))
                new_sources = [s for s in broad_results if s.get("url") not in seen_urls]
            except Exception as e:
                logger.error(f"[ITERATIVE-SEARCH] Broad search failed: {e}")

        # Update seen URLs
        seen_urls.update(s.get("url") for s in new_sources)

        if not new_sources:
            logger.warning(f"[ITERATIVE-SEARCH] Iteration {iteration}: Strategy returned 0 new sources")
            iteration += 1
            continue

        logger.info(f"[ITERATIVE-SEARCH] Found {len(new_sources)} new candidate sources")

        # Verify batch with current threshold
        verification_result = await verify_sources(
            elite_competitors=new_sources,
            db=db,
            profile_name=profile_name,
            research_run_id=research_run_id,
            mcp_session=mcp_session,
            keyword=keyword,
            niche=niche,
            min_score_threshold=current_threshold,
        )

        all_verified.extend(verification_result["verified_sources"])

        all_rejected.extend(verification_result["rejected_sources"])
        rejected_domains.update(s["domain"] for s in verification_result["rejected_sources"])

        logger.info(f"[ITERATIVE-SEARCH] Iteration {iteration} results: +{len(verification_result['verified_sources'])} verified, +{len(verification_result['rejected_sources'])} rejected")

        # Early exit if target reached mid-iteration
        if len(all_verified) >= target_count:
            logger.info(f"[ITERATIVE-SEARCH] Target reached: {len(all_verified)} sources verified")
            break

        # Threshold decay: lower bar if struggling (45 → 40 → 35)
        if iteration >= 2 and len(all_verified) < target_count:
            current_threshold -= threshold_decay
            logger.info(f"[ITERATIVE-SEARCH] Lowering threshold to {current_threshold} (iteration {iteration})")

        iteration += 1

    # Final summary
    final_count = len(all_verified)
    if final_count < target_count:
        logger.warning(f"[ITERATIVE-SEARCH] Only {final_count}/{target_count} sources after {iteration-1} iterations")
    else:
        logger.info(f"[ITERATIVE-SEARCH] Success: {final_count} sources verified after {iteration-1} iterations")

    return {
        "verified_sources": all_verified,
        "rejected_sources": all_rejected,
        "iterations_used": iteration - 1,
        "final_threshold": current_threshold,
    }
