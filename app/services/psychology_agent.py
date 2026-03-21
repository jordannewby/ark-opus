from __future__ import annotations
import json
import logging
import httpx
from pathlib import Path
from ..settings import DEEPSEEK_API_KEY, DEEPSEEK_TIMEOUT

logger = logging.getLogger(__name__)

DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"

class PsychologyAgent:
    """Uses DeepSeek-V3 (deepseek-chat) to generate a high-retention Psychological Blueprint."""

    def __init__(self, db):
        self.db = db
        
        if not DEEPSEEK_API_KEY:
            raise ValueError("DEEPSEEK_API_KEY environment variable is not set.")
        
        self.api_key = DEEPSEEK_API_KEY
        self.model_name = "deepseek-chat"
        
        prompt_path = Path(__file__).parent / "prompts" / "persuasion.md"
        with open(prompt_path, "r", encoding="utf-8") as f:
            self.system_prompt = f.read()

    async def generate_blueprint(self, research_data: dict) -> dict:
        """
        Takes Research JSON and outputs a structured blueprint.json based on PAS,
        Information Gap, and Semantic Entities.
        """
        prompt_instructions = (
            "You are to generate a psychological blueprint based on the following research data.\n\n"
            "CRITICAL CONTEXT:\n"
            f"- Information Gap: {research_data.get('information_gap', 'None found')}\n"
            f"- Semantic Entities: {', '.join(research_data.get('semantic_entities', []))}\n"
        )

        # Gap 15: Inject fact category distribution so blueprint designs around available evidence
        fact_cats = research_data.get("fact_categories")
        if fact_cats:
            prompt_instructions += (
                f"- Fact Evidence Profile: {fact_cats.get('total_facts', 0)} verified facts "
                f"(dominant type: {fact_cats.get('dominant_type', 'unknown')}). "
                f"Distribution: {json.dumps(fact_cats.get('distribution', {}))}\n"
            )
            if fact_cats.get("has_stats"):
                prompt_instructions += "  * Statistics available -- use data-driven hooks and agitation points\n"
            if fact_cats.get("has_case_studies"):
                prompt_instructions += "  * Case studies available -- leverage success/failure narratives\n"
            if fact_cats.get("has_expert_quotes"):
                prompt_instructions += "  * Expert quotes available -- use authority-based persuasion\n"

        prompt_instructions += (
            "\nFULL RESEARCH JSON:\n"
            f"{json.dumps(research_data, indent=2)}\n\n"
            "Ensure the output is STRICTLY a valid JSON object matching the required keys. "
            "Do NOT include markdown formatting like ```json or ```. Return ONLY the raw JSON object.\n"
            "Your outline_structure must use H2 headings (## prefix) for ALL main sections — "
            "the writer requires at least 5 H2 sections. Reserve H3 for sub-sections WITHIN an H2 only. "
            "Structure headings based on the PAS flow (Problem, Agitation, Solution)."
        )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": prompt_instructions}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.7,
        }

        async with httpx.AsyncClient(timeout=DEEPSEEK_TIMEOUT) as client:
            try:
                resp = await client.post(
                    DEEPSEEK_API_URL, headers=headers, json=payload
                )
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"].strip()
                
                # In case deepseek still includes markdown code blocks despite response_format
                if content.startswith("```json"):
                    content = content[7:]
                if content.startswith("```"):
                    content = content[3:]
                if content.endswith("```"):
                    content = content[:-3]
                    
                blueprint = json.loads(content.strip())

            except Exception as e:
                logger.error(f"DeepSeek Blueprint Generation Error: {e}")
                # Fallback empty blueprint on error
                blueprint = {
                    "hook_strategy": "Fallback Hook",
                    "target_identity": "Fallback Target",
                    "problem_statement": "Fallback Problem",
                    "agitation_points": ["Error fetching points"],
                    "identity_hooks": ["Error fetching hooks"],
                    "semantic_entity_map": [],
                    "outline_structure": []
                }

        # Enrich blueprint with SEO data from research for the writer
        blueprint["entities"] = research_data.get("semantic_entities", [])
        blueprint["semantic_keywords"] = research_data.get("people_also_ask", [])
        blueprint["content_patterns"] = research_data.get("content_patterns")  # Optional: SERP structure insights
        blueprint["information_gap"] = research_data.get("information_gap", "")

        # Normalize: ensure at least 5 H2 headings in outline
        outline = blueprint.get("outline_structure", [])
        h2_count = sum(1 for s in outline if isinstance(s, dict) and s.get("heading", "").startswith("H2"))
        if h2_count < 5:
            for section in outline:
                if not isinstance(section, dict):
                    continue
                heading = section.get("heading", "")
                if heading.startswith("H3:"):
                    section["heading"] = "H2:" + heading[3:]
                elif heading and not heading.startswith("H2"):
                    section["heading"] = "H2: " + heading

        return blueprint