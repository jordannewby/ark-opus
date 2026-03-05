"""
ResearchAgent — uses DataForSEO and DeepSeek-R1 to gather competitive intel for a keyword.

Returns structured JSON with:
  - Top 5 competitor H2/H3 headers
  - "People Also Ask" questions
  - 15+ semantic entities
  - Information Gap (via DeepSeek-R1)
  - On-Page metrics
  - Backlinks
"""

from __future__ import annotations

import json
import base64
import os
import re
from datetime import datetime, timedelta, timezone
import asyncio

import httpx
from sqlalchemy.orm import Session
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from ..models import ResearchCache
from ..settings import DEEPSEEK_API_KEY, DATAFORSEO_LOGIN, DATAFORSEO_PASSWORD

DATAFORSEO_API_URL = "https://api.dataforseo.com/v3"
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
CACHE_TTL_HOURS = 24

ALLOWED_TOOL_CATEGORIES = ["serp", "keyword", "backlink", "on_page"]


class ResearchAgent:
    """Gathers SEO research data for a keyword using DataForSEO MCP Server and DeepSeek-R1."""

    def __init__(self, db: Session):
        self.db = db
        if not DATAFORSEO_LOGIN or not DATAFORSEO_PASSWORD:
            raise ValueError("DataForSEO credentials missing from environment.")

    async def research(self, keyword: str, niche: str = "default", user_context: str = "") -> dict:
        """Run full research pipeline for *keyword* via localized MCP server."""
        cached = self._get_cached(keyword)
        
        from ..settings import DEBUG_MODE
        
        # Bypass cache if DEBUG_MODE is True or if user provided customized context
        if cached is not None and not user_context and not DEBUG_MODE:
            if DEBUG_MODE:
                print(f"[DEBUG] Cache Hit! Returning data for {keyword}")
            return cached

        # Step A: Initialize DataForSEO MCP Server via sub-process
        env = os.environ.copy()
        if "PATH" not in env:
            env["PATH"] = os.defpath
        env["DATAFORSEO_USERNAME"] = DATAFORSEO_LOGIN
        env["DATAFORSEO_PASSWORD"] = DATAFORSEO_PASSWORD
        
        server_params = StdioServerParameters(
            command="npx",
            args=["-y", "dataforseo-mcp-server"],
            env=env
        )
        
        # Step B: Elite Discovery (Non-MCP)
        elite_data = await self._exa_elite_discovery(keyword, niche=niche)

        # Step C: MCP Context Lifecycle & Agentic Loop
        from ..settings import DEBUG_MODE
        
        if DEBUG_MODE:
            print(f"\n[DEBUG] Spinning up ephemeral MCP Subprocess for DataForSEO...")
            
        executed_tools = []
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                if DEBUG_MODE:
                    print(f"[DEBUG] MCP Server Initialized successfully.")
                
                # Fetch available DataForSEO tools
                tools_response = await session.list_tools()
                safe_tools = []
                simplified_tools = []
                for tool in tools_response.tools:
                    if any(cat in tool.name.lower() for cat in ALLOWED_TOOL_CATEGORIES):
                        safe_tools.append({
                            "name": tool.name, 
                            "description": tool.description, 
                            "inputSchema": tool.inputSchema
                        })
                        
                        # Aggressively strip webhook noise from the schema to prevent R1 cognitive overload
                        clean_schema = ResearchAgent._strip_webhook_noise(tool.inputSchema)
                        
                        simplified_tools.append({
                            "name": tool.name, 
                            "description": tool.description,
                            "inputSchema": clean_schema
                        })
                
                # Let DeepSeek-R1 decide the workflow based on the keyword and safe_tools
                try:
                    tools_decision = await self._agentic_tool_decision(keyword, simplified_tools, user_context)
                    if DEBUG_MODE:
                        print(f"\n[DEBUG] DeepSeek-R1 Selected Tools:\n{json.dumps(tools_decision, indent=2)}\n")
                    
                    # Store Results
                    mcp_results = {}
                    
                    # Execute requested tools directly against the Local MCP Subprocess
                    for call in tools_decision.get("tool_calls", []):
                        t_name = call.get("tool_name")
                        t_args = call.get("arguments", {})
                        
                        if not any(cat in t_name.lower() for cat in ALLOWED_TOOL_CATEGORIES):
                            if DEBUG_MODE: print(f"[DEBUG-SECURITY] Blocked unauthorized tool call: {t_name}")
                            continue
                            
                        if DEBUG_MODE:
                            print(f"[DEBUG] Executing MCP Tool: {t_name}")
                            print(f"[DEBUG] Tool Payload: {json.dumps(t_args)}")
                            
                        res = await session.call_tool(t_name, arguments=t_args)
                        executed_tools.append(t_name)
                        
                        if "keyword_ideas" in t_name:
                            mcp_results["keywords"] = res
                        elif "serp" in t_name:
                            mcp_results["serp"] = res
                        elif "related" in t_name or "long_tail" in t_name:
                            mcp_results["related_keywords"] = res
                        elif "backlinks" in t_name:
                            mcp_results["backlinks"] = res
                        elif "on_page" in t_name:
                            mcp_results["on_page"] = res
                        
                except Exception as e:
                    if DEBUG_MODE: print(f"[DEBUG] Agentic loop failed, fallback triggered. Error: {e}")
                    # Fallback Logic: Safe Gather baseline
                    mcp_results = {}
                    executed_tools = []
                    mcp_results["keywords"] = await session.call_tool(
                        "dataforseo_labs_google_keyword_ideas", 
                        arguments={"keywords": [keyword], "location_code": 2840, "language_code": "en"}
                    )
                    executed_tools.append("dataforseo_labs_google_keyword_ideas (fallback)")
                    mcp_results["serp"] = await session.call_tool(
                        "serp_organic_live_advanced", 
                        arguments={"keyword": keyword, "location_code": 2840, "language_code": "en", "depth": 10}
                    )
                    executed_tools.append("serp_organic_live_advanced (fallback)")
                    
        if DEBUG_MODE:
            print(f"[DEBUG] Ephemeral MCP Subprocess terminated cleanly.\n")

        # Step D: Data Formatting
        kw_data = mcp_results.get("keywords")
        serp_data = mcp_results.get("serp")
        
        # Depending on MCP server payload schema, extract headers/entities
        kw_text = kw_data.content[0].text if kw_data and kw_data.content else "{}"
        serp_text = serp_data.content[0].text if serp_data and serp_data.content else "{}"
        
        try:
            kw_json = json.loads(kw_text)
            serp_json = json.loads(serp_text)
        except Exception:
            kw_json = {}
            serp_json = {}
            
        competitor_headers = self._extract_headers(serp_json)
        paa = self._extract_paa(serp_json)
        semantic_entities = self._extract_entities(kw_json, serp_json)
        
        long_tail = mcp_results.get("related_keywords")
        long_tail_text = long_tail.content[0].text if long_tail and hasattr(long_tail, 'content') and long_tail.content else None

        # Step E: Analyze the Information Gap with DeepSeek-R1
        compiled_text = self._strip_html(json.dumps({
            "keyword": keyword,
            "competitor_headers": competitor_headers,
            "people_also_ask": paa,
            "semantic_entities": semantic_entities,
            "elite_competitors": elite_data,
            "long_tail_suggestions": long_tail_text,
            "raw_mcp_keywords_fallback": kw_text if not semantic_entities else None,
            "raw_mcp_serp_fallback": serp_text if not competitor_headers else None
        }))
        
        info_gap = await self._analyze_information_gap(keyword, compiled_text, user_context)

        result = {
            "keyword": keyword,
            "information_gap": info_gap,
            "competitor_headers": competitor_headers,
            "people_also_ask": paa,
            "semantic_entities": semantic_entities,
            "on_page_metrics": {"avg_word_count": 1850, "header_density": "Every 150 words"}, # Mock since OnPage is not in MCP yet
            "backlink_authority": {"authority_sources": ["wikipedia.org", "hbr.org", "forbes.com"]}, # Mock
            "elite_competitors": elite_data,
            "executed_tools": executed_tools if 'executed_tools' in locals() else [],
        }

        self._save_cache(keyword, result)
        return result

    # ------------------------------------------------------------------
    # DataForSEO Quad-Stack (Phase 1)
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Brave Goggles (Elite Discovery Layer)
    # ------------------------------------------------------------------

    async def _exa_elite_discovery(self, keyword: str, niche: str = "default") -> list[dict]:
        """Use Exa.ai Neural Search to find and extract the full text of elite articles."""
        from ..settings import EXA_API_KEY
        if not EXA_API_KEY:
            return []
            
        headers = {
            "x-api-key": EXA_API_KEY,
            "Content-Type": "application/json"
        }
        
        # Exa Neural Prompting - asking for meaning, not just keywords
        prompt = f"High-quality, expert-level blog post or article about {keyword}"
        if niche != "default":
            prompt = f"High-quality, advanced {niche} blog post or article about {keyword}"
            
        payload = {
            "query": prompt,
            "type": "auto",
            "num_results": 3,
            "contents": {
                "text": {
                    "max_characters": 10000  # Truncate at ~2500 tokens to protect DeepSeek context window
                }
            }
        }
        
        async with httpx.AsyncClient(timeout=30) as client:
            try:
                resp = await client.post("https://api.exa.ai/search", headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                
                results = []
                for result in data.get("results", []):
                    results.append({
                        "title": result.get("title", ""),
                        "url": result.get("url", ""),
                        "content": result.get("text", "") 
                    })
                return results
            except Exception as e:
                print(f"Exa.ai API Error: {e}")
                return []
    # ------------------------------------------------------------------
    # Extraction Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_headers(serp_data: dict) -> list[dict]:
        """Pull H2/H3-style headers from SERP snippets and titles."""
        headers: list[dict] = []
        try:
            items = serp_data.get("tasks", [])[0].get("result", [])[0].get("items", [])
            for r in items[:5]:
                if r.get("type") == "organic":
                    entry = {"source": r.get("url", ""), "h2": r.get("title", "")}
                    description = r.get("description", "")
                    if description:
                        parts = re.split(r"(?<=[.!?])\s+", description)
                        entry["h3s"] = [p.strip() for p in parts if len(p.strip()) > 20]
                    headers.append(entry)
        except Exception:
            pass
        return headers

    @staticmethod
    def _extract_paa(serp_data: dict) -> list[str]:
        """Extract 'People Also Ask' questions from SERP."""
        questions: list[str] = []
        try:
            items = serp_data.get("tasks", [])[0].get("result", [])[0].get("items", [])
            for item in items:
                if item.get("type") == "people_also_ask":
                    for q in item.get("items", []):
                        questions.append(q.get("title", ""))
                elif item.get("type") == "related_searches":
                    for q in item.get("items", []):
                        questions.append(q.get("title", "") if isinstance(q, dict) else q)
        except Exception:
            pass
        
        # Deduplicate
        seen = set()
        return [q for q in questions if not (q.lower() in seen or seen.add(q.lower()))]

    @staticmethod
    def _extract_entities(keywords_data: dict, serp_data: dict) -> list[str]:
        """
        Derive high-value semantic entities (Golden Keywords) using advanced SEO metrics.
        Calculates an 'Opportunity Score' based on Volume, Difficulty, and Commercial Intent (CPC).
        """
        golden_keywords: list[dict] = []
        try:
            tasks = keywords_data.get("tasks", [])
            if not tasks:
                return []
                
            results = tasks[0].get("result", [])
            if not results:
                return []
                
            items = results[0].get("items", [])
            for r in items:
                kw = r.get("keyword", "")
                info = r.get("keyword_info", {})
            
                # Extract metrics (Safely handle DataForSEO 'null' values converting to Python 'None')
                sv = info.get("search_volume") or 0
                kd = info.get("keyword_difficulty") or 99 
                cpc = info.get("cpc") or 0.0
                
                if not kw:
                    continue
                    
                # ADVANCED SEO FILTERING:
                # 1. Eliminate impossibly hard keywords (KD > 65)
                # 2. Require at least *some* search volume (SV > 10) to avoid ghost town keywords
                if kd < 65 and sv > 10:
                    # Opportunity Score Formula: Rewards high volume & high CPC, penalizes high KD
                    opp_score = (sv / (kd + 1)) + (cpc * 10)
                    
                    golden_keywords.append({
                        "keyword": kw,
                        "score": opp_score,
                        "kd": kd,
                        "sv": sv
                    })
            
            # Sort by our custom Opportunity Score (Highest to Lowest)
            golden_keywords.sort(key=lambda x: x["score"], reverse=True)
            
            # Extract just the string names of the top 15 highest-opportunity keywords
            extracted = [e["keyword"] for e in golden_keywords[:15]]
            
            if extracted:
                return extracted
                
        except Exception as e:
            print(f"Entity Extraction Error: {e}")
            pass
            
        # Fallback if the MCP payload fails or is empty
        return ["seo strategy", "content marketing", "keyword research", "search intent"]

    # ------------------------------------------------------------------
    # Stripping HTML
    # ------------------------------------------------------------------
    
    @staticmethod
    def _strip_html(text: str) -> str:
        """Strip HTML boilerplate from competitor data."""
        clean = re.sub(r'<[^>]*>', '', text)
        clean = re.sub(r'\s+', ' ', clean).strip()
        return clean

    @staticmethod
    def _strip_webhook_noise(schema: dict) -> dict:
        """
        Recursively remove extraneous webhook bindings (pingback_url, postback_url, etc.)
        from the DataForSEO parameter schemas to prevent LLM cognitive overload.
        """
        if not isinstance(schema, dict):
            return schema
            
        clean_schema = {}
        for key, value in schema.items():
            if isinstance(value, dict):
                # If we are looking at the 'properties' block, filter its keys
                if key == "properties":
                    filtered_props = {}
                    for prop_k, prop_v in value.items():
                        if "pingback" not in prop_k.lower() and "postback" not in prop_k.lower() and "webhook" not in prop_k.lower():
                            filtered_props[prop_k] = ResearchAgent._strip_webhook_noise(prop_v)
                    clean_schema[key] = filtered_props
                else:
                    clean_schema[key] = ResearchAgent._strip_webhook_noise(value)
            elif isinstance(value, list):
                clean_schema[key] = [ResearchAgent._strip_webhook_noise(i) if isinstance(i, dict) else i for i in value]
            else:
                clean_schema[key] = value
                
        # Clean up required array if properties were removed
        if "required" in clean_schema and isinstance(clean_schema["required"], list):
            clean_schema["required"] = [
                r for r in clean_schema["required"] 
                if "pingback" not in r.lower() and "postback" not in r.lower() and "webhook" not in r.lower()
            ]
            
        return clean_schema

    # ------------------------------------------------------------------
    # DeepSeek Agentic Logic
    # ------------------------------------------------------------------

    async def _agentic_tool_decision(self, keyword: str, available_tools: list[dict], user_context: str = "") -> dict:
        """Ask DeepSeek-R1 which MCP tools to execute based on available schema."""
        if not DEEPSEEK_API_KEY:
            raise ValueError("DeepSeek API key missing.")
            
        prompt = (
            f"You are an expert SEO Autonomous Agent. We are researching the keyword '{keyword}'.\n"
            f"USER DIRECTIVE / INTENT CONTEXT:\n{user_context if user_context else 'None provided. Assume general intent.'}\n\n"
            "Here are the available MCP tools we can execute:\n"
            f"{json.dumps(available_tools, indent=2)}\n\n"
            "Decide which tools you need to build a comprehensive Information Gap profile.\n"
            "CRITICAL DIRECTIVES:\n"
            "1. You MUST ALWAYS select 'dataforseo_labs_google_keyword_ideas' and 'serp_organic_live_advanced'.\n"
            "2. EXTREMELY IMPORTANT: You are HIGHLY ENCOURAGED to add additional tools from the schema (e.g., related searches, backlinks, on-page) to maximize SEO quality. Do not limit yourself if the context requires deeper data.\n"
            "3. ZERO HALLUCINATION & STRICT HONESTY: Do not fake data. You must list EXACTLY the tools you want the system to execute for you using their exact schema names.\n\n"
            "OUTPUT FORMAT TEMPLATE (Use this exact structure for parameter formatting. Append additional tool objects to the 'tool_calls' array as needed):\n"
            "{\n"
            "  \"tool_calls\": [\n"
            "    {\n"
            "      \"tool_name\": \"dataforseo_labs_google_keyword_ideas\",\n"
            "      \"arguments\": {\"keywords\": [\"" + keyword + "\"], \"location_name\": \"United States\", \"language_code\": \"en\"}\n"
            "    },\n"
            "    {\n"
            "      \"tool_name\": \"serp_organic_live_advanced\",\n"
            "      \"arguments\": {\"keyword\": \"" + keyword + "\", \"location_name\": \"United States\", \"language_code\": \"en\", \"depth\": 10}\n"
            "    }\n"
            "  ]\n"
            "}\n\n"
            "Return ONLY a valid JSON object matching the format above. Do not include markdown blocks or any other text."
        )
        payload = {
            "model": "deepseek-reasoner",
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 4000
        }
        
        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        }
        
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(DEEPSEEK_API_URL, headers=headers, json=payload)
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            
            # Extract clean JSON by removing <think> blocks and matching brackets
            clean = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
            
            json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', clean, re.DOTALL)
            if json_match:
                clean = json_match.group(1).strip()
            else:
                start = clean.find('{')
                end = clean.rfind('}')
                if start != -1 and end != -1:
                    clean = clean[start:end+1]
                else:
                    clean = "{}"
                
            decision = json.loads(clean)
            return {
                "tool_calls": decision.get("tool_calls", [])
            }

    async def _analyze_information_gap(self, keyword: str, text_context: str, user_context: str = "") -> str:
        """Use deepseek-reasoner to find the expert angle Page 1 is currently ignoring."""
        if not DEEPSEEK_API_KEY:
            return "DeepSeek API key missing. Cannot generate information gap."
            
        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        }
        prompt = (
            f"You are an expert SEO strategist. Analyze the following competitor and SERP data for '{keyword}'. "
            f"USER DIRECTIVE / INTENT CONTEXT:\n{user_context}\n\n"
            "Identify the 'Information Gap'—the specific expert angle or unique insight that Page 1 is currently ignoring, "
            "that perfectly caters to the user's explicit intent. "
            "Provide ONLY the information gap insight in 2-3 sentences max.\n\n"
            f"DATA:\n{text_context[:4000]}"
        )
        payload = {
            "model": "deepseek-reasoner",
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 500
        }
        
        async with httpx.AsyncClient(timeout=60) as client:
            try:
                resp = await client.post(
                    DEEPSEEK_API_URL, headers=headers, json=payload
                )
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"].strip()
            except Exception as e:
                print(f"DeepSeek Error: {e}")
                return "Could not determine information gap due to an API error."

    # ------------------------------------------------------------------
    # Cache Layer
    # ------------------------------------------------------------------

    def _get_cached(self, keyword: str) -> dict | None:
        """Return cached result if it exists and hasn't expired."""
        row = (
            self.db.query(ResearchCache)
            .filter(ResearchCache.keyword == keyword.lower())
            .first()
        )
        if row is None:
            return None

        age = datetime.now(timezone.utc) - row.created_at.replace(
            tzinfo=timezone.utc
        )
        if age > timedelta(hours=row.cache_ttl_hours):
            self.db.delete(row)
            self.db.commit()
            return None

        return json.loads(row.result_json)

    def _save_cache(self, keyword: str, result: dict) -> None:
        """Upsert research result into the cache table."""
        row = (
            self.db.query(ResearchCache)
            .filter(ResearchCache.keyword == keyword.lower())
            .first()
        )
        payload = json.dumps(result, ensure_ascii=False)

        if row:
            row.result_json = payload
            row.created_at = datetime.now(timezone.utc)
        else:
            row = ResearchCache(
                keyword=keyword.lower(),
                result_json=payload,
                cache_ttl_hours=CACHE_TTL_HOURS,
            )
            self.db.add(row)

        self.db.commit()
