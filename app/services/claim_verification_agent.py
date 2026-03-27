"""
Claim Verification Agent

Research-grade verification layer that closes 3 trust gaps:
1. AI Content Detection — penalizes GPT-generated source articles
2. Independent Fact Verification — searches Exa for authoritative corroboration
3. Post-Writer Claim Cross-Referencing — replaces weak domain-counting Gate 2

Capabilities:
A. detect_ai_generated_content() + compute_ai_detection_penalty()
B. verify_fact_independently() + batch_verify_facts()
C. verify_fact_faithfulness()
D. extract_article_claims() + cross_reference_claims() + verify_claim_with_llm()
   + format_claim_verification_feedback()
"""

import json
import logging
import re
from collections import Counter

import httpx

from ..settings import DEEPSEEK_API_KEY, DEEPSEEK_MODEL, EXA_API_KEY, CLAIM_TEXT_SIMILARITY_THRESHOLD, LLM_SOURCE_CONTEXT_CHARS
from ..domain_tiers import TIER_1_DOMAINS, TIER_2_DOMAINS, get_domain_tier_score

DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"

logger = logging.getLogger(__name__)


# ============================================================
# Capability A: AI Content Detection
# ============================================================

def _compute_deterministic_ai_signals(content: str) -> dict:
    """
    Compute 4 measurable AI detection signals from text.
    Pure Python, $0.00 cost. Each signal: 0.0-1.0 where 1.0 = human, 0.0 = AI.
    """
    import math

    default = {"ttr": 0.5, "sentence_variance": 0.5, "hedging": 0.5, "transitions": 0.5, "avg_human_score": 0.5}

    if not content or len(content) < 200:
        return default

    # Clean content: strip markdown
    clean = re.sub(r'```[\s\S]*?```', '', content)
    clean = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', clean)
    clean = re.sub(r'[#*_>`~]', '', clean).strip()

    words = re.findall(r'[a-zA-Z]+', clean.lower())
    total_words = len(words)
    if total_words < 50:
        return default

    # Signal 1: Type-Token Ratio (root TTR for length normalization)
    # Human: root TTR 6-10. AI: root TTR 4-6.
    unique_words = set(words)
    raw_ttr = len(unique_words) / math.sqrt(total_words)
    ttr_score = min(1.0, max(0.0, (raw_ttr - 4.0) / 6.0))

    # Signal 2: Sentence length variance
    # Human: std 5-15. AI: std 2-5.
    sentences = re.split(r'[.!?]+', clean)
    sentences = [s.strip() for s in sentences if len(s.strip().split()) >= 3]

    if len(sentences) >= 5:
        lengths = [len(s.split()) for s in sentences]
        mean_len = sum(lengths) / len(lengths)
        variance = sum((l - mean_len) ** 2 for l in lengths) / len(lengths)
        std_dev = math.sqrt(variance)
        variance_score = min(1.0, max(0.0, (std_dev - 2.0) / 10.0))
    else:
        variance_score = 0.5

    # Signal 3: Hedging phrase density (>3 per 1000w = AI)
    hedging_phrases = [
        "it's important to note", "it's worth mentioning", "it's worth noting",
        "in today's digital landscape", "in today's world", "in the ever-evolving",
        "it cannot be overstated", "needless to say", "it goes without saying",
        "it should be noted", "one might argue", "it is essential to",
        "it is crucial to", "broadly speaking", "generally speaking",
        "in many cases", "for the most part", "as we all know",
    ]
    content_lower = clean.lower()
    per_1000 = 1000.0 / total_words
    hedge_count = sum(content_lower.count(p) for p in hedging_phrases)
    hedge_density = hedge_count * per_1000
    if hedge_density <= 1.0:
        hedging_score = 1.0
    elif hedge_density <= 3.0:
        hedging_score = 0.5
    else:
        hedging_score = max(0.0, 1.0 - (hedge_density - 1.0) / 5.0)

    # Signal 4: Transition formula density (>5 per 1000w = AI)
    transition_phrases = [
        "furthermore", "moreover", "additionally", "in conclusion",
        "consequently", "nevertheless", "nonetheless", "in summary",
        "to summarize", "in essence", "as a result", "on the other hand",
        "having said that", "with that being said", "it is also worth",
        "equally important", "by the same token", "in light of",
    ]
    trans_count = sum(content_lower.count(p) for p in transition_phrases)
    trans_density = trans_count * per_1000
    if trans_density <= 2.0:
        transition_score = 1.0
    elif trans_density <= 5.0:
        transition_score = 0.5
    else:
        transition_score = max(0.0, 1.0 - (trans_density - 2.0) / 8.0)

    avg_human = (ttr_score + variance_score + hedging_score + transition_score) / 4.0

    return {
        "ttr": round(ttr_score, 3),
        "sentence_variance": round(variance_score, 3),
        "hedging": round(hedging_score, 3),
        "transitions": round(transition_score, 3),
        "avg_human_score": round(avg_human, 3),
    }


def detect_ai_generated_content(content: str) -> dict:
    """
    Deterministic AI content detection using 4 measurable signals.
    No LLM call needed — deterministic signals are more reliable and free.

    Returns: {ai_probability: 0.0-1.0, signals: {}, deterministic_signals: dict, reasoning: str}
    Cost: $0.00
    """
    if not content or len(content) < 200:
        return {"ai_probability": 0.3, "signals": {}, "deterministic_signals": {}, "reasoning": "Content too short to assess"}

    det_signals = _compute_deterministic_ai_signals(content)
    ai_probability = round(1.0 - det_signals["avg_human_score"], 3)

    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(
            f"[AI-DETECT] Deterministic: ttr={det_signals['ttr']}, var={det_signals['sentence_variance']}, "
            f"hedge={det_signals['hedging']}, trans={det_signals['transitions']} | "
            f"ai_prob={ai_probability:.2f}"
        )

    return {
        "ai_probability": ai_probability,
        "signals": {},
        "deterministic_signals": det_signals,
        "reasoning": "Deterministic signals only (TTR, sentence variance, hedging, transitions)",
    }


