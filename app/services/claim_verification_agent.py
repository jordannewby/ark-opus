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

from ..settings import DEEPSEEK_API_KEY, EXA_API_KEY, DEBUG_MODE
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


async def detect_ai_generated_content(content: str) -> dict:
    """
    Single DeepSeek Reasoner call to evaluate 6 signals that distinguish
    human writing from LLM output.

    Returns: {ai_probability: 0.0-1.0, signals: dict, reasoning: str}
    Cost: ~$0.00005 per call
    """
    if not content or len(content) < 200:
        return {"ai_probability": 0.3, "signals": {}, "deterministic_signals": {}, "reasoning": "Content too short to assess"}

    # Compute deterministic signals first (free, instant)
    det_signals = _compute_deterministic_ai_signals(content)
    det_human_score = det_signals["avg_human_score"]

    try:
        prompt = f"""You are an AI content detection specialist. Analyze this text for signals that distinguish human-written content from LLM-generated content.

TEXT (first 3000 chars):
{content[:3000]}

Score each signal 0.0-1.0 where 1.0 = strongly human, 0.0 = strongly AI-generated:

1. lexical_diversity: Does vocabulary vary naturally? LLMs use unnaturally even vocabulary distributions.
   1.0 = varied, idiosyncratic word choices | 0.0 = smooth, evenly distributed vocabulary

2. sentence_rhythm: Do sentence lengths vary naturally? LLMs produce uniform sentence structures.
   1.0 = irregular lengths, fragments, run-ons | 0.0 = uniform sentence lengths throughout

3. hedging_patterns: Are hedging phrases natural or formulaic? LLMs insert "It's important to note..." at regular intervals.
   1.0 = rare or contextual hedging | 0.0 = formulaic hedging every few paragraphs

4. transition_formulaism: Are transitions natural? LLMs rely on "Furthermore... Moreover... Additionally..."
   1.0 = varied, natural flow | 0.0 = template transition words throughout

5. specificity_gradient: Are specifics distributed naturally? Humans front-load expertise; LLMs distribute evenly.
   1.0 = uneven distribution of detail | 0.0 = evenly distributed specifics

6. idiosyncrasy: Does the text have a unique voice? LLMs avoid informal patterns, fragments, asides.
   1.0 = clear personal voice, quirks, opinions | 0.0 = generic, voiceless, perfectly formal

Return JSON only:
{{
  "signals": {{
    "lexical_diversity": 0.7,
    "sentence_rhythm": 0.6,
    "hedging_patterns": 0.8,
    "transition_formulaism": 0.7,
    "specificity_gradient": 0.5,
    "idiosyncrasy": 0.6
  }},
  "ai_probability": 0.35,
  "reasoning": "Brief explanation of key indicators"
}}

ai_probability = 1.0 - average(all signals). Only return JSON."""

        headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": "deepseek-reasoner",
            "messages": [
                {"role": "system", "content": "You output valid JSON ONLY."},
                {"role": "user", "content": prompt}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.3,
        }

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(DEEPSEEK_API_URL, headers=headers, json=payload)
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"].strip()

        result = json.loads(text)
        signals = result.get("signals", {})

        # Validate: recalculate ai_probability from signals
        if signals and len(signals) == 6:
            avg_human = sum(signals.values()) / 6
            calculated_ai_prob = round(1.0 - avg_human, 3)
            reported_ai_prob = result.get("ai_probability", calculated_ai_prob)
            # Use calculated if reported is way off
            if abs(calculated_ai_prob - reported_ai_prob) > 0.15:
                ai_probability = calculated_ai_prob
            else:
                ai_probability = reported_ai_prob
        else:
            ai_probability = result.get("ai_probability", 0.3)

        # --- Merge deterministic and LLM signals ---
        det_ai_prob = round(1.0 - det_human_score, 3)
        delta = abs(ai_probability - det_ai_prob)

        if delta <= 0.2:
            # Agreement: trust LLM (more nuanced)
            final_ai_prob = ai_probability
        elif ai_probability < 0.5 and det_ai_prob >= 0.5 and delta > 0.3:
            # LLM says human, deterministic says AI: average (don't let LLM override clear signals)
            final_ai_prob = round((ai_probability + det_ai_prob) / 2, 3)
        elif ai_probability >= 0.5 and det_ai_prob < 0.5 and delta > 0.3:
            # LLM says AI, deterministic says human: trust deterministic (measurements > opinion)
            final_ai_prob = det_ai_prob
        else:
            # Moderate disagreement: weighted average (60% LLM, 40% deterministic)
            final_ai_prob = round(ai_probability * 0.6 + det_ai_prob * 0.4, 3)

        ai_probability = final_ai_prob

        if DEBUG_MODE:
            sig_str = ", ".join(f"{k}={v}" for k, v in signals.items())
            print(
                f"[AI-DETECT] LLM signals: {sig_str} | "
                f"Deterministic: ttr={det_signals['ttr']}, var={det_signals['sentence_variance']}, "
                f"hedge={det_signals['hedging']}, trans={det_signals['transitions']} | "
                f"merged ai_prob={ai_probability:.2f}"
            )

        return {
            "ai_probability": round(ai_probability, 3),
            "signals": signals,
            "deterministic_signals": det_signals,
            "reasoning": result.get("reasoning", ""),
        }

    except json.JSONDecodeError as e:
        logger.error(f"[AI-DETECT] JSON parse error: {e}")
        det_ai_prob = round(1.0 - det_human_score, 3)
        return {"ai_probability": det_ai_prob, "signals": {}, "deterministic_signals": det_signals, "reasoning": "LLM failed, using deterministic only"}
    except Exception as e:
        logger.error(f"[AI-DETECT] Detection failed: {e}")
        det_ai_prob = round(1.0 - det_human_score, 3)
        return {"ai_probability": det_ai_prob, "signals": {}, "deterministic_signals": det_signals, "reasoning": f"LLM failed: {e}, using deterministic only"}


