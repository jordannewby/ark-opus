import json
import re
import asyncio
from pathlib import Path
from anthropic import AsyncAnthropic
from ..settings import ANTHROPIC_API_KEY
from .readability_service import verify_readability, READABILITY_DIRECTIVE


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

    async def produce_article(self, blueprint: dict, profile_name: str = "default", niche: str = "general"):
        """
        Takes a blueprint JSON and streams a formatted Markdown article using Anthropic.
        Enforces Information Gain, E-E-A-T, and Entity Density rules with an iterative SEO loop.
        """
        import json # Explicitly import to prevent shadowing by local assignments later in the function
        entities = blueprint.get("entities", [])
        semantic_keywords = blueprint.get("semantic_keywords", [])
        information_gap = blueprint.get("information_gap", "")

        # 1. Build Base Prompts
        system_instructions = self.base_system_prompt + (
            "\n\nTarget the optimal SEO blog length for ranking and high engagement (approximately 1,500 to 1,800 words). "
            "Be highly comprehensive, but eliminate all rambling and fluff. Conclude naturally once the Information Gap is fully addressed."
        )

        prompt_instructions = (
            "Write a focused ~1,600 word blog post based on the following psychological blueprint:\n\n"
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
            "1. NO AI FLUFF: Do NOT use the words 'delve', 'tapestry', 'landscape', 'multifaceted', 'comprehensive', 'holistic', 'navigate', or 'crucial'.\n"
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

        max_attempts = 5
        v_feedback = ""

        for attempt in range(1, max_attempts + 1):
            yield {"type": "debug", "message": f"Writer Iteration {attempt}: Starting draft generation..."}
            
            current_prompt = prompt_instructions
            if v_feedback:
                current_prompt += f"\n\nCRITICAL FEEDBACK FROM PREVIOUS ATTEMPT:\n{v_feedback}\nFix these issues in this new draft."

            full_content = ""
            try:
                async with self.client.messages.stream(
                    model=self.model_name,
                    max_tokens=8192,
                    system=system_instructions,
                    messages=[{"role": "user", "content": current_prompt}],
                    temperature=0.7
                ) as stream:
                    async for text_delta in stream.text_stream:
                        full_content += text_delta
                        yield {"type": "content", "data": text_delta}

                # 2. Perform SEO Validation
                yield {"type": "debug", "message": f"Writer Iteration {attempt}: Validating draft quality..."}
                score = self.verify_seo_score(full_content, information_gap)

                if score["passed"]:
                    yield {"type": "debug", "message": f"Writer Iteration {attempt}: Passed SEO validation."}

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
                        "leverage", "leveraged", "leveraging",
                        "optimize", "optimized", "optimizing", "optimization",
                        "enhance", "enhanced", "enhancement",
                        "framework", "frameworks",
                        "methodology", "methodologies",
                        "ecosystem", "ecosystems",
                        "paradigm", "paradigms",
                        "establish", "established", "establishing",
                        "execute", "executed", "executing", "execution",
                        "implement", "implemented", "implementing", "implementation",
                        "facilitate", "facilitated", "facilitating",
                        "comprehensive",
                        "infrastructure", "infrastructures",
                        "capability", "capabilities",
                        "operational",
                        "strategic",
                        "scalable", "scalability"
                    ]
                    read_keywords.extend(NICHE_TERMS)
                    # Deduplicate while preserving order
                    read_keywords = list(dict.fromkeys(read_keywords))
                    read_result = verify_readability(full_content, target_grade=10.0, keywords=read_keywords)

                    # DEBUG: Validate keyword masking effectiveness
                    if read_keywords:
                        import logging
                        logging.debug(f"[READABILITY] Masking {len(read_keywords)} keywords: {read_keywords[:10]}...")
                        sample_text = full_content[:500]
                        from app.services.readability_service import mask_keywords, strip_markdown
                        sample_masked = mask_keywords(strip_markdown(sample_text), read_keywords)
                        logging.debug(f"[READABILITY] Original: {sample_text[:100]}")
                        logging.debug(f"[READABILITY] Masked: {sample_masked[:100]}")

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
                        v_feedback = (
                            f"Readability Validation Failed (Iteration {attempt}).\n"
                            f"{read_result['feedback']}"
                        )
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

                        if attempt == max_attempts:
                            yield {"type": "debug", "message": "Max attempts reached. Returning best effort draft."}
                            yield {"status": "success", "text": full_content}
                            return

                        # Clear editor for next attempt
                        yield {"type": "content", "data": "RETRY_CLEAR"}
                else:
                    issues = []
                    if score['banned_words_used']:
                        issues.append(f"Banned words found: {', '.join(score['banned_words_found'])}")
                    if not score['word_count_ok']:
                        issues.append(f"Word count too low ({score['word_count']} words, need 1500+)")
                    if not score['h1_ok']:
                        issues.append(f"H1 heading issue (found {score['h1_count']}, need exactly 1)")
                    if not score['h2_ok']:
                        issues.append(f"Not enough H2 headings (found {score['h2_count']}, need 5+)")
                    if not score['lists_tables_ok']:
                        issues.append(f"Not enough list/table blocks (found {score['list_table_blocks']}, need 3+)")
                    if not score['info_gain_ok']:
                        issues.append(f"Information gain density too low ({score['info_gain_density']:.1f}, need 2.0+)")
                    v_feedback = (
                        f"SEO Validation Failed (Iteration {attempt}).\n"
                        + ("Issues:\n- " + "\n- ".join(issues) if issues else "Unknown validation failure")
                    )
                    yield {"type": "debug", "message": f"Writer Iteration {attempt} failed: {v_feedback}"}
                    
                    if attempt == max_attempts:
                        yield {"type": "debug", "message": "Max attempts reached. Returning best effort draft."}
                        yield {"status": "success", "text": full_content}
                        return
                    
                    # Clear editor for next attempt
                    yield {"type": "content", "data": "RETRY_CLEAR"}

            except Exception as e:
                error_msg = f"Anthropic API Error: {str(e)}"
                print(f"[Writer] {error_msg}")
                yield {"status": "error", "message": error_msg}
                return

    @staticmethod
    def verify_seo_score(text: str, information_gap: str = "") -> dict:
        """
        Validates generated article against basic SEO structure requirements and Information Gain Density.
        """
        lines = text.split("\n")
        word_count = len(text.split())

        # H1 count: lines starting with exactly '# ' (not '##')
        h1_count = sum(1 for line in lines if re.match(r"^# (?!#)", line))

        # H2 count: lines starting with exactly '## ' (not '###')
        h2_count = sum(1 for line in lines if re.match(r"^## (?!#)", line))

        # Count distinct list/table blocks
        list_table_blocks = 0
        in_block = False
        for line in lines:
            stripped = line.strip()
            is_list_or_table = bool(
                re.match(r"^[-*] ", stripped)
                or re.match(r"^\d+\. ", stripped)
                or re.match(r"^\|.+\|$", stripped)
            )
            if is_list_or_table and not in_block:
                list_table_blocks += 1
                in_block = True
            elif not is_list_or_table and stripped:
                in_block = False

        # Information Gain Density Check
        info_gain_density = 0
        if information_gap:
            significant_words = {w.lower() for w in re.findall(r'\b[A-Za-z]{5,}\b', information_gap)}
            if significant_words:
                text_lower = text.lower()
                word_counts = sum(text_lower.count(w) for w in significant_words)
                info_gain_density = word_counts / len(significant_words) if len(significant_words) > 0 else 0
                
        info_gain_ok = info_gain_density >= 2.0 if information_gap else True

        # Banned phrases check
        banned_list = ["delve", "tapestry", "landscape", "multifaceted", "comprehensive", "holistic", "navigate", "crucial", "in conclusion", "ultimately", "fast-paced world", "digital age", "game-changer"]
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
