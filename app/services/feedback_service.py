import json
import httpx
from ..settings import DEEPSEEK_API_KEY
from ..models import UserStyleRule

DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"

class FeedbackAgent:
    """Uses DeepSeek V3 to diff AI vs Human text and extract persistent style rules."""

    def __init__(self, db):
        self.db = db

        if not DEEPSEEK_API_KEY:
            raise ValueError("DEEPSEEK_API_KEY environment variable is not set.")

        self.api_key = DEEPSEEK_API_KEY
        self.model_name = "deepseek-chat"

        self.system_prompt = (
            "You are a master linguistic analyst and editor. Your job is to compare an original AI-generated text "
            "against the human's final edited version. \n"
            "Analyze the changes the human made (e.g., deleted adjectives, shortened sentences, changed formatting, altered tone). "
            "Extract max 3 overarching, permanent 'style rules' that the AI should follow in the future to sound exactly like this human.\n"
            "Format your response as a raw JSON array of strings, e.g.:\n"
            "[\n"
            "  \"Rule 1: Always use strict, aggressive bullet points instead of narrative paragraphs.\",\n"
            "  \"Rule 2: Never use words like 'robust' or 'seamless'.\"\n"
            "]\n"
            "Do NOT return markdown blocks (like ```json). Return ONLY the raw JSON array."
        )

    async def analyze_and_store_feedback(self, original_text: str, edited_text: str, profile_name: str = "default") -> list[str]:
        """
        Takes the original AI text and the human's edited text, asks DeepSeek to extract style rules,
        and saves them to the UserStyleRule database.
        """
        # If the texts are identical, don't waste API calls
        if original_text.strip() == edited_text.strip():
            print("[FEEDBACK] Text matched original. No new style rules learned.")
            return []

        prompt_instructions = (
            "## ORIGINAL AI DRAFT:\n"
            f"{original_text}\n\n"
            "## HUMAN EDITED FINAL DRAFT:\n"
            f"{edited_text}\n\n"
            "Extract the 3 most important writing style rules based on how the human changed the text."
        )

        try:
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
                 "temperature": 0.2,
             }

             async with httpx.AsyncClient(timeout=60) as client:
                 resp = await client.post(DEEPSEEK_API_URL, headers=headers, json=payload)
                 resp.raise_for_status()
                 content = resp.json()["choices"][0]["message"]["content"].strip()

             # Strip markdown if present
             if content.startswith("```json"):
                 content = content[7:]
             if content.startswith("```"):
                 content = content[3:]
             if content.endswith("```"):
                 content = content[:-3]

             parsed = json.loads(content.strip())

             # Handle both {"rules": [...]} and [...] formats
             if isinstance(parsed, dict):
                 rules = parsed.get("rules", list(parsed.values())[0] if parsed else [])
             elif isinstance(parsed, list):
                 rules = parsed
             else:
                 rules = []

             # Save to DB
             for rule_text in rules:
                 new_rule = UserStyleRule(rule_description=rule_text, profile_name=profile_name)
                 self.db.add(new_rule)

             if rules:
                 self.db.commit()
                 print(f"[FEEDBACK] Learned {len(rules)} new writing style rules!")

                 # Automatically trigger distillation if needed
                 await self.prune_style_rules(profile_name)

             return rules

        except Exception as e:
             print(f"[FEEDBACK ERROR] DeepSeek Feedback Error: {e}")
             self.db.rollback()
             return []

    async def prune_style_rules(self, profile_name: str = "default"):
        """
        Consolidates rules if the user has accumulated > 20 rules to prevent memory leaks and prompt bloat.
        """
        rules = self.db.query(UserStyleRule).filter(UserStyleRule.profile_name == profile_name).order_by(UserStyleRule.id.asc()).all()
        if len(rules) <= 20:
            return

        print(f"[FEEDBACK] Starting Style Pruning for '{profile_name}' ({len(rules)} rules)...")
        rule_texts = [r.rule_description for r in rules]
        blocks = "\n".join(f"{i+1}. {r}" for i, r in enumerate(rule_texts))

        prompt = (
            "You are a master linguistic editor. The following is a raw, rambling list of style rules learned over time.\n"
            "Many of them are overlapping, contradictory, or redundant.\n\n"
            f"RAW RULES:\n{blocks}\n\n"
            "Consolidate and distill these into a pristine, mutually exclusive list of at most 10 overarching style rules. "
            "Return ONLY a raw JSON array of strings. Do not use markdown blocks."
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
                 "temperature": 0.1,
             }

             async with httpx.AsyncClient(timeout=60) as client:
                 resp = await client.post(DEEPSEEK_API_URL, headers=headers, json=payload)
                 resp.raise_for_status()
                 content = resp.json()["choices"][0]["message"]["content"].strip()

             # Strip markdown if present
             if content.startswith("```json"):
                 content = content[7:]
             if content.startswith("```"):
                 content = content[3:]
             if content.endswith("```"):
                 content = content[:-3]

             parsed = json.loads(content.strip())

             # Handle both {"rules": [...]} and [...] formats
             if isinstance(parsed, dict):
                 new_rules = parsed.get("rules", list(parsed.values())[0] if parsed else [])
             elif isinstance(parsed, list):
                 new_rules = parsed
             else:
                 return

             if len(new_rules) == 0:
                 return

             # Archive old rules before pruning (Gap 20: prevent data loss)
             from ..models import UserStyleRuleArchive
             archive = UserStyleRuleArchive(
                 profile_name=profile_name,
                 rule_descriptions_json=json.dumps(rule_texts),
                 pruned_to_count=len(new_rules),
             )
             self.db.add(archive)

             # Safe pruning: only delete old rules AFTER new ones are validated
             for r in rules:
                 self.db.delete(r)

             for rule_text in new_rules:
                 new_rule = UserStyleRule(rule_description=rule_text, profile_name=profile_name)
                 self.db.add(new_rule)

             self.db.commit()
             print(f"[FEEDBACK] Pruned {len(rules)} rules down to {len(new_rules)} optimized rules.")

        except Exception as e:
             print(f"[FEEDBACK ERROR] Pruning Error: {e}")
             self.db.rollback()
