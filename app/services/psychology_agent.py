from __future__ import annotations
import json
import os
from pathlib import Path
from google import genai
from google.genai import types
from ..schemas import BlueprintResponse
from ..settings import GEMINI_PSYCH_API_KEY

class PsychologyAgent:
    """Uses Gemini 2.5 Flash to generate a PAS-framework blueprint from research data."""

    def __init__(self, db):
        self.db = db
        
        if not GEMINI_PSYCH_API_KEY:
            raise ValueError("GEMINI_PSYCH_API_KEY environment variable is not set.")
        
        # Client still uses your specific key, but pointing to the Flash engine
        self.client = genai.Client(api_key=GEMINI_PSYCH_API_KEY)
        
        # UNIFIED: Switched to 2.5 Flash for speed and quota stability
        self.model_name = "gemini-2.5-flash"
        
        prompt_path = Path(__file__).parent / "prompts" / "persuasion.md"
        with open(prompt_path, "r", encoding="utf-8") as f:
            self.system_prompt = f.read()

    async def generate_blueprint(self, research_data: dict) -> dict:
        """
        Takes Research JSON and outputs a structured blueprint.json based on PAS.
        """
        prompt_instructions = (
            "You are to generate a psychological blueprint based on the following research data:\n\n"
            f"{json.dumps(research_data, indent=2)}\n\n"
            "Ensure the output matches the required JSON output schema. "
            "You MUST provide exactly 3 Identity Hooks. "
            "Your outline_structure must map out the SEO headings (H2/H3) for an entire 2,000-word post based on the PAS flow."
        )

        # Calling the unified Flash model
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt_instructions,
            config=types.GenerateContentConfig(
                system_instruction=self.system_prompt,
                response_mime_type="application/json",
                response_schema=BlueprintResponse,
                temperature=0.7,
            )
        )
        
        blueprint = json.loads(response.text)

        # Enrich blueprint with SEO data from research for the writer
        blueprint["entities"] = research_data.get("semantic_entities", [])
        blueprint["semantic_keywords"] = research_data.get("people_also_ask", [])

        return blueprint