def compute_ai_detection_penalty(ai_result: dict) -> float:
    """
    Penalty applied AFTER 7-factor scoring, BEFORE rescue bonus.
    Returns negative float (penalty) or 0.0.
    """
    ai_prob = ai_result.get("ai_probability", 0.0)

    if ai_prob >= 0.85:
        penalty = -15.0
    elif ai_prob >= 0.70:
        penalty = -10.0
    elif ai_prob >= 0.55:
        penalty = -5.0
    else:
        penalty = 0.0

    if penalty != 0.0 and DEBUG_MODE:
        print(f"[AI-DETECT] Penalty: {penalty} pts (ai_probability={ai_prob:.2f})")

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
    1. Statistical claims from unknown/Tier 3-4 sources
    2. Higher specificity (percentages > dollar amounts > general numbers)

    Returns: [(original_index, fact_dict), ...] sorted by priority
    """
    candidates = []

    for i, fact in enumerate(facts):
        source_url = fact.get("source_url", "")
        # Extract domain from URL
        try:
            from urllib.parse import urlparse
            domain = urlparse(source_url).netloc.lower().replace("www.", "")
        except Exception:
            domain = ""

        tier = source_tiers.get(domain, 0)

        fact_text = fact.get("fact_text", "")
        if not _is_statistical_claim(fact_text):
            continue

        # Priority score: percentages most specific, then dollar, then general
        priority = 0
        if "%" in fact_text or "percent" in fact_text.lower():
            priority = 3
        elif "$" in fact_text:
            priority = 2
        else:
            priority = 1

        # Tier 1-2: deprioritize (faithfulness catches bad ones for free)
        # but include so they can be Exa-checked if budget allows
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

    if DEBUG_MODE:
        print(f"[FACT-CHECK] Searching Exa for: {query}")

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
            if DEBUG_MODE:
                print(f"[FACT-CHECK] '{fact_text[:60]}...' -> UNVERIFIABLE (no authoritative results)")
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

                if DEBUG_MODE:
                    print(f"[FACT-CHECK] '{fact_text[:60]}...' -> CORROBORATED ({result_url})")

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
                if DEBUG_MODE:
                    print(
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
        if DEBUG_MODE:
            print(f"[FACT-CHECK] '{fact_text[:60]}...' -> UNVERIFIABLE (no number match in {len(results)} results)")

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
        if DEBUG_MODE:
            print(f"[FACT-BATCH] No statistical claims from Tier 3-4/unknown sources to verify")
        return {}

    # Limit to budget
    to_verify = candidates[:max_searches]
    skipped = len(candidates) - len(to_verify)

    if DEBUG_MODE:
        total_facts = len(facts)
        auto_trusted = total_facts - len(candidates)
        print(
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
    if DEBUG_MODE:
        statuses = Counter(v["status"] for v in verification_map.values())
        print(f"[FACT-BATCH] Results: {dict(statuses)}")

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
        if DEBUG_MODE:
            print(f"[GROUNDING] '{fact_text[:60]}...' -> grounded (exact_match)")
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
                if DEBUG_MODE:
                    print(f"[GROUNDING] '{fact_text[:60]}...' -> grounded (number_anchor: all {len(fact_numbers)} numbers within 300-char window)")
                return {"is_grounded": True, "grounding_method": "number_anchor", "confidence_multiplier": 1.0}
            else:
                if DEBUG_MODE:
                    print(f"[GROUNDING] '{fact_text[:60]}...' -> partial (all {len(fact_numbers)} numbers found but scattered, no 300-char window)")
                return {"is_grounded": True, "grounding_method": "partial_number", "confidence_multiplier": 0.6}
        elif matched_numbers == len(fact_numbers) and len(fact_numbers) == 1:
            # Single number — no proximity needed, but lower confidence
            if DEBUG_MODE:
                print(f"[GROUNDING] '{fact_text[:60]}...' -> grounded (number_anchor: single number found)")
            return {"is_grounded": True, "grounding_method": "number_anchor", "confidence_multiplier": 0.9}
        elif matched_numbers > 0:
            if DEBUG_MODE:
                print(f"[GROUNDING] '{fact_text[:60]}...' -> partial ({matched_numbers}/{len(fact_numbers)} numbers found)")
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
                if DEBUG_MODE:
                    print(f"[GROUNDING] '{fact_text[:60]}...' -> grounded (ngram_overlap: {overlap:.0%})")
                return {"is_grounded": True, "grounding_method": "ngram_overlap", "confidence_multiplier": 0.9}

    # Failed all three tiers — ungrounded
    if DEBUG_MODE:
        print(f"[GROUNDING] '{fact_text[:60]}...' -> UNGROUNDED (no match in source)")

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

        # Get surrounding context (200 chars before the citation)
        context_start = max(0, link_start - 300)
        context = article_text[context_start:link_start].strip()

        # Find the most recent sentence containing the citation
        sentences = re.split(r'(?<=[.!?])\s+', context)
        claim_text = sentences[-1] if sentences else context[-200:]

        # Check if claim contains quantitative data
        has_quant = bool(_QUANT_CLAIM_PATTERN.search(claim_text))

        claims.append({
            "claim_text": claim_text.strip(),
            "citation_url": url.strip(),
            "citation_anchor": anchor.strip(),
            "has_quantitative_claim": has_quant,
        })

    if DEBUG_MODE:
        quant_count = sum(1 for c in claims if c["has_quantitative_claim"])
        print(f"[CLAIM-EXTRACT] Found {len(claims)} cited claims ({quant_count} with quantitative data)")

    return claims


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

        # NOTE: Bare domain-level matching intentionally removed (Gap 5 fix).
        if not matched_facts:
            fabricated_count += 1
            details.append({
                "claim_text": claim_text[:200],
                "status": "fabricated",
                "matched_fact": None,
                "source_url": claim_url,
                "reason": "No verified facts matched this URL (checked: exact, normalized, path-prefix)",
            })
            if DEBUG_MODE:
                print(f"[CLAIM-XREF] FABRICATED: '{claim_text[:60]}...' cites {claim_url} (no URL match)")
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
                if DEBUG_MODE:
                    print(f"[CLAIM-XREF] Claim '{claim_text[:50]}...' matched FactCitation #{fc.id} via number_anchor")
                break

        if not matched:
            # No number match — try text similarity
            for fc in matched_facts:
                # Simple word overlap check
                claim_words = set(re.findall(r'\w{4,}', claim_text.lower()))
                fact_words = set(re.findall(r'\w{4,}', fc.fact_text.lower()))
                if claim_words and fact_words:
                    overlap = len(claim_words & fact_words) / min(len(claim_words), len(fact_words))
                    if overlap >= 0.3:
                        verified_count += 1
                        details.append({
                            "claim_text": claim_text[:200],
                            "status": "verified",
                            "matched_fact": fc.fact_text[:200],
                            "source_url": claim_url,
                            "reason": f"Text similarity ({overlap:.0%} word overlap)",
                        })
                        matched = True
                        if DEBUG_MODE:
                            print(f"[CLAIM-XREF] Claim '{claim_text[:50]}...' matched via text_similarity ({overlap:.0%})")
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
        details.append({
            "claim_text": amb["claim"]["claim_text"][:200],
            "status": "ambiguous",
            "matched_fact": None,
            "source_url": amb["claim"]["citation_url"],
            "reason": "Source in map but no clear fact match (needs LLM verification)",
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

    if DEBUG_MODE:
        status = "PASSED" if passed else "FAILED"
        print(
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
            context = f"\nSOURCE CONTEXT (snippet):\n{source_snippet[:1000]}\n"

        prompt = f"""Does this article claim match any of the verified facts from the same source?