def compute_ai_detection_penalty(ai_result: dict, tier_level: int = 0) -> float:
    """
    Tier-aware penalty applied AFTER 7-factor scoring, BEFORE rescue bonus.
    Tier 0 (unknown) domains get stricter thresholds — can't trust them.
    Tier 1-4 (curated) domains keep standard thresholds — they've earned trust.
    Returns negative float (penalty) or 0.0.
    """
    ai_prob = ai_result.get("ai_probability", 0.0)

    if tier_level == 0:
        # Stricter for unknown domains
        if ai_prob >= 0.75:
            penalty = -15.0
        elif ai_prob >= 0.60:
            penalty = -10.0
        elif ai_prob >= 0.45:
            penalty = -5.0
        else:
            penalty = 0.0
    else:
        # Standard for curated domains
        if ai_prob >= 0.85:
            penalty = -15.0
        elif ai_prob >= 0.70:
            penalty = -10.0
        elif ai_prob >= 0.55:
            penalty = -5.0
        else:
            penalty = 0.0

    if penalty != 0.0:
        tier_label = f"Tier {tier_level}" if tier_level > 0 else "Tier 0 (unknown)"
        logger.debug(f"[AI-DETECT] Penalty: {penalty} pts (ai_probability={ai_prob:.2f}, {tier_label})")

    return penalty


# ============================================================
# Capability B: Independent Fact Verification via Exa
# ============================================================

# Number extraction for query building
_NUMBER_PATTERN = re.compile(r'(\d+(?:\.\d+)?)\s*(%|percent|million|billion|trillion|M\b|B\b|K\b)')
_DOLLAR_PATTERN = re.compile(r'\$\s*(\d+(?:\.\d+)?)\s*(million|billion|trillion|M\b|B\b|K\b)?', re.IGNORECASE)

# Build Tier 1+2 domain list for Exa include_domains
_TIER_1_2_DOMAINS = sorted([d for d in (TIER_1_DOMAINS | TIER_2_DOMAINS) if not d.startswith(".")])


def _is_statistical_claim(fact_text: str) -> bool:
    """Check if a fact contains specific numbers/stats that can be independently verified."""
    return bool(_NUMBER_PATTERN.search(fact_text) or _DOLLAR_PATTERN.search(fact_text))


def _build_verification_query(fact_text: str) -> str:
    """
    Extract core statistical claim for Exa search.
    '67% of SMBs experienced a cyberattack in 2023' -> '"67%" SMBs cyberattack 2023'
    """
    # Extract key numbers
    numbers = []
    for m in _NUMBER_PATTERN.finditer(fact_text):
        numbers.append(f'"{m.group(0).strip()}"')
    for m in _DOLLAR_PATTERN.finditer(fact_text):
        numbers.append(f'"{m.group(0).strip()}"')

    # Extract key nouns (words > 4 chars, not stopwords)
    stopwords = {"that", "this", "with", "from", "have", "been", "were", "about",
                 "their", "which", "than", "more", "most", "some", "also", "into",
                 "over", "such", "only", "other", "would", "could", "should", "after",
                 "before", "according", "report", "reports", "reported", "study",
                 "studies", "found", "shows", "showed", "states", "stated", "says"}
    words = re.findall(r'[a-zA-Z]{4,}', fact_text.lower())
    key_words = [w for w in words if w not in stopwords][:5]

    # Extract year if present
    year_match = re.search(r'\b(20[12]\d)\b', fact_text)
    year = year_match.group(1) if year_match else ""

    parts = numbers[:2] + key_words[:4]
    if year:
        parts.append(year)

    return " ".join(parts)


def _prioritize_facts_for_verification(facts: list[dict], source_tiers: dict) -> list[tuple[int, dict]]:
    """
    Rank facts by verification priority:
    1. Statistical claims from unknown/Tier 3-4 sources (highest)
    2. Non-statistical claims from Tier 0 sources (expert quotes, case studies — need corroboration chance)
    3. Higher specificity (percentages > dollar amounts > general numbers)

    Returns: [(original_index, fact_dict), ...] sorted by priority
    """
    candidates = []

    for i, fact in enumerate(facts):
        source_url = fact.get("source_url", "")
        try:
            from urllib.parse import urlparse
            domain = urlparse(source_url).netloc.lower().replace("www.", "")
        except Exception:
            domain = ""

        tier = source_tiers.get(domain, 0)

        fact_text = fact.get("fact_text", "")
        is_statistical = _is_statistical_claim(fact_text)

        if not is_statistical and tier in (1, 2):
            # Non-statistical facts from Tier 1-2 are auto-trusted via faithfulness
            continue

        # Priority score: percentages most specific, then dollar, then general
        priority = 0
        if is_statistical:
            if "%" in fact_text or "percent" in fact_text.lower():
                priority = 3
            elif "$" in fact_text:
                priority = 2
            else:
                priority = 1
        else:
            # Non-statistical Tier 0 facts: lower priority than stats but still queue them
            priority = 0

        # Tier 1-2: deprioritize (faithfulness catches bad ones for free)
        if tier in (1, 2):
            priority -= 10

        candidates.append((i, fact, priority))

    # Sort by priority descending
    candidates.sort(key=lambda x: x[2], reverse=True)
    return [(idx, f) for idx, f, _ in candidates]


