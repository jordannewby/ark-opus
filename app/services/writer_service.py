import json
import logging
import re
from pathlib import Path
from anthropic import AsyncAnthropic
from ..settings import ANTHROPIC_API_KEY, MAX_WRITER_ATTEMPTS, WRITER_MAX_TOKENS, LLM_SOURCE_CONTEXT_CHARS, MAX_UNCITED_CLAIMS
from .readability_service import verify_readability, READABILITY_DIRECTIVE

logger = logging.getLogger(__name__)


class WriterService:
    """Uses Anthropic Claude 4 Sonnet to enforce strict anti-AI prose logic & deep comprehensiveness."""

    def __init__(self, db):
        self.db = db
        if not ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY environment variable is not set.")

        self.client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        self.model_name = "claude-sonnet-4-20250514"

        # Load the strict writer system prompt
        prompt_path = Path(__file__).parent / "prompts" / "writer.md"
        with open(prompt_path, "r", encoding="utf-8") as f:
            self.base_system_prompt = f.read()

    # Deterministic banned-word replacements (LLM prompt enforcement is unreliable)
    # Must include all inflected forms since SEO gate uses substring matching
    _BANNED_REPLACEMENTS = {
        # delve
        "delving": "exploring", "delved": "explored", "delves": "explores", "delve": "explore",
        # tapestry
        "tapestries": "mixes", "tapestry": "mix",
        # landscape
        "landscapes": "spaces", "landscape": "space",
        # multifaceted
        "multifaceted": "complex",
        # comprehensive
        "comprehensively": "thoroughly", "comprehensive": "thorough",
        # holistic
        "holistically": "completely", "holistic": "complete",
        # navigate
        "navigating": "moving through", "navigated": "moved through", "navigates": "moves through", "navigate": "move through",
        # crucial
        "crucially": "critically", "crucial": "critical",
        # robust
        "robustly": "strongly", "robustness": "strength", "robust": "strong",
        # seamless
        "seamlessly": "smoothly", "seamless": "smooth",
        # synergy
        "synergies": "collaborations", "synergy": "collaboration",
        # leverage (must come before base to avoid partial matches)
        "leveraging": "using", "leveraged": "used", "leverages": "uses", "leverage": "use",
        # scalable
        "scalability": "growth capacity", "scalable": "growable",
        # foster
        "fostering": "encouraging", "fostered": "encouraged", "fosters": "encourages", "foster": "encourage",
        # optimize
        "optimization": "improvement", "optimizing": "improving", "optimized": "improved", "optimizes": "improves", "optimize": "improve",
        # ecosystem
        "ecosystems": "environments", "ecosystem": "environment",
        # paradigm
        "paradigms": "models", "paradigm": "model",
    }

    def _sanitize_banned_words(self, text: str) -> str:
        """Replace banned words and their inflections with safe alternatives, preserving case."""
        for banned, replacement in self._BANNED_REPLACEMENTS.items():
            pattern = re.compile(r'\b' + re.escape(banned) + r'\b', re.IGNORECASE)
            def _match_case(match, repl=replacement):
                word = match.group()
                if word[0].isupper():
                    return repl[0].upper() + repl[1:]
                return repl
            text = pattern.sub(_match_case, text)
        return text

    async def produce_article(self, blueprint: dict, profile_name: str = "default", niche: str = "general", research_run_id: int | None = None, source_content_map: dict | None = None):
        """
        Takes a blueprint JSON and streams a formatted Markdown article using Anthropic.
        Enforces Information Gain, E-E-A-T, and Entity Density rules with an iterative SEO loop.
        Includes citation map from verified sources if research_run_id provided.
        """
        import json # Explicitly import to prevent shadowing by local assignments later in the function
        entities = blueprint.get("entities", [])
        semantic_keywords = blueprint.get("semantic_keywords", [])
        information_gap = blueprint.get("information_gap", "")

        # 1. Build Base Prompts
        system_instructions = self.base_system_prompt + (
            "\n\nMINIMUM 1,500 words (non-negotiable). Target 1,500-1,800 words for optimal SEO ranking and engagement. "
            "Articles under 1,500 words WILL be rejected and you WILL have to rewrite. "
            "Be highly comprehensive, but eliminate all rambling and fluff. Conclude naturally once the Information Gap is fully addressed."
        )

        prompt_instructions = (
            "Write a 1,500-1,800 word blog post (HARD MINIMUM: 1,500 words) based on the following psychological blueprint:\n\n"
            f"{json.dumps(blueprint, indent=2)}\n\n"
            "MANDATORY:\n"
            "- Deliver the 'Information Gap' hook in the first 150 words.\n"
            "- Cite 'Authority Sources' using the Phase 1 Backlinks insight if applicable.\n"
        )

        if entities:
            prompt_instructions += f"## SEO Entities to Weave Naturally:\n{', '.join(entities)}\n\n"

        if semantic_keywords:
            prompt_instructions += f"## Semantic Keywords to Include:\n{', '.join(semantic_keywords)}\n\n"

        prompt_instructions += (
            "CRITICAL WRITING CONSTRAINTS (Read Carefully):\n"
            "1. NO AI FLUFF: Do NOT use ANY of these words: "
            "'delve', 'tapestry', 'landscape', 'multifaceted', 'comprehensive', 'holistic', "
            "'navigate', 'crucial', 'robust', 'seamless', 'synergy', 'leverage', 'scalable', "
            "'foster', 'optimize', 'ecosystem', 'paradigm'. Using ANY of these words will cause "
            "an automatic validation failure and forced rewrite.\n"
            "2. NO CLICHES: Do NOT use 'In conclusion', 'Ultimately', 'In today's digital age', or 'game-changer'.\n"
            "3. FORMATTING: The very first ## H2 MUST focus entirely on the 'Information Gap' as a pattern interrupt.\n"
            "4. CADENCE: Max 2-3 sentences per paragraph. Short, punchy delivery. White space between every paragraph.\n"
            "5. NO FAKE ASSETS: Do NOT reference specific templates, tools, downloads, checklists, frameworks, or products that do not actually exist. Do NOT promise deliverables the reader cannot access. Do NOT name fake templates like 'QuickBooks Integration Template' or 'Security Audit Checklist'. Instead, give actionable steps the reader can follow directly in the article.\n"
            "6. NO FABRICATED DATA: Do NOT invent statistics, percentages, dollar amounts, study results, or benchmarks. Use ONLY facts and numbers that appear in the research brief provided above. If the research brief does not contain a specific stat, do NOT make one up. Say 'studies show' or 'research suggests' ONLY if the research brief contains the actual source. It is better to make a strong argument without numbers than to fabricate a stat that destroys reader trust.\n"
        )

        # Inject Dynamic Human Style Rules
        from ..models import UserStyleRule
        style_rules = self.db.query(UserStyleRule).filter(UserStyleRule.profile_name == profile_name).all()
        if style_rules:
            prompt_instructions += "\n--- HUMAN STYLE GUIDELINES LEARNED FROM PAST EDITS ---\n"
            for rule in style_rules:
                prompt_instructions += f"- {rule.rule_description}\n"
            prompt_instructions += "--------------------------------------------------------\n"

        # Inject WriterPlaybook (Readability Learning)
        from ..models import WriterPlaybook

        normalized_niche = niche.strip().lower().replace(" ", "-") if niche else "general"
        writer_playbook = self.db.query(WriterPlaybook).filter(
            WriterPlaybook.profile_name == profile_name,
            WriterPlaybook.niche == normalized_niche
        ).first()

        if writer_playbook:
            playbook_data = json.loads(writer_playbook.playbook_json)
            prompt_instructions += "\n--- READABILITY PLAYBOOK (LEARNED FROM PAST SUCCESSES) ---\n"
            prompt_instructions += f"This niche typically achieves ARI: {playbook_data['avg_ari_baseline']} grade level.\n"
            prompt_instructions += f"Target sentence length: {playbook_data['structure_template']['target_avg_sentence_length']} words.\n"

            if playbook_data.get('effective_sentence_patterns'):
                prompt_instructions += "\nEffective sentence patterns for this niche:\n"
                for pattern in playbook_data['effective_sentence_patterns'][:3]:  # Top 3
                    prompt_instructions += f"- {pattern['pattern']} (avg ARI: {pattern['avg_ari']})\n"

            if playbook_data.get('preferred_word_swaps'):
                prompt_instructions += "\nPreferred word simplifications:\n"
                for complex_word, simple_words in list(playbook_data['preferred_word_swaps'].items())[:5]:
                    prompt_instructions += f"- Instead of '{complex_word}', use: {', '.join(simple_words)}\n"

            prompt_instructions += f"(Playbook version {playbook_data['version']}, based on {playbook_data['runs_distilled']} successful articles)\n"
            prompt_instructions += "----------------------------------------------------------------\n"

        # Inject Content Patterns from DataForSEO (Optional)
        content_patterns = blueprint.get("content_patterns")
        if content_patterns:
            prompt_instructions += "\n--- SERP CONTENT PATTERNS (TOP 10 RESULTS ANALYSIS) ---\n"
            prompt_instructions += f"The top-ranking articles for this keyword typically have:\n"

            if content_patterns.get("avg_word_count"):
                word_count = content_patterns["avg_word_count"]
                prompt_instructions += f"- Average word count: {word_count:,} words (aim for similar depth)\n"

            if content_patterns.get("avg_heading_count"):
                h_counts = content_patterns["avg_heading_count"]
                if isinstance(h_counts, dict):
                    h2_count = h_counts.get("h2", 0)
                    h3_count = h_counts.get("h3", 0)
                    if h2_count > 0:
                        prompt_instructions += f"- Average H2 headings: {h2_count} (structure your article similarly)\n"
                    if h3_count > 0:
                        prompt_instructions += f"- Average H3 headings: {h3_count} (add sub-sections as needed)\n"

            if content_patterns.get("avg_list_count") and content_patterns["avg_list_count"] > 0:
                list_count = content_patterns["avg_list_count"]
                prompt_instructions += f"- Average lists: {list_count} (readers expect bulleted/numbered lists)\n"

            if content_patterns.get("avg_table_count") and content_patterns["avg_table_count"] > 0:
                table_count = content_patterns["avg_table_count"]
                prompt_instructions += f"- Average tables: {table_count} (consider comparison tables if relevant)\n"

            if content_patterns.get("content_types"):
                types = content_patterns["content_types"]
                if types:
                    prompt_instructions += f"- Common content types: {', '.join(types[:3])} (match reader expectations)\n"

            if content_patterns.get("top_topics"):
                topics = content_patterns["top_topics"]
                if topics:
                    prompt_instructions += f"- Top related topics: {', '.join(topics[:5])}\n"

            prompt_instructions += "\nUse these patterns as a guide for structure, not as strict requirements.\n"
            prompt_instructions += "Your article should match the depth and format readers expect from top results.\n"
            prompt_instructions += "------------------------------------------------------------\n"

        # Inject Citation Map from Verified Sources
        if research_run_id:
            from ..models import FactCitation

            citations = self.db.query(FactCitation).filter_by(research_run_id=research_run_id).all()

            if citations:
                # Filter out unverified facts and apply usability-tier weighting
                verified_citations = [c for c in citations if getattr(c, 'is_verified', True)]

                def _usability_weight(c):
                    status = getattr(c, 'verification_status', 'not_checked') or 'not_checked'
                    if status in ("corroborated", "trusted"):
                        tier_mult = 1.5   # Premium: verified facts
                    elif status == "not_checked":
                        tier_mult = 0.6   # Discount: unchecked facts
                    elif status == "suspect":
                        tier_mult = 0.4   # Heavy discount: suspect source
                    else:
                        tier_mult = 0.5
                    grounding_mult = 1.2 if getattr(c, 'is_grounded', True) else 0.8
                    return (c.composite_score or 0) * tier_mult * grounding_mult

                citations_sorted = sorted(verified_citations, key=_usability_weight, reverse=True)

                prompt_instructions += "\n╔════════════════════════════════════════════════════════════════╗\n"
                prompt_instructions += "║   CRITICAL CITATION REQUIREMENTS (NON-NEGOTIABLE)             ║\n"
                prompt_instructions += "╚════════════════════════════════════════════════════════════════╝\n\n"

                prompt_instructions += f"[!] You have access to {len(citations_sorted)} VERIFIED factual claims below.\n"
                prompt_instructions += "[!] You MUST cite sources when making ANY factual claim.\n\n"

                prompt_instructions += "═══ AVAILABLE CITATIONS (use exact markdown format) ═══\n\n"

                for cite in citations_sorted:
                    markdown_link = f"[{cite.citation_anchor}]({cite.source_url})"
                    # Truncate fact to 100 chars for readability
                    fact_preview = cite.fact_text
                    prompt_instructions += f"  • {markdown_link} — {fact_preview}\n"

                prompt_instructions += "\n═══════════════════════════════════════════════════\n\n"

                prompt_instructions += "MANDATORY FORMAT:\n"
                prompt_instructions += "   When you write a fact from the map, cite it IMMEDIATELY like this:\n"
                prompt_instructions += '   "67% of SMBs experienced a cyberattack in 2023 [Verizon 2024](https://verizon.com/dbir)."\n\n'

                prompt_instructions += "MINIMUM CITATION REQUIREMENTS:\n"
                prompt_instructions += "   • If your article has 0-2 quantitative claims: Cite at least 3 sources\n"
                prompt_instructions += "   • If your article has 3+ quantitative claims: Cite 1 source per claim\n"
                prompt_instructions += "   • Distribute citations throughout the article (not all in one section)\n\n"

                prompt_instructions += "STRICT PROHIBITIONS:\n"
                prompt_instructions += "   • DO NOT invent statistics, percentages, or dollar amounts\n"
                prompt_instructions += "   • DO NOT use vague claims like 'many companies' or 'recent studies'\n"
                prompt_instructions += "   • DO NOT cite sources not in the citation map above\n"
                prompt_instructions += "   • DO NOT write facts without immediate inline citations\n\n"

                prompt_instructions += "ACCEPTED CITATION FORMATS:\n"
                prompt_instructions += "   1. Markdown links: [Source Name 2024](URL)  ← PREFERRED\n"
                prompt_instructions += "   2. Parenthetical: (Source 2024)\n"
                prompt_instructions += "   3. Footnotes: [1], [2], etc.\n\n"

                prompt_instructions += "EXAMPLES OF PROPER CITATION:\n"
                prompt_instructions += "   [OK] 'According to [Gartner 2024](url), cloud adoption will reach 85% by 2026.'\n"
                prompt_instructions += "   [OK] 'The average cost of a data breach is $4.35 million [IBM Report](url).'\n"
                prompt_instructions += "   [OK] 'Healthcare faces 3x more attacks than other sectors (Verizon 2024).'\n"
                prompt_instructions += "   [X] '67% of SMBs report security concerns.' -- NO CITATION!\n"
                prompt_instructions += "   [X] 'Many companies are adopting AI.' -- VAGUE, NO DATA!\n\n"

                prompt_instructions += "================================================\n"

                # Layer 3A: Topical mismatch warning
                # If few citations actually match the keyword topic, warn writer to cite sparingly
                kw_for_check = blueprint.get("keyword", "")
                kw_tokens = set(kw_for_check.lower().replace("-", " ").split())
                kw_tokens = {t for t in kw_tokens if len(t) >= 3}
                if kw_tokens:
                    on_topic_cites = 0
                    for cite in citations_sorted:
                        fact_lower = (cite.fact_text or "").lower()
                        if sum(1 for t in kw_tokens if t in fact_lower) >= max(1, min(2, len(kw_tokens))):
                            on_topic_cites += 1

                    if on_topic_cites < 3:
                        prompt_instructions += "\n*** TOPICAL MISMATCH WARNING ***\n"
                        prompt_instructions += f"Only {on_topic_cites} of {len(citations_sorted)} available citations directly match the article topic.\n"
                        prompt_instructions += "ADJUSTED CITATION RULES:\n"
                        prompt_instructions += "  - Only cite facts that genuinely support your claims. Do NOT force-cite off-topic sources.\n"
                        prompt_instructions += "  - Prefer 2-3 well-matched citations over 8 forced ones.\n"
                        prompt_instructions += "  - Write authoritative prose WITHOUT citations when no matching source exists.\n"
                        prompt_instructions += "  - It is acceptable to have sections with zero citations if the topic is not covered by available sources.\n"
                        prompt_instructions += "***********************************\n"

        # Pre-flight simplicity primer
        prompt_instructions += """

---
CRITICAL: 7TH-10TH GRADE READABILITY REQUIREMENT (ARI ≤10.0)
---
This article will be scored for readability (ARI ≤10.0).
If you fail this gate, you will be asked to rewrite up to 5 times.
After 5 failures, the article is published as-is with a quality penalty.

MANDATORY GATES YOU WILL BE TESTED AGAINST:
1. ARI score ≤10.0 (Automated Readability Index)
2. 80% of sentences MUST be 8-12 words (this is NOT a suggestion)
3. Max 15% of sentences can exceed 15 words
4. Average sentence length ≤12 words

PRE-FLIGHT CHECKLIST (review BEFORE writing each sentence):
1. Is this sentence 8-12 words? (Count as you write: "one, two, three...")
2. Did I use a word from the "short alternatives" list below?
3. Can I split this sentence at a comma into two shorter sentences?
4. Am I explaining technical terms in simple language in the next sentence?
5. Did I avoid business jargon (streamline, leverage, optimize, framework)?

Write your first draft as if explaining to a busy small business owner who:
- Skims headings and first sentences only
- Skips complex jargon they don't understand
- Values clear, actionable advice over impressive vocabulary
- Has zero patience for filler or academic language

THINK SIMPLE FROM THE START. Rewriting wastes tokens and time.
"""

        prompt_instructions += f"\n\n{READABILITY_DIRECTIVE}"
        prompt_instructions += "\nFollow all system prompt guidelines strictly. Write directly in Markdown."

        max_attempts = MAX_WRITER_ATTEMPTS
        v_feedback = ""
        all_feedback_history = []  # Gap 31: Accumulate feedback across iterations to prevent ping-pong
        last_readability_scores = None  # Track for max-attempts fallback

        # Gap 12 fix: Track best attempt across retries.
        # On max-attempts or early-exit, return the best-scoring attempt, not the last.
        best_attempt = None  # {"content": str, "readability": dict, "seo_passed": bool, "claims_passed": bool, "score": float}

        for attempt in range(1, max_attempts + 1):
            yield {"type": "debug", "message": f"Writer Iteration {attempt}: Starting draft generation..."}
            
            current_prompt = prompt_instructions
            if v_feedback:
                # Gap 31: Include accumulated feedback history (last 3 entries) so writer
                # sees ALL constraints simultaneously, preventing ping-pong loops
                feedback_block = ""
                if len(all_feedback_history) > 1:
                    # Show prior unresolved feedback so writer doesn't regress
                    prior = all_feedback_history[-3:-1] if len(all_feedback_history) > 2 else all_feedback_history[:-1]
                    feedback_block += "PRIOR UNRESOLVED ISSUES (do NOT regress on these):\n"
                    for i, fb in enumerate(prior, 1):
                        feedback_block += f"--- Issue {i} ---\n{fb}\n"
                    feedback_block += "\nLATEST FEEDBACK:\n"
                feedback_block += v_feedback
                current_prompt += (
                    f"\n\nCRITICAL FEEDBACK FROM PREVIOUS ATTEMPTS (MUST FIX ALL ISSUES SIMULTANEOUSLY):\n{feedback_block}\n"
                    "IMPORTANT: Fix ALL issues at once. Do NOT fix one issue while breaking another. "
                    "Replace each banned word with a specific alternative. "
                    "For example: 'landscape' -> 'space' or 'market', 'optimize' -> 'improve' or 'refine', "
                    "'robust' -> 'strong' or 'reliable', 'seamless' -> 'smooth' or 'easy', "
                    "'scalable' -> 'growable' or 'expandable'. "
                    "Maintain word count (1500+ words) while fixing all other issues."
                )

            full_content = ""
            try:
                # Lower temperature on retries for tighter readability compliance
                retry_temperature = 0.7 if attempt <= 2 else 0.5

                async with self.client.messages.stream(
                    model=self.model_name,
                    max_tokens=WRITER_MAX_TOKENS,
                    system=system_instructions,
                    messages=[{"role": "user", "content": current_prompt}],
                    temperature=retry_temperature
                ) as stream:
                    async for text_delta in stream.text_stream:
                        full_content += text_delta
                        yield {"type": "content", "data": text_delta}

                # 1b. Deterministic banned-word sanitization (LLM often slips)
                full_content = self._sanitize_banned_words(full_content)

                # 2. Perform SEO Validation
                yield {"type": "debug", "message": f"Writer Iteration {attempt}: Validating draft quality..."}
                score = self.verify_seo_score(full_content, information_gap)

                # Gap 12: Score this attempt for best-of-N tracking
                # Higher = better. SEO pass is worth 50pts, each sub-check adds points.
                attempt_score = 0.0
                if score["word_count_ok"]:
                    attempt_score += 10
                if score["h1_ok"]:
                    attempt_score += 5
                if score["h2_ok"]:
                    attempt_score += 10
                if score["lists_tables_ok"]:
                    attempt_score += 5
                if score["info_gain_ok"]:
                    attempt_score += 10
                if not score["banned_words_used"]:
                    attempt_score += 10

                # Gap 12: Update best_attempt if this is the best so far
                if best_attempt is None or attempt_score > best_attempt["score"]:
                    best_attempt = {
                        "content": full_content,
                        "readability": last_readability_scores,
                        "score": attempt_score,
                        "attempt": attempt,
                    }

                if score["passed"]:
                    yield {"type": "debug", "message": f"Writer Iteration {attempt}: Passed SEO validation."}

                    # --- Gate 3: Claim Cross-Referencing (replaces domain-counting Gate 2) ---
                    # Gap 8 fix: Always verify citation URLs exist in FactCitation table,
                    # not just for quantitative articles. Qualitative articles with fabricated
                    # citation links were passing unchecked.
                    if research_run_id:
                        try:
                            from .claim_verification_agent import (
                                extract_article_claims,
                                cross_reference_claims,
                                verify_claim_with_llm,
                                format_claim_verification_feedback,
                                detect_uncited_claims,
                            )

                            # Step 1: Always extract claim+citation pairs from article
                            article_claims = extract_article_claims(full_content)

                            if article_claims:
                                # Step 2: Cross-reference against verified FactCitations
                                fact_citations = self.db.query(FactCitation).filter_by(research_run_id=research_run_id).all()
                                # Only use verified facts for cross-referencing
                                verified_facts = [fc for fc in fact_citations if getattr(fc, 'is_verified', True)]

                                xref_result = cross_reference_claims(
                                    article_claims=article_claims,
                                    fact_citations=verified_facts,
                                    source_content_map=source_content_map,
                                )

                                # Step 2B: Detect uncited factual claims
                                uncited_claims = detect_uncited_claims(full_content, article_claims)
                                if uncited_claims:
                                    xref_result["uncited"] = uncited_claims
                                    xref_result["uncited_count"] = len(uncited_claims)

                                # Step 3: Resolve ambiguous claims with LLM
                                # Raised cap to 10 to handle articles with many citations
                                llm_calls = 0
                                for amb in xref_result.get("ambiguous_claims", [])[:10]:
                                    llm_result = await verify_claim_with_llm(
                                        claim_text=amb["claim"]["claim_text"],
                                        fact_candidates=amb["candidate_facts"],
                                        source_snippet=(source_content_map or {}).get(amb["claim"]["citation_url"], "")[:LLM_SOURCE_CONTEXT_CHARS] if source_content_map else None,
                                    )
                                    llm_calls += 1
                                    # Update detail status based on LLM result
                                    for detail in xref_result["details"]:
                                        if detail["claim_text"] == amb["claim"]["claim_text"][:200] and detail["status"] == "ambiguous":
                                            if llm_result["supported"]:
                                                detail["status"] = "verified"
                                                xref_result["verified"] += 1
                                            else:
                                                # Gap 33: Use "ungrounded" not "fabricated" — URL exists but claim doesn't match
                                                detail["status"] = "ungrounded"
                                                detail["reason"] = "URL exists in citation map but LLM confirms claim is not supported by source facts"
                                                # Preserve candidate_facts for feedback
                                                detail["candidate_facts"] = detail.get("candidate_facts", [])
                                                xref_result["ungrounded"] = xref_result.get("ungrounded", 0) + 1
                                            xref_result["ambiguous"] -= 1
                                            break

                                # Recalculate pass after LLM resolution
                                remaining_ambiguous = xref_result.get("ambiguous", 0)
                                ungrounded_count = xref_result.get("ungrounded", 0)
                                total_claims = xref_result.get("total_claims", 1)
                                # Allow up to 25% of claims to remain ambiguous (min 3)
                                # Ambiguous means "source exists but match unclear" — not fabricated
                                max_ambiguous = max(3, int(total_claims * 0.25))

                                # Layer 2A: Assess topical coverage of FactCitations
                                # When sources are off-topic (niche filter returned irrelevant results),
                                # allow a small number of ungrounded claims instead of zero-tolerance
                                kw_raw = blueprint.get("keyword", "")
                                kw_toks = set(kw_raw.lower().replace("-", " ").split())
                                kw_toks = {t for t in kw_toks if len(t) >= 3}
                                on_topic_facts = 0
                                if kw_toks:
                                    for fc in verified_facts:
                                        ft = (getattr(fc, 'fact_text', '') or '').lower()
                                        if sum(1 for t in kw_toks if t in ft) >= max(1, min(2, len(kw_toks))):
                                            on_topic_facts += 1

                                low_topical_coverage = (len(kw_toks) > 0 and on_topic_facts < 3)

                                # Layer 2B: Soften ungrounded tolerance for low-coverage scenarios
                                if low_topical_coverage:
                                    max_ungrounded = max(2, int(total_claims * 0.15))
                                    yield {"type": "debug", "message": f"Low topical coverage ({on_topic_facts} on-topic facts). Allowing up to {max_ungrounded} ungrounded claims."}
                                else:
                                    max_ungrounded = 0  # Normal: zero-tolerance for ungrounded

                                uncited_count = xref_result.get("uncited_count", 0)

                                xref_result["passed"] = (
                                    xref_result["fabricated"] == 0
                                    and ungrounded_count <= max_ungrounded
                                    and remaining_ambiguous <= max_ambiguous
                                    and uncited_count <= MAX_UNCITED_CLAIMS
                                )

                                if not xref_result["passed"]:
                                    v_feedback = format_claim_verification_feedback(xref_result)
                                    all_feedback_history.append(v_feedback)  # Gap 31
                                    if remaining_ambiguous > max_ambiguous:
                                        v_feedback += f"\n\nADDITIONAL: {remaining_ambiguous} claims remain ambiguous after LLM verification (max allowed: {max_ambiguous}). Too many unresolvable claims indicate unreliable sourcing. Rewrite using only facts from the citation map."
                                    yield {"type": "debug", "message": f"Claim Verification Failed (Iteration {attempt}):\n{v_feedback}"}

                                    if attempt == max_attempts:
                                        yield {"type": "debug", "message": "Max attempts reached. Returning best effort draft."}
                                        best_c = best_attempt["content"] if best_attempt else full_content
                                        best_r = best_attempt.get("readability") if best_attempt else last_readability_scores
                                        yield {"status": "success", "text": best_c, "readability_score": best_r, "quality_flag": "best_effort"}
                                        return

                                    # Clear editor for next attempt
                                    yield {"type": "control", "action": "retry_clear"}
                                    continue

                                yield {"type": "debug", "message": f"Writer Iteration {attempt}: Passed claim verification ({xref_result['verified']}/{xref_result['total_claims']} claims verified, {llm_calls} LLM calls, {remaining_ambiguous} ambiguous, {ungrounded_count} ungrounded, {uncited_count} uncited)."}
                            else:
                                yield {"type": "debug", "message": f"Writer Iteration {attempt}: No cited claims extracted (no markdown links found)."}

                        except Exception as e:
                            # Fallback to domain-counting v2 if claim verification fails
                            logger.error(f"[CLAIM-GATE] Claim verification failed, falling back to v2: {e}")
                            # Clear dirty session state so fallback queries don't fail too
                            try:
                                self.db.rollback()
                            except Exception:
                                pass

                            citations_fb = self.db.query(FactCitation).filter_by(research_run_id=research_run_id).all()
                            from .source_verification_service import extract_domain
                            available_domains = len(set(
                                extract_domain(c.source_url) for c in citations_fb
                                if c.source_url and extract_domain(c.source_url)
                            ))
                            min_required = min(3, max(available_domains, 3))

                            citation_result = self.verify_citation_requirements_v2(
                                full_content, citation_map=citations_fb, min_citations=min_required
                            )
                            if not citation_result["passed"]:
                                v_feedback = f"Citation Validation Failed (fallback v2, Iteration {attempt}). {citation_result['feedback']}"
                                yield {"type": "debug", "message": v_feedback}
                                if attempt == max_attempts:
                                    yield {"type": "debug", "message": "Max attempts reached. Returning best effort draft."}
                                    best_c = best_attempt["content"] if best_attempt else full_content
                                    best_r = best_attempt.get("readability") if best_attempt else last_readability_scores
                                    yield {"status": "success", "text": best_c, "readability_score": best_r, "quality_flag": "best_effort"}
                                    return
                                yield {"type": "control", "action": "retry_clear"}
                                continue
                            yield {"type": "debug", "message": f"Writer Iteration {attempt}: Passed citation validation (fallback v2)."}

                    # --- Gate 2: Readability Validation ---
                    # Build broad keyword list for readability masking
                    # Includes semantic keywords + entities from research blueprint
                    read_keywords = list(semantic_keywords) if semantic_keywords else []
                    if entities:
                        read_keywords.extend(entities)
                    # Add common technical terms that are unavoidable in this niche
                    # These inflate ARI but are NOT simplifiable — they're the subject matter
                    NICHE_TERMS = [
                        "security", "business", "software", "customer", "customers",
                        "company", "companies", "technology", "platform", "digital",
                        "strategy", "analysis", "employee", "employees", "solution",
                        "solutions", "management", "operations", "performance",
                        "enterprise", "interface", "revenue", "compliance",
                        "automated", "automation", "intelligence", "artificial",
                        "monitoring", "detection", "protection", "vulnerable",
                        "organization", "organizations", "productivity",

                        # B2B / SMB Specific additions
                        "investment", "financial", "development", "marketing", "owner",
                        "owners", "industry", "industries", "professional", "professionals",
                        "experience", "experiences", "competitive", "competition",

                        # Common business jargon that inflates ARI unfairly
                        "streamline", "streamlined", "streamlining",
                        "enhance", "enhanced", "enhancement",
                        "framework", "frameworks",
                        "methodology", "methodologies",
                        "establish", "established", "establishing",
                        "execute", "executed", "executing", "execution",
                        "implement", "implemented", "implementing", "implementation",
                        "facilitate", "facilitated", "facilitating",
                        "infrastructure", "infrastructures",
                        "capability", "capabilities",
                        "operational",
                        "strategic",

                        # Cybersecurity / Bug Bounty terms
                        "vulnerability", "vulnerabilities", "vulnerable",
                        "exploitation", "exploiting", "exploited",
                        "authentication", "authorization", "authenticated",
                        "configuration", "misconfiguration", "configured",
                        "credential", "credentials",
                        "remediation", "mitigation", "mitigations",
                        "reconnaissance", "enumeration",
                        "penetration", "injection", "introspection",
                        "containerized", "containerization",
                        "encryption", "decryption", "encrypted",
                        "exfiltration", "exfiltrate",
                        "obfuscation", "obfuscated",
                        "adversarial", "adversary", "adversaries",
                        "endpoint", "endpoints",
                        "certificate", "certificates",
                        "permission", "permissions", "authorization",
                        "privilege", "privileges", "privileged", "escalation",
                        "malicious", "payload", "payloads",
                        "server-side", "client-side",
                        "environment", "environments",
                        "application", "applications",
                        "architecture", "architectural",
                        "verification", "validation",
                        "processing", "processor",
                        "parameter", "parameters",
                        "registration", "registered",
                        "transaction", "transactions",
                        "mechanism", "mechanisms",
                        "identifier", "identifiers",
                        "specification", "specifications",
                        "documentation", "documented",
                        "deployment", "deployments", "deployed",
                        "repository", "repositories",
                        "component", "components",
                        "integration", "integrations", "integrated",
                        "response", "responses",
                        "concurrent", "concurrency",
                        "synchronization", "asynchronous",
                        "directory", "directories",
                    ]
                    read_keywords.extend(NICHE_TERMS)
                    # Deduplicate while preserving order
                    read_keywords = list(dict.fromkeys(read_keywords))
                    read_result = verify_readability(full_content, target_grade=10.0, keywords=read_keywords)

                    # DEBUG: Validate keyword masking effectiveness
                    if read_keywords:
                        logger.debug(f"[READABILITY] Masking {len(read_keywords)} keywords: {read_keywords[:10]}...")
                        sample_text = full_content[:500]
                        from app.services.readability_service import mask_keywords, strip_markdown
                        sample_masked = mask_keywords(strip_markdown(sample_text), read_keywords)
                        logger.debug(f"[READABILITY] Original: {sample_text[:100]}")
                        logger.debug(f"[READABILITY] Masked: {sample_masked[:100]}")

                    if read_result["pass"]:
                        details = read_result["details"]
                        yield {
                            "type": "debug",
                            "message": (
                                f"Writer Iteration {attempt}: Readability PASS — "
                                f"Grade {details['composite_grade']} "
                                f"(ARI: {details['ari_grade']}, "
                                f"CLI: {details['coleman_liau_grade']}, "
                                f"FK: {details['flesch_kincaid_grade']})"
                            )
                        }

                        # Gap 14: Lightweight blueprint compliance check (soft gate — warn only)
                        outline = blueprint.get("outline_structure", [])
                        if outline:
                            article_h2s = [
                                line.strip().lstrip('#').strip().lower()
                                for line in full_content.split('\n')
                                if re.match(r'^## (?!#)', line)
                            ]
                            blueprint_headings = []
                            for item in outline:
                                if isinstance(item, dict):
                                    blueprint_headings.append((item.get("heading") or item.get("title") or "").lower())
                                elif isinstance(item, str):
                                    blueprint_headings.append(item.lower())

                            matched_h2s = 0
                            for bh in blueprint_headings:
                                bh_words = set(re.findall(r'[a-zA-Z]{4,}', bh))
                                if not bh_words:
                                    continue
                                for ah in article_h2s:
                                    ah_words = set(re.findall(r'[a-zA-Z]{4,}', ah))
                                    if len(bh_words & ah_words) >= 2:
                                        matched_h2s += 1
                                        break

                            if matched_h2s < min(3, len(blueprint_headings)):
                                yield {"type": "debug", "message": f"Blueprint compliance: {matched_h2s}/{len(blueprint_headings)} outline headings reflected in article H2s (soft warning)."}

                        # Gap 14: Hook strategy compliance check (soft gate — warn only)
                        hook_strategy = blueprint.get("hook_strategy", "")
                        if hook_strategy and len(hook_strategy) > 5:
                            hook_words = set(re.findall(r'[a-zA-Z]{4,}', hook_strategy.lower()))
                            if hook_words:
                                article_opening = full_content[:200].lower()
                                opening_words = set(re.findall(r'[a-zA-Z]{4,}', article_opening))
                                hook_overlap = hook_words & opening_words
                                if len(hook_overlap) < 1:
                                    yield {"type": "debug", "message": f"Blueprint compliance: Hook strategy not reflected in article opening (0/{len(hook_words)} hook words in first 200 chars). Hook: '{hook_strategy[:80]}' (soft warning)."}

                        # Include readability scores for database tracking
                        yield {
                            "status": "success",
                            "text": full_content,
                            "readability_score": {
                                "ari": details['ari_grade'],
                                "fk": details['flesch_kincaid_grade'],
                                "cli": details['coleman_liau_grade'],
                                "avg_sentence_length": details['avg_sentence_length']
                            }
                        }
                        return
                    else:
                        details = read_result["details"]
                        last_readability_scores = {
                            "ari": details['ari_grade'],
                            "fk": details['flesch_kincaid_grade'],
                            "cli": details['coleman_liau_grade'],
                            "avg_sentence_length": details['avg_sentence_length'],
                        }
                        v_feedback = (
                            f"Readability Validation Failed (Iteration {attempt}).\n"
                            f"{read_result['feedback']}"
                        )
                        all_feedback_history.append(v_feedback)  # Gap 31
                        yield {
                            "type": "debug",
                            "message": (
                                f"Writer Iteration {attempt}: Readability FAIL — "
                                f"Grade {details['composite_grade']} "
                                f"(ARI: {details['ari_grade']}, "
                                f"CLI: {details['coleman_liau_grade']}, "
                                f"FK: {details['flesch_kincaid_grade']}) "
                                f"| ARI Target: ≤10.0 "
                                f"| Avg sentence: {details['avg_sentence_length']} words "
                                f"| {details['complex_sentence_count']} complex sentences"
                            )
                        }

                        # Gap 12: Update best_attempt with readability scores
                        read_scores = {
                            "ari": details['ari_grade'],
                            "fk": details['flesch_kincaid_grade'],
                            "cli": details['coleman_liau_grade'],
                            "avg_sentence_length": details['avg_sentence_length'],
                        }
                        # Readability-failing attempts that passed SEO+claims score higher
                        read_attempt_score = attempt_score + 50  # +50 for passing SEO
                        if best_attempt is None or read_attempt_score > best_attempt["score"]:
                            best_attempt = {
                                "content": full_content,
                                "readability": read_scores,
                                "score": read_attempt_score,
                                "attempt": attempt,
                            }

                        # Early exit detection for unsimplifiable jargon (after 3rd attempt)
                        if attempt >= 3:
                            if self.detect_unsimplifiable_jargon(full_content, read_keywords):
                                yield {
                                    "type": "debug",
                                    "message": (
                                        "Technical jargon detected (>30% density). "
                                        "Content contains unavoidable domain-specific terms. "
                                        "Accepting current readability level to preserve accuracy."
                                    )
                                }
                                # Gap 12: Return best attempt, not current
                                best_c = best_attempt["content"] if best_attempt else full_content
                                best_r = best_attempt.get("readability", read_scores) if best_attempt else read_scores
                                best_r["early_exit"] = "unsimplifiable_jargon"
                                yield {
                                    "status": "success",
                                    "text": best_c,
                                    "readability_score": best_r,
                                    "quality_flag": "best_effort",
                                }
                                return

                        if attempt == max_attempts:
                            yield {"type": "debug", "message": "Max attempts reached. Returning best effort draft."}
                            best_c = best_attempt["content"] if best_attempt else full_content
                            best_r = best_attempt.get("readability") if best_attempt else last_readability_scores
                            yield {"status": "success", "text": best_c, "readability_score": best_r, "quality_flag": "best_effort"}
                            return

                        # Clear editor for next attempt
                        yield {"type": "control", "action": "retry_clear"}
                else:
                    issues = []
                    if score['banned_words_used']:
                        issues.append(f"Banned words found: {', '.join(score['banned_words_found'])}")
                    if not score['word_count_ok']:
                        shortfall = 1500 - score['word_count']
                        issues.append(f"Word count too low ({score['word_count']} words, need 1500+). Add ~{shortfall} more words: expand analysis sections, add practical examples, deeper explanations, or additional subsections. Do NOT add filler — add substantive content.")
                    if not score['h1_ok']:
                        issues.append(f"H1 heading issue (found {score['h1_count']}, need exactly 1). CRITICAL: Use '# ' (single hash) ONLY for the article title. Use '## ' (double hash) for ALL section headings. You have {score['h1_count']} lines starting with '# ' — convert all but the title to '## '")
                    if not score['h2_ok']:
                        issues.append(f"Not enough H2 headings (found {score['h2_count']}, need 5+). Add more '## Section Title' headings to break the article into 5+ distinct sections.")
                    if not score['lists_tables_ok']:
                        issues.append(f"Not enough list/table blocks (found {score['list_table_blocks']}, need 3+)")
                    if not score['info_gain_ok']:
                        issues.append(f"Information gain too low ({score['info_gain_density']} angles covered, need 2+). Address more angles from the information gap in your H2 sections.")
                    v_feedback = (
                        f"SEO Validation Failed (Iteration {attempt}).\n"
                        + ("Issues:\n- " + "\n- ".join(issues) if issues else "Unknown validation failure")
                    )
                    all_feedback_history.append(v_feedback)  # Gap 31
                    yield {"type": "debug", "message": f"Writer Iteration {attempt} failed: {v_feedback}"}
                    
                    if attempt == max_attempts:
                        yield {"type": "debug", "message": "Max attempts reached. Returning best effort draft."}
                        best_c = best_attempt["content"] if best_attempt else full_content
                        best_r = best_attempt.get("readability") if best_attempt else last_readability_scores
                        yield {"status": "success", "text": best_c, "readability_score": best_r, "quality_flag": "best_effort"}
                        return

                    # Clear editor for next attempt
                    yield {"type": "control", "action": "retry_clear"}

            except Exception as e:
                error_msg = f"Anthropic API Error: {str(e)}"
                logger.error(f"[Writer] {error_msg}")
                yield {"status": "error", "message": error_msg}
                return

    @staticmethod
    def verify_seo_score(text: str, information_gap: str = "") -> dict:
        """
        Validates generated article against basic SEO structure requirements and Information Gain Density.
        """
        # Strip fenced code blocks before counting headings/structure
        # Code comments (# comment) were being falsely counted as H1 headings
        text_no_code = re.sub(r'```[\s\S]*?```', '', text)
        lines = text_no_code.split("\n")
        word_count = len(text.split())  # Word count uses full text (code included)

        # H1 count: lines starting with exactly '# ' (not '##')
        h1_count = sum(1 for line in lines if re.match(r"^# (?!#)", line))

        # H2 count: lines starting with exactly '## ' (not '###')
        h2_count = sum(1 for line in lines if re.match(r"^## (?!#)", line))

        # Count distinct list/table blocks
        # Gap 30 fix: Allow 1 blank-line gap within a block + match table separator rows
        list_table_blocks = 0
        in_block = False
        blank_gap = 0  # Track consecutive blank lines within a block
        for line in lines:
            stripped = line.strip()
            is_list_or_table = bool(
                re.match(r"^[-*] ", stripped)
                or re.match(r"^\d+\. ", stripped)
                or re.match(r"^\|.+\|$", stripped)
                or re.match(r"^\|[-:| ]+\|$", stripped)  # Table separator rows
            )
            if is_list_or_table:
                if not in_block:
                    list_table_blocks += 1
                in_block = True
                blank_gap = 0
            elif not stripped:
                # Blank line — tolerate 1 blank gap within a block
                if in_block:
                    blank_gap += 1
                    if blank_gap > 1:
                        in_block = False
                        blank_gap = 0
            elif stripped:
                in_block = False
                blank_gap = 0

        # Information Gain Check
        # Gap 13 fix: Replaced keyword frequency with real information gain check.
        # Extracts distinct claims/angles from information_gap and verifies they
        # appear as H2 sections or cited facts in the article.
        info_gain_density = 0
        if information_gap:
            # Extract distinct angles: split on sentence boundaries and list markers
            raw_angles = re.split(r'[.;!\n•\-]', information_gap)
            angles = [a.strip() for a in raw_angles if len(a.strip()) > 20]

            if angles:
                text_lower = text.lower()
                # Extract H2 headings from article
                h2_headings = [line.strip().lstrip('#').strip().lower() for line in text_no_code.split('\n') if re.match(r'^## (?!#)', line)]

                matched_angles = 0
                for angle in angles:
                    angle_lower = angle.lower()
                    # Extract 3 most significant words (5+ chars) from this angle
                    angle_words = [w for w in re.findall(r'[a-zA-Z]{5,}', angle_lower)][:5]
                    if len(angle_words) < 2:
                        continue

                    # Check 1: Do 2+ angle words appear in any H2 heading?
                    h2_match = any(
                        sum(1 for w in angle_words if w in h2) >= 2
                        for h2 in h2_headings
                    )
                    # Check 2: Do 3+ angle words appear in the article body?
                    body_match = sum(1 for w in angle_words if w in text_lower) >= 3

                    if h2_match or body_match:
                        matched_angles += 1

                # info_gain_density = matched angles (need at least 2)
                info_gain_density = matched_angles

            info_gain_ok = info_gain_density >= 2 if angles else True
        else:
            info_gain_ok = True
            logger.info("[SEO-CHECK] No information_gap provided -- info gain check bypassed")

        # Banned phrases check
        # Gap 11 fix: Merged prompt banned list (22 words) + AI slop phrases into gate.
        # Previously only 13 words were enforced; the rest were prompt-only (unenforced).
        banned_list = [
            # Original 13
            "delve", "tapestry", "landscape", "multifaceted", "comprehensive",
            "holistic", "navigate", "crucial", "in conclusion", "ultimately",
            "fast-paced world", "digital age", "game-changer",
            # 9 additional from readability directive (were prompt-only, never gate-enforced)
            "robust", "seamless", "synergy", "leverage", "scalable",
            "foster", "optimize", "ecosystem", "paradigm",
            # AI slop phrases
            "it's worth noting", "it's important to note", "it is worth noting",
            "whether you're a", "in the ever-evolving",
            "when it comes to", "at the end of the day", "let's face it",
            "in today's world", "in today's digital landscape",
            "it cannot be overstated", "needless to say",
        ]
        text_lower = text.lower()
        found_banned_words = [word for word in banned_list if word in text_lower]
        banned_words_used = len(found_banned_words) > 0

        passed = (
            word_count >= 1500
            and h1_count == 1
            and h2_count >= 5
            and list_table_blocks >= 3
            and info_gain_ok
            and not banned_words_used
        )

        return {
            "word_count": word_count,
            "word_count_ok": word_count >= 1500,
            "h1_count": h1_count,
            "h1_ok": h1_count == 1,
            "h2_count": h2_count,
            "h2_ok": h2_count >= 5,
            "list_table_blocks": list_table_blocks,
            "lists_tables_ok": list_table_blocks >= 3,
            "info_gain_density": info_gain_density,
            "info_gain_ok": info_gain_ok,
            "banned_words_used": banned_words_used,
            "banned_words_found": found_banned_words,
            "passed": passed,
        }

    @staticmethod
    def verify_citation_requirements(text: str, min_citations: int = 3) -> dict:
        """
        Validates that article includes minimum required inline citations.

        Enhanced validation (March 2026): Accepts multiple citation formats:
        - Markdown links: [text](url)
        - Parenthetical citations: (Source 2024)
        - Footnote markers: [1], [2], etc.

        Returns: {passed: bool, citation_count: int, feedback: str}
        """
        all_citations = []

        # Format 1: Markdown links [text](url) - PREFERRED
        markdown_pattern = r'\[([^\]]+)\]\(https?://[^\)]+\)'
        markdown_citations = re.findall(markdown_pattern, text)
        all_citations.extend(markdown_citations)

        # Format 2: Parenthetical citations (Author/Source YYYY)
        # Matches: (Source 2024), (Verizon 2024), (IBM Report 2024), (Cloud-Native 2025)
        # Enhanced to support numbers, hyphens, and periods in source names
        parenthetical_pattern = r'\([A-Z][a-zA-Z0-9\s&\-\.]+\s+20\d{2}\)'
        parenthetical_citations = re.findall(parenthetical_pattern, text)
        all_citations.extend(parenthetical_citations)

        # Format 3: Footnote markers [1], [2], etc.
        # Only count if there are actual numbered footnotes (not just markdown links)
        footnote_pattern = r'\[(\d+)\]'
        footnote_citations = re.findall(footnote_pattern, text)
        # Only count unique footnote numbers
        unique_footnotes = list(set(footnote_citations))
        all_citations.extend(unique_footnotes)

        # Count total unique citations across all formats
        citation_count = len(all_citations)

        # DEBUG: Log what was found
        logger.debug(f"[DEBUG] Citation validation: Found {citation_count} citations")
        logger.debug(f"  - Markdown: {len(markdown_citations)}")
        logger.debug(f"  - Parenthetical: {len(parenthetical_citations)}")
        logger.debug(f"  - Footnotes: {len(unique_footnotes)}")
        if citation_count > 0:
            logger.debug(f"  - Sample: {all_citations[:3]}")

        passed = citation_count >= min_citations

        feedback = ""
        if not passed:
            feedback = (
                f"Only {citation_count} citations found, need {min_citations} minimum. "
                f"Add more inline citations using one of these formats:\n"
                f"  - Markdown links: [Source Title](URL)\n"
                f"  - Parenthetical: (Source 2024)\n"
                f"  - Footnotes: [1], [2], etc.\n"
                f"Use the citation map provided in the prompt."
            )

        return {
            "passed": passed,
            "citation_count": citation_count,
            "feedback": feedback,
        }

    @staticmethod
    def extract_citation_domains(text: str) -> set[str]:
        """
        Extract all domains from inline citations (markdown links).

        Returns set of domains cited in the article.
        Used for domain-based citation validation (more flexible than exact text matching).
        """
        from .source_verification_service import extract_domain

        domains = set()

        # Markdown links: [text](https://domain.com/path)
        markdown_pattern = r'\[([^\]]+)\]\((https?://[^\)]+)\)'
        markdown_urls = re.findall(markdown_pattern, text)

        for _, url in markdown_urls:
            domain = extract_domain(url)
            if domain:
                domains.add(domain)

        return domains

    @staticmethod
    def verify_citation_requirements_v2(
        text: str,
        citation_map: list,
        min_citations: int = 3
    ) -> dict:
        """
        Domain-based citation validation (v2).

        More flexible than regex text matching - validates that article cites
        domains from the citation map, not exact anchor text.

        This fixes the common issue where DeepSeek extracts "Verizon 2024" but
        Claude writes "Verizon Report 2024" - both cite the same domain, so both valid.

        Args:
            text: Article markdown content
            citation_map: list of FactCitation objects with source_url
            min_citations: Minimum number of verified sources that must be cited

        Returns:
            {
                "passed": bool,
                "citation_count": int,  # How many map domains are cited
                "feedback": str
            }
        """
        from .source_verification_service import extract_domain

        # Extract all domains cited in article
        article_domains = WriterService.extract_citation_domains(text)

        # Extract all domains from citation map
        map_domains = set()
        for cite in citation_map:
            domain = extract_domain(cite.source_url)
            if domain:
                map_domains.add(domain)

        # Count how many map sources are cited (intersection)
        cited_count = len(article_domains & map_domains)

        passed = cited_count >= min_citations

        feedback = ""
        if not passed:
            missing = map_domains - article_domains
            feedback = (
                f"Only {cited_count}/{min_citations} verified sources cited.\n"
                f"You cited domains: {', '.join(sorted(article_domains)) if article_domains else 'NONE'}\n"
                f"Missing verified sources from these domains: {', '.join(sorted(list(missing)[:5]))}\n"
                f"Use the citation map provided in the prompt and cite these domains."
            )

        logger.debug(f"[CITATION-V2] Article domains: {article_domains}")
        logger.debug(f"[CITATION-V2] Map domains: {map_domains}")
        logger.debug(f"[CITATION-V2] Cited {cited_count}/{min_citations} required sources")

        return {
            "passed": passed,
            "citation_count": cited_count,
            "feedback": feedback,
        }

    @staticmethod
    def detect_quantitative_claims(text: str) -> dict:
        """
        Detect quantitative claims that require citations.

        Enhanced patterns (March 2026) to catch more claim types:
        - Percentages (67%, 85%)
        - Dollar amounts ($200K, $4.5M)
        - Numeric statistics (3 out of 4)
        - Benchmarks (average of 12, median 45 days)
        - Spelled-out fractions (half of companies, most enterprises)
        - Narrative claims (studies show, research indicates)
        - Comparative stats (twice as likely, 50% more effective)
        - Year-based statistics (In 2024, 500 organizations...)

        Returns:
            {
                'has_claims': bool,
                'claim_count': int,
                'claim_samples': list[str],
                'required_citations': int
            }
        """
        claims = []

        # Pattern 1: Percentages
        percentage_pattern = r'\b\d+\.?\d*\s*%'

        # Pattern 2: Dollar amounts
        dollar_pattern = r'\$\d+(?:,\d{3})*(?:\.\d+)?(?:\s*(?:million|billion|M|B|K|thousand))?'

        # Pattern 3: "X out of Y" statistics
        stat_pattern = r'\b\d+\.?\d*\s*(?:out of|in|times|x)\s*\d+'

        # Pattern 4: Benchmarks
        benchmark_pattern = r'\b(?:average|median|mean|typical(?:ly)?)\s+(?:of\s+)?\d+\.?\d*'

        # Pattern 5: Spelled-out fractional quantities (NEW)
        spelled_numbers_pattern = r'\b(?:half|quarter|third|two-thirds|majority|most|minority|few|several|many)\s+(?:of\s+)?(?:businesses|companies|organizations|enterprises|firms|users|customers|respondents|participants)'

        # Pattern 6: Narrative claims with research backing (NEW)
        narrative_claims_pattern = r'\b(?:studies?|research|reports?|surveys?|data|findings?|analysis|analyses)\s+(?:show|indicate|reveal|suggest|demonstrate|found|concluded)'

        # Pattern 7: Comparative statistics (NEW)
        comparative_pattern = r'\b(?:twice|double|triple|[\d]+x)\s+(?:as\s+)?(?:likely|effective|common|frequent|expensive|cheaper|faster|slower)'

        # Pattern 8: Year-based statistics (NEW)
        year_stats_pattern = r'\b(?:in|during|by)\s+(?:20\d{2}|recent years?),?\s+(?:[\d]+\.?[\d]*\s*%|[\d]+(?:,\d{3})*\s+(?:companies|businesses|organizations|users|customers))'

        # All patterns (original + new)
        all_patterns = [
            percentage_pattern,
            dollar_pattern,
            stat_pattern,
            benchmark_pattern,
            spelled_numbers_pattern,  # NEW
            narrative_claims_pattern,  # NEW
            comparative_pattern,       # NEW
            year_stats_pattern         # NEW
        ]

        # Extract all matching patterns with context
        for pattern in all_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                # Get 50 chars of context around match
                start = max(0, match.start() - 50)
                end = min(len(text), match.end() + 50)
                context = text[start:end].strip()
                claims.append(context)

        # Deduplicate by numeric core (not 50-char context window)
        seen_cores = set()
        unique_claims = []
        for claim in claims:
            numbers = re.findall(r'\d[\d,.]*%?', claim)
            core = ' '.join(numbers) if numbers else claim[:30]
            if core not in seen_cores:
                seen_cores.add(core)
                unique_claims.append(claim)
        claim_count = len(unique_claims)

        # Calculate required citations (logarithmic scaling)
        # One source often backs multiple claims (e.g., Verizon DBIR provides 5+ stats)
        import math
        if claim_count == 0:
            required = 0  # No claims = no citations needed
        elif claim_count <= 2:
            required = 3  # Few claims = maintain credibility floor
        else:
            # 3-5 claims → 3-5, 10 claims → 7, 21 claims → 9
            required = min(claim_count, 3 + int(math.log2(claim_count)))

        return {
            'has_claims': claim_count > 0,
            'claim_count': claim_count,
            'claim_samples': unique_claims[:3],
            'required_citations': required
        }

    @staticmethod
    def detect_unsimplifiable_jargon(content: str, keywords: list[str]) -> bool:
        """
        Detect if article uses many technical terms that can't be simplified.

        Heuristic: If >30% of unique words are 10+ characters AND not in common word list,
        likely unsimplifiable technical content (e.g., "authentication", "containerization").

        Returns True if jargon density suggests simplification is impossible.
        """
        from .readability_service import strip_markdown

        # Common long words that are NOT jargon
        COMMON_LONG_WORDS = {
            "organization", "information", "management", "important", "significant",
            "technology", "development", "experience", "environment", "different",
            "understand", "following", "including", "according", "implementation",
            "everything", "something", "understand", "understanding", "relationship",
            "relationships", "traditional", "customer", "customers", "professional",
            "professionals", "opportunity", "opportunities", "performance",
            "generation", "businesses", "enterprise", "enterprises", "investment",
            "investments", "protection", "competitive", "competition", "infrastructure",
        }

        clean = strip_markdown(content)
        words = re.findall(r'[a-zA-Z]+', clean.lower())

        if not words:
            return False

        long_words = [w for w in words if len(w) >= 10]
        unique_long = set(long_words) - COMMON_LONG_WORDS - set(k.lower() for k in keywords)

        jargon_density = len(unique_long) / len(set(words)) if set(words) else 0

        logger.debug(f"[JARGON] Unique long words: {len(unique_long)}, Total unique: {len(set(words))}, Density: {jargon_density:.2%}")
        if jargon_density > 0.25:
            logger.debug(f"[JARGON] Sample jargon: {list(unique_long)[:10]}")

        return jargon_density > 0.30
