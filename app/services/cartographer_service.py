import json
import logging
import httpx
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import desc

from ..database import ensure_db_alive
from ..models import ContentCampaign
from ..security import sanitize_prompt_input

logger = logging.getLogger(__name__)
from ..schemas import CampaignResponse, PillarKeyword, SpokeKeyword
from ..settings import DATAFORSEO_LOGIN, DATAFORSEO_PASSWORD, DEEPSEEK_API_KEY, DEEPSEEK_REASONER_MODEL, CARTOGRAPHER_TIMEOUT


class CartographerService:
    def __init__(self, db: Session):
        self.db = db

    def get_campaigns(self, profile_name: str):
        campaigns = self.db.query(ContentCampaign).filter(
            ContentCampaign.profile_name == profile_name
        ).order_by(desc(ContentCampaign.created_at)).all()
        
        response_list = []
        for c in campaigns:
            spokes_data = json.loads(c.spoke_keywords_json) if c.spoke_keywords_json else []
            pillar_data = PillarKeyword(keyword=c.pillar_keyword, kd=0, vol=0) # KD/Vol for pillar not persisted natively in DB columns, inferring from JSON later if needed, but schema requires it. Let's adjust approach or stick to returning the model.
            
            # The schema expects a PillarKeyword and a list of SpokeKeyword. 
            # Spoke keywords are stored as JSON. Pillar keyword is stored as string.
            
            # Reconstruct response to match CampaignResponse exactly:
            # Re-parsing from spoke_keywords_json which we'll store as the full JSON object
            # including both pillar and spokes to make mapping back to schema easier.
            try:
                full_map = json.loads(c.spoke_keywords_json)
                pillar_obj = PillarKeyword(**full_map.get("pillar", {"keyword": c.pillar_keyword, "kd": 0, "vol": 0}))
                spokes_list = [SpokeKeyword(**s) for s in full_map.get("spokes", [])]
            except Exception:
                pillar_obj = PillarKeyword(keyword=c.pillar_keyword, kd=0, vol=0)
                spokes_list = []

            response_list.append(
                CampaignResponse(
                    id=c.id,
                    profile_name=c.profile_name,
                    seed_topic=c.seed_topic,
                    pillar=pillar_obj,
                    spokes=spokes_list,
                    created_at=c.created_at
                )
            )
        return response_list

    async def plan_campaign(self, seed_topic: str, profile_name: str, niche_context: str = ""):
        # 1. Fetch from DataForSEO
        keyword_data = await self._fetch_dataforseo_keywords(seed_topic)
        
        # 2. Token Optimization: Map massive payload down to minimal dicts
        minimal_data = []
        for item in keyword_data:
            minimal_data.append({
                "keyword": item.get("keyword", ""),
                "search_volume": item.get("keyword_info", {}).get("search_volume", 0),
                "keyword_difficulty": item.get("keyword_properties", {}).get("keyword_difficulty", 0)
            })

        # 3. Call DeepSeek-Reasoner
        json_output = await self._call_deepseek_reasoner(seed_topic, minimal_data, niche_context)
        
        # 4. Parse JSON with Markdown Strip Resilience
        import re
        try:
            # Robust regex extraction to find the JSON object even if surrounded by text
            match = re.search(r'\{.*\}', json_output, re.DOTALL)
            if not match:
                raise ValueError("No JSON object found in response.")
                
            clean_json_str = match.group(0).strip()
            parsed_map = json.loads(clean_json_str)
        except Exception as e:
            logger.error(f"Error parsing DeepSeek JSON: {e}")
            logger.error(f"Raw output was: {json_output}")
            raise Exception("Failed to parse campaign JSON from AI.")

        # 5. Persist to Neon Postgres DB
        pillar_kw = parsed_map.get("pillar", {}).get("keyword", seed_topic)
        
        campaign = ContentCampaign(
            profile_name=profile_name,
            seed_topic=seed_topic,
            pillar_keyword=pillar_kw,
            spoke_keywords_json=json.dumps(parsed_map)  # Store whole map for easy retrieval
        )
        self.db = ensure_db_alive(self.db)
        self.db.add(campaign)
        self.db.commit()
        self.db.refresh(campaign)
        
        # 6. Return standard schema response
        pillar_obj = PillarKeyword(**parsed_map.get("pillar", {"keyword": pillar_kw, "kd": 0, "vol": 0}))
        spokes_list = [SpokeKeyword(**s) for s in parsed_map.get("spokes", [])]
        
        return CampaignResponse(
            id=campaign.id,
            profile_name=campaign.profile_name,
            seed_topic=campaign.seed_topic,
            pillar=pillar_obj,
            spokes=spokes_list,
            created_at=campaign.created_at
        )

    async def _fetch_dataforseo_keywords(self, seed_topic: str) -> list:
        url = "https://api.dataforseo.com/v3/dataforseo_labs/google/keyword_ideas/live"
        payload = [{
            "keywords": [seed_topic],
            "location_name": "United States",
            "language_name": "English",
            "limit": 700,
            "include_serp_info": False
        }]
        
        auth = httpx.BasicAuth(username=DATAFORSEO_LOGIN, password=DATAFORSEO_PASSWORD)
        
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, auth=auth, timeout=CARTOGRAPHER_TIMEOUT)
            response.raise_for_status()
            data = response.json()
            
            try:
                # Navigate DataForSEO's nested response structure
                items = data["tasks"][0]["result"][0]["items"]
                return items
            except (KeyError, IndexError):
                logger.error(f"Unexpected DataForSEO response: {data}")
                return []

    async def _call_deepseek_reasoner(self, seed_topic: str, keyword_data: list, niche_context: str) -> str:
        url = "https://api.deepseek.com/chat/completions"
        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        }
        
        data_str = json.dumps(keyword_data)
        safe_seed = sanitize_prompt_input(seed_topic, max_chars=200, tag="seed_topic")
        safe_context = sanitize_prompt_input(niche_context, max_chars=500, tag="niche_context") if niche_context else ""

        prompt = f"""You are an Elite Enterprise SEO Strategist.
Context/Target Audience: {safe_context}
Seed Topic: {safe_seed}
Raw Keyword Data: {data_str}

Your goal is to build a high-converting, hyper-relevant 'Hub and Spoke' Topical Authority map. 

CRITICAL FILTERING RULES: You MUST ruthlessly discard any keywords from the raw data that match these criteria:
1. Job-seeking or academic (e.g., 'salary', 'jobs', 'resume', 'course', 'degree')
2. Navigational/Login (e.g., 'login', 'support', 'customer service')
3. Competitor-branded (unless doing a specific VS comparison)
4. Completely irrelevant to the 'Context/Target Audience' provided above.

CRITICAL: If out of the 700 keywords provided, only 2 actually match the target audience/niche, return ONLY 2 spokes. DO NOT force 10 spokes if it means including irrelevant, broad, or job/login-related keywords. Returning generic keywords just to fill space is a critical failure.

If the raw data is full of garbage, pick ONLY the absolute best keywords. It is better to return 4 highly relevant spokes than 10 garbage ones.

Select 1 broad, high-volume 'Pillar' keyword.
Select up to 10 'Spoke' keywords that: 1) Have KD < 45, 2) Do not cannibalize each other, 3) Cover different buyer journey stages, and 4) Strictly align with the target audience.

Output ONLY a strict JSON object:
{{"pillar": {{"keyword": "...", "kd": X, "vol": Y}}, "spokes": [{{"keyword": "...", "kd": X, "vol": Y, "intent": "Informational/Commercial", "angle": "Brief 1-sentence content angle"}}]}}"""
        
        payload = {
            "model": DEEPSEEK_REASONER_MODEL,
            "messages": [
                {"role": "system", "content": "You are a precise JSON-generating SEO architect. You never output conversational text, only strict JSON."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.5
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers, timeout=CARTOGRAPHER_TIMEOUT)
            response.raise_for_status()
            result = response.json()
            
            # Deepseek returns reasoning first in "reasoning_content" then the "content"
            content = result["choices"][0]["message"]["content"]
            return content