async def verify_fact_independently(
    fact_text: str,
    source_domain: str,
    source_tier: int,
    niche: str,
) -> dict:
    """
    Search Exa with Tier 1-2 domain filter to independently verify a claim.

    Returns: {
        status: 'corroborated' | 'corrected' | 'unverifiable',
        corroboration_url: str | None,
        corroboration_snippet: str | None,
        correction: str | None,
        score_adjustment: float,
    }
    Cost: ~$0.001 per Exa search
    """
    if not EXA_API_KEY:
        return {
            "status": "not_checked",
            "corroboration_url": None,
            "corroboration_snippet": None,
            "correction": None,
            "score_adjustment": 0.0,
        }

    query = _build_verification_query(fact_text)
    if not query.strip():
        return {
            "status": "not_checked",
            "corroboration_url": None,
            "corroboration_snippet": None,
            "correction": None,
            "score_adjustment": 0.0,
        }

    logger.debug(f"[FACT-CHECK] Searching Exa for: {query}")

    try:
        headers = {"x-api-key": EXA_API_KEY, "Content-Type": "application/json"}
        payload = {
            "query": query,
            "type": "auto",
            "num_results": 5,
            "use_autoprompt": True,
            "include_domains": _TIER_1_2_DOMAINS[:50],  # Exa limit
            "contents": {
                "text": {"max_characters": 2000}
            }
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post("https://api.exa.ai/search", headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        results = data.get("results", [])

        if not results:
            logger.debug(f"[FACT-CHECK] '{fact_text[:60]}...' -> UNVERIFIABLE (no authoritative results)")
            return {
                "status": "unverifiable",
                "corroboration_url": None,
                "corroboration_snippet": None,
                "correction": None,
                "score_adjustment": -0.5,
            }

        # Extract numbers from the original fact for comparison
        original_numbers = set()
        for m in _NUMBER_PATTERN.finditer(fact_text):
            original_numbers.add(m.group(1))
        for m in _DOLLAR_PATTERN.finditer(fact_text):
            original_numbers.add(m.group(1))

        # Check each result for corroboration or contradiction
        for r in results:
            result_text = r.get("text", "") or ""
            result_url = r.get("url", "")
            result_title = r.get("title", "")

            if not result_text:
                continue

            # Check if any of our original numbers appear in the authoritative source
            result_numbers = set()
            for m in _NUMBER_PATTERN.finditer(result_text):
                result_numbers.add(m.group(1))
            for m in _DOLLAR_PATTERN.finditer(result_text):
                result_numbers.add(m.group(1))

            matching_numbers = original_numbers & result_numbers
            if matching_numbers:
                # Numbers match - corroborated
                # Find the sentence containing the match for snippet
                snippet = ""
                for num in matching_numbers:
                    idx = result_text.find(num)
                    if idx >= 0:
                        start = max(0, idx - 100)
                        end = min(len(result_text), idx + 150)
                        snippet = result_text[start:end].strip()
                        break

                logger.debug(f"[FACT-CHECK] '{fact_text[:60]}...' -> CORROBORATED ({result_url})")

                return {
                    "status": "corroborated",
                    "corroboration_url": result_url,
                    "corroboration_snippet": snippet,
                    "correction": None,
                    "score_adjustment": 0.2,
                }

            # Numbers don't match - check if this is a correction
            # (result discusses same topic but different numbers)
            if result_numbers and original_numbers:
                # Both have numbers but they don't overlap => possible correction
                snippet = result_text[:300]
                logger.debug(
                    f"[FACT-CHECK] '{fact_text[:60]}...' -> CORRECTED "
                    f"(original: {original_numbers}, authoritative: {result_numbers}, source: {result_url})"
                )
                return {
                    "status": "corrected",
                    "corroboration_url": result_url,
                    "corroboration_snippet": snippet,
                    "correction": f"Authoritative source ({result_title}) reports different figures: {result_numbers}",
                    "score_adjustment": -0.3,
                }

        # No result had matching or conflicting numbers
        logger.debug(f"[FACT-CHECK] '{fact_text[:60]}...' -> UNVERIFIABLE (no number match in {len(results)} results)")

        return {
            "status": "unverifiable",
            "corroboration_url": None,
            "corroboration_snippet": None,
            "correction": None,
            "score_adjustment": -0.5,
        }

    except Exception as e:
        logger.error(f"[FACT-CHECK] Exa verification failed for '{fact_text[:60]}...': {e}")
        return {
            "status": "not_checked",
            "corroboration_url": None,
            "corroboration_snippet": None,
            "correction": None,
            "score_adjustment": 0.0,
        }


async def batch_verify_facts(
    facts: list[dict],
    source_tiers: dict,
    niche: str,
    max_searches: int = 5,
) -> dict:
    """
    Batch wrapper for independent fact verification.
    Prioritizes statistical claims from Tier 3-4/unknown sources.
    Runs up to max_searches Exa queries in parallel.

    Args:
        facts: list of fact dicts with fact_text, source_url, etc.
        source_tiers: {domain: tier_level} mapping
        niche: niche string for context
        max_searches: max Exa API calls (budget control)

    Returns: {fact_index: verification_result}
    """
    import asyncio

    candidates = _prioritize_facts_for_verification(facts, source_tiers)

    if not candidates:
        logger.debug(f"[FACT-BATCH] No statistical claims from Tier 3-4/unknown sources to verify")
        return {}

    # Limit to budget
    to_verify = candidates[:max_searches]
    skipped = len(candidates) - len(to_verify)

    if logger.isEnabledFor(logging.DEBUG):
        total_facts = len(facts)
        auto_trusted = total_facts - len(candidates)
        logger.debug(
            f"[FACT-BATCH] Verifying {len(to_verify)}/{total_facts} facts "
            f"({auto_trusted} auto-trusted Tier 1-2, {skipped} deprioritized)"
        )

    # Build verification tasks
    tasks = []
    indices = []
    for orig_idx, fact in to_verify:
        try:
            from urllib.parse import urlparse
            domain = urlparse(fact.get("source_url", "")).netloc.lower().replace("www.", "")
        except Exception:
            domain = ""

        tier = source_tiers.get(domain, 0)
        tasks.append(verify_fact_independently(
            fact_text=fact.get("fact_text", ""),
            source_domain=domain,
            source_tier=tier,
            niche=niche,
        ))
        indices.append(orig_idx)

    # Run in parallel
    results = await asyncio.gather(*tasks, return_exceptions=True)

    verification_map = {}
    for i, result in enumerate(results):
        orig_idx = indices[i]
        if isinstance(result, Exception):
            logger.error(f"[FACT-BATCH] Verification failed for fact #{orig_idx}: {result}")
            verification_map[orig_idx] = {
                "status": "not_checked",
                "corroboration_url": None,
                "corroboration_snippet": None,
                "correction": None,
                "score_adjustment": 0.0,
            }
        else:
            verification_map[orig_idx] = result

    # Summary log
    if logger.isEnabledFor(logging.DEBUG):
        statuses = Counter(v["status"] for v in verification_map.values())
        logger.debug(f"[FACT-BATCH] Results: {dict(statuses)}")

    return verification_map


# ============================================================
# Capability C: Fact Faithfulness Check (Free, Pure Python)
# ============================================================

def verify_fact_faithfulness(fact_text: str, source_content: str) -> dict:
    """
    Three-tier check that an extracted fact actually appears in its source.
    Pure Python, $0.00 cost.

    Returns: {is_grounded: bool, grounding_method: str, confidence_multiplier: float}
    """
    if not source_content or not fact_text:
        # Gap 7 fix: No content = cannot verify = not grounded
        return {"is_grounded": False, "grounding_method": "no_content", "confidence_multiplier": 0.3}

    fact_lower = fact_text.lower().strip()
    content_lower = source_content.lower()

    # Tier 1: Exact substring match (case-insensitive)
    if fact_lower in content_lower:
        logger.debug(f"[GROUNDING] '{fact_text[:60]}...' -> grounded (exact_match)")
        return {"is_grounded": True, "grounding_method": "exact_match", "confidence_multiplier": 1.0}

    # Tier 2: Number anchoring — extract numbers from fact, check proximity in source
    # Gap 10 fix: All fact numbers must appear within a 300-char window in the source.
    # Scattered numbers across different contexts = partial match, not full anchor.
    fact_numbers = set(re.findall(r'\d+(?:\.\d+)?', fact_text))
    if fact_numbers:
        matched_numbers = 0
        for num in fact_numbers:
            positions = [m.start() for m in re.finditer(re.escape(num), source_content)]
            if positions:
                matched_numbers += 1

        if matched_numbers == len(fact_numbers) and len(fact_numbers) >= 2:
            # Proximity check: all numbers must co-occur within 300 chars
            # Find positions of each number in source, check if any window contains all
            number_positions = {}
            for num in fact_numbers:
                number_positions[num] = [m.start() for m in re.finditer(re.escape(num), source_content)]

            # Check if there's a 300-char window containing at least one occurrence of each number
            proximity_ok = False
            # Use first number's positions as anchors
            anchor_num = list(fact_numbers)[0]
            for anchor_pos in number_positions.get(anchor_num, []):
                window_start = max(0, anchor_pos - 150)
                window_end = anchor_pos + 150
                all_in_window = True
                for other_num in fact_numbers:
                    if other_num == anchor_num:
                        continue
                    found_in_window = any(
                        window_start <= pos <= window_end
                        for pos in number_positions.get(other_num, [])
                    )
                    if not found_in_window:
                        all_in_window = False
                        break
                if all_in_window:
                    proximity_ok = True
                    break

            if proximity_ok:
                logger.debug(f"[GROUNDING] '{fact_text[:60]}...' -> grounded (number_anchor: all {len(fact_numbers)} numbers within 300-char window)")
                return {"is_grounded": True, "grounding_method": "number_anchor", "confidence_multiplier": 1.0}
            else:
                logger.debug(f"[GROUNDING] '{fact_text[:60]}...' -> partial (all {len(fact_numbers)} numbers found but scattered, no 300-char window)")
                return {"is_grounded": True, "grounding_method": "partial_number", "confidence_multiplier": 0.6}
        elif matched_numbers == len(fact_numbers) and len(fact_numbers) == 1:
            # Single number — no proximity needed, but lower confidence
            logger.debug(f"[GROUNDING] '{fact_text[:60]}...' -> grounded (number_anchor: single number found)")
            return {"is_grounded": True, "grounding_method": "number_anchor", "confidence_multiplier": 0.9}
        elif matched_numbers > 0:
            logger.debug(f"[GROUNDING] '{fact_text[:60]}...' -> partial ({matched_numbers}/{len(fact_numbers)} numbers found)")
            return {"is_grounded": True, "grounding_method": "partial_number", "confidence_multiplier": 0.6}

    # Tier 3: N-gram overlap — 4-word n-grams, require >= 55% overlap
    # Gap 16 fix: Raised from 40% to 55%. Same-topic articles share enough jargon
    # n-grams to hit 40% trivially; 55% requires genuine content overlap.
    fact_words = re.findall(r'\w+', fact_lower)
    if len(fact_words) >= 4:
        fact_ngrams = set()
        for i in range(len(fact_words) - 3):
            fact_ngrams.add(" ".join(fact_words[i:i + 4]))

        if fact_ngrams:
            matched = sum(1 for ng in fact_ngrams if ng in content_lower)
            overlap = matched / len(fact_ngrams)

            if overlap >= 0.55:
                logger.debug(f"[GROUNDING] '{fact_text[:60]}...' -> grounded (ngram_overlap: {overlap:.0%})")
                return {"is_grounded": True, "grounding_method": "ngram_overlap", "confidence_multiplier": 0.9}

    # Failed all three tiers — ungrounded
    logger.debug(f"[GROUNDING] '{fact_text[:60]}...' -> UNGROUNDED (no match in source)")

    return {"is_grounded": False, "grounding_method": "none", "confidence_multiplier": 0.5}


# ============================================================
# Capability D: Post-Writer Claim Cross-Referencing
# ============================================================


def _normalize_url(url: str) -> str:
    """
    Normalize URL for matching: strip trailing slash, query params, lowercase netloc, strip www.
    'https://www.nist.gov/path/page?q=1' -> 'https://nist.gov/path/page'
    """
    try:
        from urllib.parse import urlparse, urlunparse
        parsed = urlparse(url)
        netloc = parsed.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        path = parsed.path.rstrip("/")
        return urlunparse((parsed.scheme, netloc, path, "", "", ""))
    except Exception:
        return url.strip().rstrip("/")


def _path_prefix_match(url_a: str, url_b: str) -> bool:
    """
    Check if two URLs share the same domain AND first path segment.
    'nist.gov/cybersecurity/page-a' matches 'nist.gov/cybersecurity/page-b'.
    'nist.gov/ai/report' does NOT match 'nist.gov/cybersecurity/page-b'.
    """
    try:
        from urllib.parse import urlparse
        pa = urlparse(url_a)
        pb = urlparse(url_b)
        domain_a = pa.netloc.lower().replace("www.", "", 1)
        domain_b = pb.netloc.lower().replace("www.", "", 1)
        if domain_a != domain_b:
            return False
        seg_a = pa.path.strip("/").split("/")[0] if pa.path.strip("/") else ""
        seg_b = pb.path.strip("/").split("/")[0] if pb.path.strip("/") else ""
        return seg_a == seg_b and seg_a != ""
    except Exception:
        return False


# Pattern: [anchor text](url) or [anchor](url "title")
_CITATION_LINK_PATTERN = re.compile(
    r'\[([^\]]+)\]\(([^)\s]+)(?:\s+"[^"]*")?\)'
)

# Pattern for quantitative claims near citations
_QUANT_CLAIM_PATTERN = re.compile(
    r'(?:(?:\d+(?:\.\d+)?)\s*(?:%|percent|million|billion|trillion|M\b|B\b|K\b)'
    r'|\$\s*\d+(?:\.\d+)?(?:\s*(?:million|billion|trillion|M\b|B\b|K\b))?)',
    re.IGNORECASE
)


def detect_unverified_entities(
    draft_text: str,
    citation_urls: list[str],
    citation_anchors: list[str] | None = None,
) -> list[str]:
    """
    Detect product/tool/brand names in writer draft that aren't backed by any citation source.
    Catches hallucinated tools like "LoRA AI", "iTerm AI", "Caktus AI" that the writer
    invents from training data.

    Args:
        draft_text: Section markdown from the writer
        citation_urls: List of source_url values from the citation map
        citation_anchors: Optional list of citation_anchor texts for name matching

    Returns: List of unverified entity names (empty = all entities verified or no entities found)
    """
    # --- Step 1: Extract product/tool name candidates from draft ---
    # Pre-strip markdown structures that produce false positives:
    # - Headings use Title Case by convention (not product names)
    # - Link anchors/URLs are citation markup, not prose claims
    scan_text = re.sub(r'^#{1,6}\s+.*$', '', draft_text, flags=re.MULTILINE)
    scan_text = re.sub(r'\[([^\]]+)\]\([^)]+\)', '', scan_text)

    # Pattern: Capitalized word(s) followed by a tech product suffix
    _PRODUCT_SUFFIXES = r'(?:AI|ML|Cloud|Pro|Plus|Enterprise|Suite|Platform|Studio|Labs?|Hub|Tools?|Software|Engine|API)'
    # Match "Word AI", "Two Words AI", "Word-Word AI"
    product_pattern = re.compile(
        r'\b([A-Z][a-zA-Z]*(?:[\s\-][A-Z][a-zA-Z]*)*\s+' + _PRODUCT_SUFFIXES + r')\b'
    )
    # Also match standalone capitalized product names (e.g., "Zapier", "Perplexity", "Gencraft")
    standalone_pattern = re.compile(
        r'\b([A-Z][a-z]{2,}(?:\.ai|\.io|\.co)?)\b'
    )

    # Collect candidate product names
    candidates = set()
    for m in product_pattern.finditer(scan_text):
        name = m.group(1).strip()
        if len(name) >= 4:  # Skip very short matches
            candidates.add(name)

    for m in standalone_pattern.finditer(scan_text):
        name = m.group(1).strip()
        # Only keep standalone names that look like products (not common English words)
        if len(name) >= 4 and name.lower() not in _COMMON_WORDS:
            candidates.add(name)

    if not candidates:
        return []

    # --- Step 2: Build known entities from citation sources ---
    known_entities = set()

    # Extract domain basenames from citation URLs (zapier.com → "zapier")
    for url in citation_urls:
        try:
            from urllib.parse import urlparse
            domain = urlparse(url).netloc.lower().replace("www.", "")
            basename = domain.split(".")[0]
            if basename:
                known_entities.add(basename.lower())
                known_entities.add(domain.lower())
        except Exception:
            pass

    # Extract names from citation anchors (e.g., "Salesforce 2024" → "salesforce")
    if citation_anchors:
        for anchor in citation_anchors:
            words = re.findall(r'[A-Za-z]{3,}', anchor)
            for w in words:
                known_entities.add(w.lower())

    # Also add all citation URL text as-is for broad matching
    all_urls_text = " ".join(citation_urls).lower()

    # --- Step 3: Check each candidate against known entities ---
    unverified = []
    for candidate in sorted(candidates):
        candidate_lower = candidate.lower()
        # Extract the core name (strip suffix like " AI", " Platform")
        core_name = re.sub(r'\s+(' + _PRODUCT_SUFFIXES + r')$', '', candidate, flags=re.IGNORECASE).strip().lower()

        # Check if core name or full name appears in known entities
        is_known = (
            core_name in known_entities
            or candidate_lower in known_entities
            or any(core_name in entity for entity in known_entities)
            or core_name in all_urls_text
        )

        if not is_known and core_name not in _TECH_TERMS:
            unverified.append(candidate)

    if unverified:
        logger.info(f"[ENTITY-GATE] {len(unverified)} unverified entities: {unverified[:5]}")

    return unverified


# Legitimate tech brands/terms that are NOT hallucinated products
_TECH_TERMS = frozenset({
    "anthropic", "openai", "chatgpt", "claude", "gemini", "deepseek",
    "agentic", "generative", "multimodal", "transformer", "neural",
    "copilot", "midjourney", "perplexity", "mistral", "llama", "meta",
    "google", "microsoft", "amazon", "nvidia", "hugging", "huggingface",
})

# Common English words that should NOT be flagged as product names
_COMMON_WORDS = frozenset({
    "the", "this", "that", "these", "those", "what", "which", "where", "when",
    "with", "from", "into", "onto", "over", "under", "above", "below", "between",
    "through", "during", "before", "after", "about", "against", "along", "among",
    "around", "behind", "beyond", "despite", "down", "except", "inside", "near",
    "off", "outside", "past", "since", "toward", "upon", "within", "without",
    "also", "just", "only", "even", "still", "already", "always", "never",
    "often", "sometimes", "usually", "very", "really", "quite", "rather",
    "here", "there", "then", "than", "both", "each", "every", "either",
    "neither", "most", "much", "many", "more", "some", "such", "other",
    # Common text words that get capitalized at sentence start
    "companies", "businesses", "organizations", "enterprises", "teams",
    "however", "therefore", "moreover", "furthermore", "meanwhile",
    "according", "because", "although", "while", "since", "until",
    "small", "medium", "large", "first", "second", "third", "next",
    "best", "better", "most", "least", "last", "new", "old",
    # Common section keywords
    "introduction", "conclusion", "overview", "summary", "example",
    "step", "steps", "guide", "tips", "ways", "reasons", "benefits",
    # Generic tech terms (not specific products)
    "artificial", "intelligence", "machine", "learning", "deep",
    "automation", "analytics", "data", "digital", "technology",
    "cybersecurity", "security", "network", "cloud", "server",
    "marketing", "content", "customer", "business", "service",
    "implementation", "integration", "optimization", "performance",
    "research", "report", "study", "survey", "analysis", "finding",
    # Verbs (capitalized at sentence start, flagged as products)
    "build", "keep", "adapt", "fix", "fail", "change", "create", "start",
    "use", "make", "find", "take", "give", "tell", "work", "run", "try",
    "apply", "follow", "include", "provide", "offer", "improve", "test",
    "compare", "write", "read", "learn", "think", "know", "need", "want",
    "help", "show", "call", "move", "turn", "play", "feel", "become",
    "consider", "suggest", "require", "expect", "allow", "remain",
    "reduce", "avoid", "imagine", "understand", "describe", "explain",
    "generate", "produce", "develop", "design", "define", "measure",
    # Nouns/adjectives that get sentence-start capitalized
    "advice", "approach", "attempt", "anchor", "audit", "average",
    "blank", "chain", "cleaner", "coding", "complex", "cost",
    "editing", "everyone", "fast", "formula", "missing", "nearly",
    "sounds", "standard", "common", "bad", "simple", "real", "full",
    "long", "clear", "high", "low", "open", "free", "basic",
    "human", "model", "prompt", "response", "output", "input",
    "tool", "system", "process", "method", "result", "problem",
    "solution", "answer", "question", "context", "pattern", "task",
    "format", "style", "structure", "section", "paragraph", "sentence",
    "word", "text", "image", "video", "code", "file",
})


def extract_article_claims(article_text: str) -> list[dict]:
    """
    Regex-only extraction of claim + adjacent citation URL pairs from article markdown.
    $0.00 cost.

    Returns: [{claim_text, citation_url, citation_anchor, has_quantitative_claim}]
    """
    claims = []

    # Find all citation links
    for match in _CITATION_LINK_PATTERN.finditer(article_text):
        anchor = match.group(1)
        url = match.group(2)
        link_start = match.start()

        # Get surrounding context (300 chars before the citation)
        context_start = max(0, link_start - 300)
        context = article_text[context_start:link_start].strip()

        # Find the most recent explicit sentence containing the citation
        raw_sentences = re.split(r'(?<=[.!?])\s+', context)
        valid_sentences = [s for s in raw_sentences if len(s.strip()) > 5]
        
        claim_text = valid_sentences[-1] if valid_sentences else context[-200:]
        claim_stripped = claim_text.strip()

        # Skip bare resource/reference links that aren't factual claims:
        # e.g. "## Resources\n- [Link text](url)" or "- [Title](url)"
        # A real claim has substantive text before the link, not just headings/list markers
        if len(claim_stripped) < 20:
            continue
        # Skip if context is only headings, list markers, or link anchors (no prose)
        context_no_markup = re.sub(r'[#\-*>\[\]():|\n]', ' ', claim_stripped).strip()
        context_words = [w for w in context_no_markup.split() if len(w) > 2]
        if len(context_words) < 4:
            continue

        # Check if claim contains quantitative data
        has_quant = bool(_QUANT_CLAIM_PATTERN.search(claim_stripped))

        # If the LLM cited a narrative/summary sentence without statistics, ignore the citation.
        # This prevents the verification loop from choking on "flavor text" citations.
        if not has_quant:
            continue

        claims.append({
            "claim_text": claim_stripped,
            "citation_url": url.strip(),
            "citation_anchor": anchor.strip(),
            "has_quantitative_claim": has_quant,
        })

    if logger.isEnabledFor(logging.DEBUG):
        quant_count = sum(1 for c in claims if c["has_quantitative_claim"])
        logger.debug(f"[CLAIM-EXTRACT] Found {len(claims)} cited claims ({quant_count} with quantitative data)")

    return claims


def detect_uncited_claims(article_text: str, cited_claims: list[dict]) -> list[dict]:
    """
    Find factual claims (stats, percentages, dollar amounts) that lack citations.
    Returns: [{claim_text, reason}]
    """
    uncited = []

    # Get all cited sentence texts to avoid double-flagging
    cited_texts = {c["claim_text"] for c in cited_claims}

    # Split article into sentences
    sentences = re.split(r'(?<=[.!?])\s+', article_text)

    for sentence in sentences:
        stripped = sentence.strip()
        if len(stripped) < 20:
            continue
        # Skip headings, list markers, and markdown tables
        if stripped.startswith('#') or stripped.startswith('- ') or stripped.startswith('* ') or stripped.startswith('|'):
            continue
        if '|' in stripped and len(stripped.split('|')) > 2:
            continue
        # Skip gracefully if it looks like a malformed markdown link typo (e.g. LLM forgot opening bracket)
        if '](http' in stripped:
            continue
        # Check if sentence has quantitative data
        if not _QUANT_CLAIM_PATTERN.search(stripped):
            continue
        # Check if this sentence already has a citation (markdown link)
        if _CITATION_LINK_PATTERN.search(stripped):
            continue
        # Check if it overlaps with an already-cited claim
        if any(stripped in ct or ct in stripped for ct in cited_texts):
            continue

        uncited.append({
            "claim_text": stripped[:200],
            "reason": "Factual claim with statistic/percentage/dollar amount but no citation",
        })

    if uncited:
        logger.debug(f"[CLAIM-UNCITED] Found {len(uncited)} uncited factual claims")

    return uncited


# Stopwords excluded from context matching
_MATCH_STOPWORDS = frozenset({
    "the", "and", "for", "that", "with", "this", "from", "are", "was", "were",
    "has", "have", "had", "not", "but", "can", "will", "more", "than", "also",
    "their", "they", "been", "which", "about", "into", "over", "such", "many",
    "most", "some", "other", "would", "could", "should", "after", "before",
    "report", "reports", "show", "shows", "found", "says", "said", "according",
})


def _context_words_near_number(text: str, number: str, window: int = 80) -> set:
    """Extract significant words (4+ chars, not stopwords) within `window` chars of a number."""
    words = set()
    text_lower = text.lower()
    idx = 0
    while True:
        pos = text_lower.find(number, idx)
        if pos == -1:
            break
        start = max(0, pos - window)
        end = min(len(text_lower), pos + len(number) + window)
        snippet = text_lower[start:end]
        for w in re.findall(r'[a-zA-Z]{4,}', snippet):
            if w not in _MATCH_STOPWORDS:
                words.add(w)
        idx = pos + 1
    return words


def _numbers_match(claim_text: str, fact_text: str) -> bool:
    """
    Context-aware number matching.
    Requires: shared number + at least 2 shared context words near that number.
    Prevents '67% of CTOs prioritize AI' matching '67% of users report bugs'.
    """
    claim_numbers = set(re.findall(r'\d+(?:\.\d+)?', claim_text))
    fact_numbers = set(re.findall(r'\d+(?:\.\d+)?', fact_text))
    significant = claim_numbers & fact_numbers

    for n in significant:
        # Get context words near this number in both texts
        claim_context = _context_words_near_number(claim_text, n)
        fact_context = _context_words_near_number(fact_text, n)
        shared_context = claim_context & fact_context

        if len(shared_context) >= 2:
            return True

    return False


def cross_reference_claims(
    article_claims: list[dict],
    fact_citations: list,
    source_content_map: dict | None = None,
) -> dict:
    """
    For each cited claim in the article, verify it matches a FactCitation.

    Args:
        article_claims: from extract_article_claims()
        fact_citations: list of FactCitation ORM objects
        source_content_map: {url: content} for LLM fallback context

    Returns: {
        total_claims: int,
        verified: int,
        fabricated: int,
        uncited: int,
        details: [{claim_text, status, matched_fact, source_url}],
        passed: bool,
    }
    """
    # Build URL -> facts index
    url_facts_map = {}
    for fc in fact_citations:
        url = fc.source_url
        if url not in url_facts_map:
            url_facts_map[url] = []
        url_facts_map[url].append(fc)

    details = []
    verified_count = 0
    fabricated_count = 0
    ambiguous_claims = []  # For LLM fallback

    for claim in article_claims:
        claim_url = claim["citation_url"]
        claim_text = claim["claim_text"]

        # Find FactCitations for this URL
        # Step 1: Exact URL match
        matched_facts = url_facts_map.get(claim_url, [])

        # Step 2: Normalized URL match (strip query params, trailing slash, www)
        if not matched_facts:
            normalized_claim = _normalize_url(claim_url)
            for url, facts in url_facts_map.items():
                if _normalize_url(url) == normalized_claim:
                    matched_facts = facts
                    break

        # Step 3: Path-prefix match (same domain + same first path segment)
        if not matched_facts:
            for url, facts in url_facts_map.items():
                if _path_prefix_match(claim_url, url):
                    matched_facts = facts
                    break

        # Step 4: Domain fallback match (Allows LLM fallback to handle the truth check if URL is truncated)
        if not matched_facts:
            try:
                from urllib.parse import urlparse
                claim_domain = urlparse(claim_url).netloc.lower().replace("www.", "")
                for url, facts in url_facts_map.items():
                    fact_domain = urlparse(url).netloc.lower().replace("www.", "")
                    if claim_domain == fact_domain and claim_domain != "":
                        matched_facts = facts
                        break
            except Exception:
                pass

        # NOTE: Bare domain-level matching restored as LLM fallback gate properly handles hallucinated paths.
        if not matched_facts:
            fabricated_count += 1
            details.append({
                "claim_text": claim_text[:200],
                "status": "fabricated",
                "matched_fact": None,
                "source_url": claim_url,
                "reason": "No verified facts matched this URL (checked: exact, normalized, path-prefix)",
            })
            logger.debug(f"[CLAIM-XREF] FABRICATED: '{claim_text[:60]}...' cites {claim_url} (no URL match)")
            continue

        # Try number-matching first
        matched = False
        for fc in matched_facts:
            if _numbers_match(claim_text, fc.fact_text):
                verified_count += 1
                details.append({
                    "claim_text": claim_text[:200],
                    "status": "verified",
                    "matched_fact": fc.fact_text[:200],
                    "source_url": claim_url,
                    "reason": "Number match with verified fact",
                })
                matched = True
                logger.debug(f"[CLAIM-XREF] Claim '{claim_text[:50]}...' matched FactCitation #{fc.id} via number_anchor")
                break

        if not matched:
            # No number match — try text similarity
            for fc in matched_facts:
                # Simple word overlap check
                claim_words = set(re.findall(r'\w{4,}', claim_text.lower()))
                fact_words = set(re.findall(r'\w{4,}', fc.fact_text.lower()))
                if claim_words and fact_words:
                    overlap = len(claim_words & fact_words) / min(len(claim_words), len(fact_words))
                    if overlap >= CLAIM_TEXT_SIMILARITY_THRESHOLD:
                        verified_count += 1
                        details.append({
                            "claim_text": claim_text[:200],
                            "status": "verified",
                            "matched_fact": fc.fact_text[:200],
                            "source_url": claim_url,
                            "reason": f"Text similarity ({overlap:.0%} word overlap)",
                        })
                        matched = True
                        logger.debug(f"[CLAIM-XREF] Claim '{claim_text[:50]}...' matched via text_similarity ({overlap:.0%})")
                        break

        if not matched:
            # Ambiguous — queue for LLM fallback
            ambiguous_claims.append({
                "claim": claim,
                "candidate_facts": matched_facts,
            })

    # Handle ambiguous claims (will be resolved by caller with LLM if needed)
    for amb in ambiguous_claims:
        # Default to warning (not fabricated) since source exists in map
        # Gap 32: Include candidate facts so feedback can show writer what's actually available
        candidate_texts = [fc.fact_text[:150] for fc in amb["candidate_facts"][:3]]
        details.append({
            "claim_text": amb["claim"]["claim_text"][:200],
            "status": "ambiguous",
            "matched_fact": None,
            "source_url": amb["claim"]["citation_url"],
            "reason": "Source in map but no clear fact match (needs LLM verification)",
            "candidate_facts": candidate_texts,
        })

    passed = fabricated_count == 0

    result = {
        "total_claims": len(article_claims),
        "verified": verified_count,
        "fabricated": fabricated_count,
        "ambiguous": len(ambiguous_claims),
        "details": details,
        "passed": passed,
        "ambiguous_claims": ambiguous_claims,
    }

    if logger.isEnabledFor(logging.DEBUG):
        status = "PASSED" if passed else "FAILED"
        logger.debug(
            f"[CLAIM-GATE] {status}: {verified_count}/{len(article_claims)} verified, "
            f"{fabricated_count} fabricated, {len(ambiguous_claims)} ambiguous"
        )

    return result


async def verify_claim_with_llm(
    claim_text: str,
    fact_candidates: list,
    source_snippet: str | None = None,
) -> dict:
    """
    LLM fallback for ambiguous claims where number/text matching failed.
    Max 2 calls per article to control cost (~$0.0001 per call).

    Returns: {supported: bool, matched_fact_text: str | None, reasoning: str}
    """
    if not DEEPSEEK_API_KEY:
        return {"supported": False, "matched_fact_text": None, "reasoning": "No API key"}

    try:
        fact_list = "\n".join(
            f"  {i+1}. \"{fc.fact_text}\""
            for i, fc in enumerate(fact_candidates[:5])
        )

        context = ""
        if source_snippet:
            context = f"\nSOURCE CONTEXT (snippet):\n{source_snippet[:LLM_SOURCE_CONTEXT_CHARS]}\n"

        prompt = f"""Does this article claim match or is it supported by any of the verified facts from the same source?

ARTICLE CLAIM: "{claim_text}"

VERIFIED FACTS FROM SOURCE:
{fact_list}
{context}
IMPORTANT: The writer paraphrases facts in its own tone. Accept the claim as SUPPORTED if:
- The core fact, statistic, or percentage is present in any verified fact (even if worded differently)
- The claim is a reasonable summary or restatement of information in the verified facts or source context
- Numbers expressed differently still count (e.g., "67%" vs "nearly seven in ten", "4,500" vs "thousands")

Mark as UNSUPPORTED only if the claim introduces a fact, number, or statistic NOT found anywhere in the verified facts or source context.

Return JSON:
{{
  "supported": true/false,
  "matched_fact_index": 1,
  "reasoning": "Brief explanation"
}}
Only return JSON."""

        headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": DEEPSEEK_MODEL,
            "messages": [
                {"role": "system", "content": "You output valid JSON ONLY."},
                {"role": "user", "content": prompt}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(DEEPSEEK_API_URL, headers=headers, json=payload)
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"].strip()

        result = json.loads(text)
        supported = result.get("supported", False)
        matched_idx = result.get("matched_fact_index")
        matched_fact_text = None

        if supported and matched_idx and 1 <= matched_idx <= len(fact_candidates):
            matched_fact_text = fact_candidates[matched_idx - 1].fact_text

        if logger.isEnabledFor(logging.DEBUG):
            status = "supported" if supported else "unsupported"
            logger.debug(f"[CLAIM-LLM] Ambiguous claim -> {status}: {result.get('reasoning', '')[:80]}")

        return {
            "supported": supported,
            "matched_fact_text": matched_fact_text,
            "reasoning": result.get("reasoning", ""),
        }

    except Exception as e:
        logger.error(f"[CLAIM-LLM] LLM verification failed: {e}")
        return {"supported": False, "matched_fact_text": None, "reasoning": f"LLM call failed: {e}"}


def format_claim_verification_feedback(verification_result: dict) -> str:
    """
    Format claim-level feedback for writer retries.
    Replaces generic 'cite more sources' with specific fix instructions.

    Gap 32: Shows candidate facts so writer knows what to use instead of just removing claims.
    Gap 33: Separates FABRICATED (URL not in map) from UNGROUNDED (URL exists, claim doesn't match).
    """
    lines = []

    fabricated = [d for d in verification_result["details"] if d["status"] == "fabricated"]
    ungrounded = [d for d in verification_result["details"] if d["status"] == "ungrounded"]
    ambiguous = [d for d in verification_result["details"] if d["status"] == "ambiguous"]

    if fabricated:
        lines.append("FABRICATED CITATIONS (URL not in citation map - must fix):")
        for i, d in enumerate(fabricated, 1):
            lines.append(f"  {i}. \"{d['claim_text'][:120]}...\"")
            lines.append(f"     Cites: {d['source_url']}")
            lines.append(f"     Problem: {d['reason']}")
            lines.append(f"     Fix: Remove this claim entirely OR replace with a fact from the citation map.")
        lines.append("")

    if ungrounded:
        lines.append("UNGROUNDED CITATIONS (URL exists but claim doesn't match source facts - must fix):")
        for i, d in enumerate(ungrounded, 1):
            lines.append(f"  {i}. \"{d['claim_text'][:120]}...\"")
            lines.append(f"     Cites: {d['source_url']}")
            lines.append(f"     Problem: Your paraphrase doesn't match any verified fact from this source.")
            # Gap 32: Show candidate facts so writer can use the correct ones
            candidates = d.get("candidate_facts", [])
            if candidates:
                lines.append(f"     Available facts from this source:")
                for j, fact in enumerate(candidates[:3], 1):
                    lines.append(f"       {j}. \"{fact}\"")
            lines.append(f"     Fix: Rewrite using one of the available facts above, or remove the claim.")
        lines.append("")

    if ambiguous:
        lines.append("AMBIGUOUS CITATIONS (needs clarification):")
        for i, d in enumerate(ambiguous, 1):
            lines.append(f"  {i}. \"{d['claim_text'][:120]}...\"")
            lines.append(f"     Cites: {d['source_url']}")
            lines.append(f"     Problem: {d['reason']}")
            # Gap 32: Show candidate facts for ambiguous claims too
            candidates = d.get("candidate_facts", [])
            if candidates:
                lines.append(f"     Available facts from this source:")
                for j, fact in enumerate(candidates[:3], 1):
                    lines.append(f"       {j}. \"{fact}\"")
            lines.append(f"     Fix: Rewrite to closely match one of the available facts above.")
        lines.append("")

    uncited = verification_result.get("uncited", [])
    if uncited:
        lines.append("UNCITED FACTUAL CLAIMS (must add citation from the citation map):")
        for i, d in enumerate(uncited, 1):
            lines.append(f"  {i}. \"{d['claim_text'][:120]}\"")
            lines.append(f"     Problem: {d['reason']}")
            lines.append(f"     Fix: Add a [Source](URL) citation from the citation map, or remove the claim.")
        lines.append("")

    # Attribution-URL mismatches
    attr_mismatches = verification_result.get("attribution_mismatches", [])
    if attr_mismatches:
        lines.append("ATTRIBUTION-URL MISMATCHES (named org doesn't match citation domain - must fix):")
        for i, m in enumerate(attr_mismatches, 1):
            lines.append(f"  {i}. \"{m['claim_text']}\"")
            lines.append(f"     Names: {m['named_org']}")
            lines.append(f"     But links to: {m['citation_domain']} ({m['citation_url']})")
            lines.append(f"     Fix: Either link to {m['named_org']}'s official domain, or remove the {m['named_org']} attribution.")
        lines.append("")

    # Summary
    total = verification_result["total_claims"]
    verified = verification_result["verified"]
    fab = verification_result["fabricated"]
    amb = verification_result.get("ambiguous", 0)
    ung = verification_result.get("ungrounded", 0)
    unc = len(uncited)
    mis = len(attr_mismatches)

    lines.append(f"CLAIM VERIFICATION: {verified}/{total} verified, {fab} fabricated, {ung} ungrounded, {amb} ambiguous, {unc} uncited, {mis} attribution mismatches")

    if fab > 0 or ung > 0 or unc > 0 or mis > 0:
        lines.append("STATUS: FAILED - Fix all fabricated, ungrounded, uncited, and misattributed claims before retry.")
    else:
        lines.append("STATUS: PASSED")

    return "\n".join(lines)
