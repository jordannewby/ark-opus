from __future__ import annotations
import json
import httpx
from pathlib import Path
from ..settings import DEEPSEEK_API_KEY

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
            f"- Semantic Entities: {', '.join(research_data.get('semantic_entities', []))}\n\n"
            "FULL RESEARCH JSON:\n"
            f"{json.dumps(research_data, indent=2)}\n\n"
            "Ensure the output is STRICTLY a valid JSON object matching the required keys. "
            "Do NOT include markdown formatting like ```json or ```. Return ONLY the raw JSON object.\n"
            "Your outline_structure must map out the SEO headings (H2/H3) based on the PAS flow (Problem, Agitation, Solution)."
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

        async with httpx.AsyncClient(timeout=60) as client:
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
                print(f"DeepSeek Blueprint Generation Error: {e}")
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

        return blueprint