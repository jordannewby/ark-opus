import json
import re
from pathlib import Path

from google import genai
from google.genai import types
from ..settings import GEMINI_API_KEY


class WriterService:
    """Uses Gemini 3 Flash Preview to enforce strict anti-AI prose logic."""

    def __init__(self, db):
        # Injecting db for consistency across the orchestration layer
        self.db = db

        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY environment variable is not set.")

        self.client = genai.Client(api_key=GEMINI_API_KEY)
        self.model_name = "gemini-3-flash-preview" # or gemini-3.0-flash-exp depending on API availability

        # Load the strict writer system prompt
        prompt_path = Path(__file__).parent / "prompts" / "writer.md"
        with open(prompt_path, "r", encoding="utf-8") as f:
            self.system_prompt = f.read()

    async def produce_article(self, blueprint: dict) -> str:
        """
        Takes a blueprint JSON and outputs a formatted Markdown article.
        Enforces Information Gain, E-E-A-T, and Entity Density rules.
        """
        entities = blueprint.get("entities", [])
        semantic_keywords = blueprint.get("semantic_keywords", [])

        # Start building the user prompt
        prompt_instructions = (
            "Write a full ~2,000 word blog post based on the following psychological blueprint:\n\n"
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
            "4. CADENCE: Max 3 sentences per paragraph. Short, punchy, aggressive delivery.\n"
        )
        
        # Inject Dynamic Human Style Rules learned from previous edits
        from ..models import UserStyleRule
        style_rules = self.db.query(UserStyleRule).all()
        if style_rules:
            prompt_instructions += "\n--- HUMAN STYLE GUIDELINES LEARNED FROM PAST EDITS ---\n"
            prompt_instructions += "You MUST organically integrate these stylistic preferences into your writing:\n"
            for rule in style_rules:
                prompt_instructions += f"- {rule.rule_description}\n"
            prompt_instructions += "--------------------------------------------------------\n"

        prompt_instructions += "\nFollow all system prompt guidelines strictly. Write directly in Markdown."

        try:
             response = self.client.models.generate_content(
                 model=self.model_name,
                 contents=prompt_instructions,
                 config=types.GenerateContentConfig(
                     system_instruction=self.system_prompt,
                     temperature=0.8,
                     max_output_tokens=4000,
                 ),
             )
             return response.text
             
        except Exception as e:
             print(f"Gemini SDK Error: {e}")
             return f"Error Generating Article: {e}"

    @staticmethod
    def verify_seo_score(text: str, information_gap: str = "") -> dict:
        """
        Validates generated article against basic SEO structure requirements and Information Gain Density.
        """
        lines = text.split("\n")

        # Word count
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
        # specific insight from the Information Gap MUST appear at least 3 times
        info_gain_density = 0
        if information_gap:
            # Extract significant unique nouns/keywords from the gap
            significant_words = {w.lower() for w in re.findall(r'\b[A-Za-z]{5,}\b', information_gap)}
            if significant_words:
                text_lower = text.lower()
                # Count the total occurrences of these significant concepts
                word_counts = sum(text_lower.count(w) for w in significant_words)
                # Average mentions per significant concept as a proxy for density
                info_gain_density = word_counts / len(significant_words) if len(significant_words) > 0 else 0
                
        info_gain_ok = info_gain_density >= 3.0 if information_gap else True

        # Banned phrases check
        banned_list = ["delve", "tapestry", "landscape", "multifaceted", "comprehensive", "holistic", "navigate", "crucial", "in conclusion", "ultimately", "fast-paced world", "digital age", "game-changer"]
        text_lower = text.lower()
        found_banned_words = [word for word in banned_list if word in text_lower]
        banned_words_used = len(found_banned_words) > 0

        passed = (
            word_count >= 1500  # Adjusted slightly per Haiku's length distribution
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