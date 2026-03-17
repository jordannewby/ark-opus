import json
from google import genai
from google.genai import types
from ..settings import GEMINI_API_KEY

class BriefingAgent:
    """Uses Gemini 2.5 Flash to quickly ask clarifying questions before heavy research begins."""

    def __init__(self):
        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY environment variable is not set.")

        self.client = genai.Client(api_key=GEMINI_API_KEY)
        self.model_name = "gemini-2.5-pro"

    async def get_clarifying_questions(self, keyword: str) -> list[str]:
        """Generates exactly 3 short, targeted questions based on the keyword."""
        prompt = (
            f"The user wants our autonomous SEO engine to write a comprehensive article about '{keyword}'.\n"
            "Ask exactly 3 short, highly targeted questions to clarify the intent, target audience, and primary goal.\n"
            "Examples: 'Are we targeting enterprise CTOs or junior devs?' or 'Is the primary goal lead generation or brand awareness?'\n"
            "Return ONLY a valid JSON array of 3 strings. Do not include markdown blocks like ```json."
        )

        try:
            response = await self.client.aio.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.7,
                    response_mime_type="application/json"
                )
            )
            
            content = response.text.strip()
            if content.startswith("```json"):
                content = content.replace("```json", "").replace("```", "").strip()
                
            questions = json.loads(content)
            
            # Ensure it's strictly a list of 3 strings
            if isinstance(questions, list) and len(questions) > 0:
                return [str(q) for q in questions][:3]
            
            return ["Who is the exact target audience?", "What is the primary goal of this article?", "Are there any specific pain points to highlight?"]
            
        except Exception as e:
            print(f"BriefingAgent Error: {e}")
            return ["Could you clarify the main objective?", "Who should be reading this?", "What is the key takeaway?"]