ARTICLE CLAIM: "{claim_text}"

VERIFIED FACTS FROM SOURCE:
{fact_list}
{context}
Return JSON:
{{
  "supported": true/false,
  "matched_fact_index": 1,
  "reasoning": "Brief explanation"
}}

'supported' = true if the claim is a reasonable paraphrase or use of any verified fact.
Only return JSON."""

        headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": "deepseek-chat",
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

        if DEBUG_MODE:
            status = "supported" if supported else "unsupported"
            print(f"[CLAIM-LLM] Ambiguous claim -> {status}: {result.get('reasoning', '')[:80]}")

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
    """
    lines = []

    fabricated = [d for d in verification_result["details"] if d["status"] == "fabricated"]
    ambiguous = [d for d in verification_result["details"] if d["status"] == "ambiguous"]

    if fabricated:
        lines.append("FABRICATED CITATIONS (must fix):")
        for i, d in enumerate(fabricated, 1):
            lines.append(f"  {i}. \"{d['claim_text'][:120]}...\"")
            lines.append(f"     Cites: {d['source_url']}")
            lines.append(f"     Problem: {d['reason']}")
            lines.append(f"     Fix: Remove this claim or replace with a fact from the citation map.")
        lines.append("")

    if ambiguous:
        lines.append("AMBIGUOUS CITATIONS (should verify):")
        for i, d in enumerate(ambiguous, 1):
            lines.append(f"  {i}. \"{d['claim_text'][:120]}...\"")
            lines.append(f"     Cites: {d['source_url']}")
            lines.append(f"     Problem: {d['reason']}")
            lines.append(f"     Fix: Ensure the cited source actually states this specific claim.")
        lines.append("")

    # Summary
    total = verification_result["total_claims"]
    verified = verification_result["verified"]
    fab = verification_result["fabricated"]
    amb = verification_result.get("ambiguous", 0)

    lines.append(f"CLAIM VERIFICATION: {verified}/{total} verified, {fab} fabricated, {amb} ambiguous")

    if fab > 0:
        lines.append("STATUS: FAILED - Remove or fix all fabricated citations before retry.")
    else:
        lines.append("STATUS: PASSED")

    return "\n".join(lines)
