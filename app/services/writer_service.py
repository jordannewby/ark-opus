import json
import re
from pathlib import Path

from google import genai
# Import the Flash-specific key from settings
from ..settings import GEMINI_API_KEY


class WriterService:
    """Uses Gemini 2.5 Flash for high-speed, 2,000-word generation."""

    def __init__(self, db):
        # Injecting db for consistency across the orchestration layer
        self.db = db

        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY environment variable is not set.")

        # This client is explicitly locked to the standard Flash key
        self.client = genai.Client(api_key=GEMINI_API_KEY)

        # UNIFIED: Updated to 2.5 Flash to ensure stable API calls
        self.model_name = "gemini-2.5-flash"

        # Load the system prompt
        prompt_path = Path(__file__).parent / "prompts" / "writer.md"
        with open(prompt_path, "r", encoding="utf-8") as f:
            self.system_prompt = f.read()

    async def produce_article(self, blueprint: dict) -> str:
        """
        Takes a blueprint JSON and outputs a 2,000-word Markdown article.
        Extracts entities and semantic keywords from the blueprint to fuel SEO.
        """
        entities = blueprint.get("entities", [])
        semantic_keywords = blueprint.get("semantic_keywords", [])

        prompt_instructions = (
            "Write a full ~2,000 word blog post based on the following psychological blueprint:\n\n"
            f"{json.dumps(blueprint, indent=2)}\n\n"
        )

        if entities:
            prompt_instructions += f"## SEO Entities to Weave Naturally:\n{', '.join(entities)}\n\n"

        if semantic_keywords:
            prompt_instructions += f"## Semantic Keywords to Include:\n{', '.join(semantic_keywords)}\n\n"

        prompt_instructions += "Follow all system prompt guidelines. Write in Markdown."

        # Calling the unified Flash model
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt_instructions,
            config=genai.types.GenerateContentConfig(
                system_instruction=self.system_prompt,
                temperature=0.8,
            ),
        )

        return response.text

    @staticmethod
    def verify_seo_score(text: str) -> dict:
        """
        Validates generated article against basic SEO structure requirements.
        Returns a dict with individual checks and an overall pass/fail.
        """
        lines = text.split("\n")

        # Word count
        word_count = len(text.split())

        # H1 count: lines starting with exactly '# ' (not '##')
        h1_count = sum(1 for line in lines if re.match(r"^# (?!#)", line))

        # H2 count: lines starting with exactly '## ' (not '###')
        h2_count = sum(1 for line in lines if re.match(r"^## (?!#)", line))

        # Count distinct list/table blocks (consecutive list items or table rows count as one)
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

        passed = (
            word_count >= 2000
            and h1_count >= 1
            and h2_count >= 5
            and list_table_blocks >= 3
        )

        return {
            "word_count": word_count,
            "word_count_ok": word_count >= 2000,
            "h1_count": h1_count,
            "h1_ok": h1_count >= 1,
            "h2_count": h2_count,
            "h2_ok": h2_count >= 5,
            "list_table_blocks": list_table_blocks,
            "lists_tables_ok": list_table_blocks >= 3,
            "passed": passed,
        }