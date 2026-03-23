import json
import logging
import httpx
from ..settings import DEEPSEEK_API_KEY, BRIEFING_TIMEOUT

logger = logging.getLogger(__name__)

DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"

class BriefingAgent:
    """Uses DeepSeek V3 to quickly ask clarifying questions before heavy research begins."""

    def __init__(self):
        if not DEEPSEEK_API_KEY:
            raise ValueError("DEEPSEEK_API_KEY environment variable is not set.")

        self.api_key = DEEPSEEK_API_KEY
        self.model_name = "deepseek-chat"

    async def get_clarifying_questions(self, keyword: str, niche: str = "") -> list[str]:
        """Generates exactly 3 short, targeted questions based on the keyword and niche."""
        niche_context = f" in the '{niche}' niche" if niche else ""
        prompt = (
            f"The user wants our autonomous SEO engine to write a comprehensive article about '{keyword}'{niche_context}.\n"
            "Ask exactly 3 short, highly targeted questions to clarify the intent, target audience, and primary goal.\n"
            f"{'Tailor questions to the ' + niche + ' audience. ' if niche else ''}"
            "Examples: 'Are we targeting enterprise CTOs or junior devs?' or 'Is the primary goal lead generation or brand awareness?'\n"
            "Return ONLY a valid JSON array of 3 strings. Do not include markdown blocks like ```json."
        )

        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": self.model_name,
                "messages": [
                    {"role": "system", "content": "You output raw JSON arrays ONLY."},
                    {"role": "user", "content": prompt}
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.7
            }

            async with httpx.AsyncClient(timeout=BRIEFING_TIMEOUT) as client:
                resp = await client.post(DEEPSEEK_API_URL, headers=headers, json=payload)
                resp.raise_for_status()
                content = resp.json()["choices"][0]["message"]["content"].strip()

            if content.startswith("```json"):
                content = content.replace("```json", "").replace("```", "").strip()

            questions = json.loads(content)

            # Handle both {"questions": [...]} and [...] formats
            if isinstance(questions, dict):
                questions = questions.get("questions", list(questions.values())[0] if questions else [])

            if isinstance(questions, list) and len(questions) > 0:
                return [str(q) for q in questions][:3]

            return ["Who is the exact target audience?", "What is the primary goal of this article?", "Are there any specific pain points to highlight?"]

        except Exception as e:
            logger.error(f"BriefingAgent Error: {e}")
            return ["Could you clarify the main objective?", "Who should be reading this?", "What is the key takeaway?"]
