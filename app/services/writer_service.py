import json
import logging
import re
from pathlib import Path
from anthropic import AsyncAnthropic
from ..database import ensure_db_alive
from ..settings import ANTHROPIC_API_KEY, CLAUDE_MODEL, MAX_WRITER_ATTEMPTS, WRITER_MAX_TOKENS, LLM_SOURCE_CONTEXT_CHARS, MAX_UNCITED_CLAIMS
from ..security import sanitize_external_content
from .readability_service import verify_readability

logger = logging.getLogger(__name__)


# Module-level banned-word replacements (used by both WriterService and editor_node)
# Must include all inflected forms since SEO gate uses substring matching
BANNED_REPLACEMENTS = {
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


def sanitize_banned_words(text: str) -> str:
    """Replace banned words and their inflections with safe alternatives, preserving case."""
    for banned, replacement in BANNED_REPLACEMENTS.items():
        pattern = re.compile(r'\b' + re.escape(banned) + r'\b', re.IGNORECASE)
        def _match_case(match, repl=replacement):
            word = match.group()
            if word[0].isupper():
                return repl[0].upper() + repl[1:]
            return repl
        text = pattern.sub(_match_case, text)
    return text


class WriterService:
    """Uses Anthropic Claude 4 Sonnet to enforce strict anti-AI prose logic & deep comprehensiveness."""

    def __init__(self, db):
        self.db = db
        if not ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY environment variable is not set.")

        self.client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        self.model_name = CLAUDE_MODEL

        # Load the strict writer system prompt
        prompt_path = Path(__file__).parent / "prompts" / "writer.md"
        with open(prompt_path, "r", encoding="utf-8") as f:
            self.base_system_prompt = f.read()

    _BANNED_REPLACEMENTS = BANNED_REPLACEMENTS

    def _sanitize_banned_words(self, text: str) -> str:
        """Replace banned words and their inflections with safe alternatives, preserving case."""
        return sanitize_banned_words(text)

    async def produce_article(self, blueprint: dict, profile_name: str = "default", niche: str = "general", research_run_id: int | None = None, source_content_map: dict | None = None, claim_feedback: str | None = None, settings_override: dict | None = None):
        """
        Uses LangGraph Agentic RAG architecture to plan, retrieve, write, and edit the article section-by-section.
        """
        from .writer_agent_graph import app_graph, WriterState
        import logging
        logger = logging.getLogger(__name__)
        
        all_citations = []
        if research_run_id:
            from ..models import FactCitation
            self.db = ensure_db_alive(self.db)
            citations = self.db.query(FactCitation).filter_by(research_run_id=research_run_id).all()

            logger.info(f"[CITATION-FILTER] Starting with {len(citations)} raw citations from research_run {research_run_id}")

            _QUANT_RE = re.compile(r'\d+%|\$\d|percent|\d+\.\d+')
            verified_citations = []

            # Diagnostic counters
            filtered_unverified = 0
            filtered_quant_not_checked = 0
            passed_quant_verified = 0
            passed_non_quant = 0

            for c in citations:
                if not getattr(c, 'is_verified', True):
                    filtered_unverified += 1
                    continue

                status = getattr(c, 'verification_status', 'not_checked') or 'not_checked'
                fact_text = getattr(c, 'fact_text', '') or ''

                # Quantitative claims (stats, percentages, dollar figures) require
                # strong verification — "not_checked" is insufficient
                if _QUANT_RE.search(fact_text):
                    if status not in ("corroborated", "trusted"):
                        filtered_quant_not_checked += 1
                        logger.debug(
                            f"[CITATION-FILTER] Filtered quantitative citation (status={status}): "
                            f"{fact_text[:80]}... from {c.source_url}"
                        )
                        continue
                    else:
                        passed_quant_verified += 1
                else:
                    passed_non_quant += 1

                verified_citations.append(c)

            logger.info(
                f"[CITATION-FILTER] Results: "
                f"{len(verified_citations)} passed, "
                f"{filtered_unverified} filtered (is_verified=False), "
                f"{filtered_quant_not_checked} filtered (quantitative + not verified), "
                f"{passed_quant_verified} passed (quantitative + verified), "
                f"{passed_non_quant} passed (non-quantitative)"
            )

            # If ALL citations were filtered due to verification, log critical warning
            if citations and not verified_citations:
                logger.critical(
                    f"[CITATION-FILTER] ZERO citations passed! All {len(citations)} citations filtered. "
                    f"This will cause writer to fail. Breakdown: "
                    f"is_verified=False: {filtered_unverified}, "
                    f"quantitative+not_checked: {filtered_quant_not_checked}"
                )

            def _usability_weight(c):
                status = getattr(c, 'verification_status', 'not_checked') or 'not_checked'
                if status in ("corroborated", "trusted"):
                    tier_mult = 1.5
                elif status == "not_checked":
                    tier_mult = 0.6
                elif status == "suspect":
                    tier_mult = 0.4
                else:
                    tier_mult = 0.5
                grounding_mult = 1.2 if getattr(c, 'is_grounded', True) else 0.8
                return (c.composite_score or 0) * tier_mult * grounding_mult

            citations_sorted = sorted(verified_citations, key=_usability_weight, reverse=True)
            for c in citations_sorted:
                all_citations.append({
                    "citation_anchor": c.citation_anchor,
                    "source_url": c.source_url,
                    "fact_text": c.fact_text,
                    "confidence": round(c.confidence_score, 2) if c.confidence_score else 0.0,
                    "verification_status": getattr(c, 'verification_status', 'not_checked') or 'not_checked',
                })

        # Inject Dynamic Human Style Rules (capped to prevent prompt crowding)
        from ..models import UserStyleRule
        from ..settings import MAX_STYLE_RULES_CHARS
        style_rules_text = ""
        self.db = ensure_db_alive(self.db)
        style_rules = self.db.query(UserStyleRule).filter(UserStyleRule.profile_name == profile_name).all()
        if style_rules:
            for rule in style_rules:
                safe_rule = sanitize_external_content(rule.rule_description, max_chars=500)
                style_rules_text += f"- {safe_rule}\n"
            if len(style_rules_text) > MAX_STYLE_RULES_CHARS:
                style_rules_text = style_rules_text[:MAX_STYLE_RULES_CHARS] + "\n[...truncated]\n"

        if claim_feedback:
            safe_feedback = sanitize_external_content(claim_feedback, max_chars=2000)
            style_rules_text += "\n\n=== CLAIM VERIFICATION FEEDBACK (MUST FIX) ===\n"
            style_rules_text += safe_feedback
            style_rules_text += "\n=== END CLAIM FEEDBACK ===\n"

        initial_state: WriterState = {
            "blueprint": blueprint,
            "profile_name": profile_name,
            "niche": niche,
            "all_citations": all_citations,
            "style_rules": style_rules_text,
            "psychology_directives": "",
            "sections_planned": [],
            "current_section_idx": 0,
            "draft_sections": [],
            "current_section_citations": [],
            "current_section_draft": "",
            "section_feedback": "",
            "section_retry_count": 0,
            "final_article": "",
            "yield_messages": []
        }
        
        final_state = None
        try:
            async for output in app_graph.astream(initial_state, stream_mode="updates", recursion_limit=75):
                for node_name, state_update in output.items():
                    if "yield_messages" in state_update:
                        for msg in state_update["yield_messages"]:
                            yield msg
                    final_state = state_update
        except Exception as e:
            error_msg = f"LangGraph Execution Error: {str(e)}"
            logger.error(f"[Writer] {error_msg}")
            yield {"status": "error", "message": error_msg}
            return

        final_text = final_state.get("final_article", "") if hasattr(final_state, "get") else ""
        if not final_text:
            yield {"status": "error", "message": "Failed to generate article using LangGraph."}
            return
            
        from .readability_service import verify_readability
        read_result = verify_readability(final_text)
        details = read_result.get("details", {})

        yield {
            "status": "success", 
            "text": final_text, 
            "readability_score": {
                "ari": details.get("ari_grade", 0),
                "fk": details.get("flesch_kincaid_grade", 0),
                "cli": details.get("coleman_liau_grade", 0),
                "avg_sentence_length": details.get("avg_sentence_length", 0)
            }, 
            "quality_flag": "agentic_rag"
        }

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