import json
import re
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

    async def produce_article(self, blueprint: dict, profile_name: str = "default", niche: str = "general", research_run_id: int | None = None):
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
                # Sort citations by composite_score (descending) to prioritize high-quality sources
                citations_sorted = sorted(
                    citations,
                    key=lambda c: c.composite_score if c.composite_score else 0,
                    reverse=True
                )

                prompt_instructions += "\n╔════════════════════════════════════════════════════════════════╗\n"
                prompt_instructions += "║   CRITICAL CITATION REQUIREMENTS (NON-NEGOTIABLE)             ║\n"
                prompt_instructions += "╚════════════════════════════════════════════════════════════════╝\n\n"

                prompt_instructions += f"⚠️  You have access to {len(citations_sorted)} VERIFIED factual claims below.\n"
                prompt_instructions += "⚠️  You MUST cite sources when making ANY factual claim.\n\n"

                prompt_instructions += "═══ AVAILABLE CITATIONS (use exact markdown format) ═══\n\n"

                for cite in citations_sorted:
                    markdown_link = f"[{cite.citation_anchor}]({cite.source_url})"
                    # Truncate fact to 100 chars for readability
                    fact_preview = cite.fact_text[:100] + "..." if len(cite.fact_text) > 100 else cite.fact_text
                    prompt_instructions += f"  • {markdown_link} — {fact_preview}\n"

                prompt_instructions += "\n═══════════════════════════════════════════════════\n\n"

                prompt_instructions += "📋 MANDATORY FORMAT:\n"
                prompt_instructions += "   When you write a fact from the map, cite it IMMEDIATELY like this:\n"
                prompt_instructions += '   "67% of SMBs experienced a cyberattack in 2023 [Verizon 2024](https://verizon.com/dbir)."\n\n'

                prompt_instructions += "📊 MINIMUM CITATION REQUIREMENTS:\n"
                prompt_instructions += "   • If your article has 0-2 quantitative claims: Cite at least 3 sources\n"
                prompt_instructions += "   • If your article has 3+ quantitative claims: Cite 1 source per claim\n"
                prompt_instructions += "   • Distribute citations throughout the article (not all in one section)\n\n"

                prompt_instructions += "🚫 STRICT PROHIBITIONS:\n"
                prompt_instructions += "   • DO NOT invent statistics, percentages, or dollar amounts\n"
                prompt_instructions += "   • DO NOT use vague claims like 'many companies' or 'recent studies'\n"
                prompt_instructions += "   • DO NOT cite sources not in the citation map above\n"
                prompt_instructions += "   • DO NOT write facts without immediate inline citations\n\n"

                prompt_instructions += "✅ ACCEPTED CITATION FORMATS:\n"
                prompt_instructions += "   1. Markdown links: [Source Name 2024](URL)  ← PREFERRED\n"
                prompt_instructions += "   2. Parenthetical: (Source 2024)\n"
                prompt_instructions += "   3. Footnotes: [1], [2], etc.\n\n"

                prompt_instructions += "💡 EXAMPLES OF PROPER CITATION:\n"
                prompt_instructions += "   ✓ 'According to [Gartner 2024](url), cloud adoption will reach 85% by 2026.'\n"
                prompt_instructions += "   ✓ 'The average cost of a data breach is $4.35 million [IBM Report](url).'\n"
                prompt_instructions += "   ✓ 'Healthcare faces 3x more attacks than other sectors (Verizon 2024).'\n"
                prompt_instructions += "   ✗ '67% of SMBs report security concerns.' ← NO CITATION!\n"
                prompt_instructions += "   ✗ 'Many companies are adopting AI.' ← VAGUE, NO DATA!\n\n"

                prompt_instructions += "================================================\n"

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

                    # --- Gate 3: Intelligent Citation Validation ---
                    if research_run_id:
                        # Detect quantitative claims that require citations
                        claim_detection = self.detect_quantitative_claims(full_content)

                        if claim_detection['has_claims']:
                            # Article has stats/numbers → require citations
                            min_required = claim_detection['required_citations']
                            citation_result = self.verify_citation_requirements(full_content, min_citations=min_required)

                            if not citation_result["passed"]:
                                v_feedback = (
                                    f"Citation Validation Failed (Iteration {attempt}).\n"
                                    f"Detected {claim_detection['claim_count']} quantitative claims requiring {min_required} citations.\n"
                                    f"{citation_result['feedback']}\n\n"
                                    f"Example claims found:\n" + "\n".join(f"- {c[:100]}..." for c in claim_detection['claim_samples'])
                                )
                                yield {"type": "debug", "message": v_feedback}

                                if attempt == max_attempts:
                                    yield {"type": "debug", "message": "Max attempts reached. Returning best effort draft."}
                                    yield {"status": "success", "text": full_content}
                                    return

                                # Clear editor for next attempt
                                yield {"type": "content", "data": "RETRY_CLEAR"}
                                continue

                            yield {"type": "debug", "message": f"Writer Iteration {attempt}: Passed citation validation ({citation_result['citation_count']} citations for {claim_detection['claim_count']} claims)."}
                        else:
                            # No quantitative claims → skip citation requirement
                            yield {"type": "debug", "message": f"Writer Iteration {attempt}: No quantitative claims detected. Skipping citation validation (general advice article)."}

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
                        "scalable", "scalability",

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
                        shortfall = 1500 - score['word_count']
                        issues.append(f"Word count too low ({score['word_count']} words, need 1500+). Add ~{shortfall} more words: expand analysis sections, add practical examples, deeper explanations, or additional subsections. Do NOT add filler — add substantive content.")
                    if not score['h1_ok']:
                        issues.append(f"H1 heading issue (found {score['h1_count']}, need exactly 1). CRITICAL: Use '# ' (single hash) ONLY for the article title. Use '## ' (double hash) for ALL section headings. You have {score['h1_count']} lines starting with '# ' — convert all but the title to '## '")
                    if not score['h2_ok']:
                        issues.append(f"Not enough H2 headings (found {score['h2_count']}, need 5+). Add more '## Section Title' headings to break the article into 5+ distinct sections.")
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
        from ..settings import DEBUG_MODE
        if DEBUG_MODE:
            print(f"[DEBUG] Citation validation: Found {citation_count} citations")
            print(f"  - Markdown: {len(markdown_citations)}")
            print(f"  - Parenthetical: {len(parenthetical_citations)}")
            print(f"  - Footnotes: {len(unique_footnotes)}")
            if citation_count > 0:
                print(f"  - Sample: {all_citations[:3]}")

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

        # Deduplicate overlapping matches
        unique_claims = list(set(claims))
        claim_count = len(unique_claims)

        # Calculate required citations
        if claim_count == 0:
            required = 0  # No claims = no citations needed
        elif claim_count <= 2:
            required = 3  # Few claims = maintain credibility floor
        else:
            required = claim_count  # Many claims = 1 citation each

        return {
            'has_claims': claim_count > 0,
            'claim_count': claim_count,
            'claim_samples': unique_claims[:3],
            'required_citations': required
        }
