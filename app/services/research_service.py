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

from ..models import ResearchCache, NichePlaybook, ResearchRun
from ..settings import DEEPSEEK_API_KEY, DATAFORSEO_LOGIN, DATAFORSEO_PASSWORD

DATAFORSEO_API_URL = "https://api.dataforseo.com/v3"
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
CACHE_TTL_HOURS = 24

ALLOWED_TOOL_CATEGORIES = ["serp", "keyword", "backlink", "on_page"]

# Native Exa tools injected alongside MCP tools into DeepSeek-R1's tool array
EXA_NATIVE_TOOLS = [
    {
        "name": "exa_scout_search",
        "description": "Search the web for high-authority articles using Exa.ai Neural Search. Returns lightweight results (id, title, url, snippet). Use this iteratively with different queries if initial results are poor quality.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "A natural language search query describing the type of article you want to find."}
            },
            "required": ["query"]
        }
    },
    {
        "name": "exa_extract_full_text",
        "description": "Fetch the full body text of articles discovered by exa_scout_search. Use this ONCE after you have found optimal URLs. Pass the article IDs from a previous scout_search result.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ids": {"type": "array", "items": {"type": "string"}, "description": "List of article IDs from a previous exa_scout_search result."}
            },
            "required": ["ids"]
        }
    }
]

NATIVE_TOOL_NAMES = {t["name"] for t in EXA_NATIVE_TOOLS}


class ResearchAgent:
    """Gathers SEO research data for a keyword using DataForSEO MCP Server and DeepSeek-R1."""

    def __init__(self, db: Session):
        self.db = db
        if not DATAFORSEO_LOGIN or not DATAFORSEO_PASSWORD:
            raise ValueError("DataForSEO credentials missing from environment.")

    async def research(self, keyword: str, niche: str = "default", user_context: str = "", profile_name: str = "default", mcp_session=None) -> dict:
        """Run full research pipeline for *keyword* via localized MCP server."""
        niche = niche.strip().lower().replace(" ", "-") if niche and niche != "default" else "default"
        cached = self._get_cached(keyword, profile_name, niche)
        
        from ..settings import DEBUG_MODE
        
        # Bypass cache if DEBUG_MODE is True or if user provided customized context
        if cached is not None and not user_context and not DEBUG_MODE:
            if DEBUG_MODE:
                print(f"[DEBUG] Cache Hit! Returning data for {keyword}")
            return cached
        
        # Step B: Exa discovery is now handled by R1 via native tools (Scout & Extract)
        exa_results = []

        # Step C: MCP Context Lifecycle & Agentic Loop
        from ..settings import DEBUG_MODE
        
        if DEBUG_MODE:
            print(f"\n[DEBUG] Using global persistent MCP Session...")
            
        executed_tools = []
        exa_queries_log: list[str] = []
        
        # We use a dummy context to avoid a massive 200-line git diff of indentation
        from contextlib import asynccontextmanager
        @asynccontextmanager
        async def dummy_context():
            yield mcp_session
            
        async with dummy_context() as _:
            async with dummy_context() as session:
                if not session:
                    raise ValueError("Global MCP Session not initialized")
                if DEBUG_MODE:
                    print(f"[DEBUG] MCP Session attached successfully.")
                
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
                
                # Inject native Exa tools alongside MCP tools
                all_tools = simplified_tools + EXA_NATIVE_TOOLS
                
                # Build set of all valid tool names for hallucination detection
                valid_mcp_names = {t["name"] for t in simplified_tools}
                
                # ================================================================
                # ITERATIVE AGENTIC TOOL LOOP (Scout & Extract Architecture)
                # R1 selects tools, we execute, feed results back. Max 5 iterations.
                # ================================================================
                mcp_results = {}
                info_gap_from_loop = None
                MAX_ITERATIONS = 5
                iteration_count = 0

                niche_intel = self._get_niche_playbook(niche, profile_name)

                try:
                    messages = [{
                        "role": "user",
                        "content": self._build_agentic_prompt(keyword, all_tools, user_context, niche, niche_intel)
                    }]

                    for loop_count in range(MAX_ITERATIONS):
                        iteration_count += 1
                        if DEBUG_MODE:
                            print(f"\n[DEBUG] === R1 Agentic Loop: Iteration {loop_count + 1}/{MAX_ITERATIONS} ===")
                        
                        # Call DeepSeek-R1
                        r1_response = await self._call_deepseek_r1(messages)

                        if DEBUG_MODE:
                            # Show first 500 chars of R1's raw response to diagnose tool skipping
                            print(f"[DEBUG] R1 raw response (first 500 chars): {r1_response[:500]}")

                        # Parse the response for tool_calls vs final analysis
                        parsed = self._parse_r1_response(r1_response)
                        tool_calls = parsed.get("tool_calls", [])
                        
                        # If R1 returned an information_gap, it's done researching
                        if parsed.get("information_gap"):
                            # Capture full expanded research output (unique_angles, competitor_weaknesses, etc.)
                            if any(k in parsed for k in ["unique_angles", "competitor_weaknesses", "data_points", "practitioner_insights"]):
                                info_gap_from_loop = parsed  # Full dict with all fields
                            else:
                                info_gap_from_loop = parsed["information_gap"]  # Legacy string format
                            if DEBUG_MODE:
                                print(f"[DEBUG] R1 produced Information Gap. Exiting loop.")
                            break
                        
                        # If no tool_calls and no info_gap, R1 is confused — force final output
                        if not tool_calls:
                            if DEBUG_MODE:
                                print(f"[DEBUG] R1 returned no tool_calls and no info_gap. Forcing final output.")
                            messages.append({"role": "assistant", "content": r1_response})
                            messages.append({"role": "user", "content": (
                                "You did not request any tools or provide an information_gap. "
                                "Please output your final analysis NOW using the data you have. "
                                "Return JSON with an 'information_gap' key."
                            )})
                            continue
                        
                        # Append R1's response to history
                        messages.append({"role": "assistant", "content": r1_response})
                        
                        # Execute each tool call with three-way routing
                        tool_results_text = []
                        for call in tool_calls:
                            t_name = call.get("tool_name", "")
                            t_args = call.get("arguments", {})
                            
                            if t_name in NATIVE_TOOL_NAMES:
                                # --- Route A: Native Exa Tool ---
                                if DEBUG_MODE:
                                    print(f"[DEBUG] Executing Native Tool: {t_name}")
                                try:
                                    if t_name == "exa_scout_search":
                                        exa_queries_log.append(t_args.get("query", keyword))
                                        native_result = await self.exa_scout_search(t_args.get("query", keyword))
                                        tool_results_text.append(
                                            f"TOOL RESULT [{t_name}]:\n{json.dumps(native_result, indent=2)}"
                                        )
                                    elif t_name == "exa_extract_full_text":
                                        native_result = await self.exa_extract_full_text(t_args.get("ids", []))
                                        # Store extracted articles for the final result
                                        exa_results.extend(native_result)
                                        tool_results_text.append(
                                            f"TOOL RESULT [{t_name}]:\n{json.dumps(native_result, indent=2)}"
                                        )
                                    executed_tools.append(t_name)
                                except Exception as te:
                                    tool_results_text.append(
                                        f"TOOL RESULT [{t_name}]: ERROR — {str(te)}"
                                    )
                                    
                            elif t_name in valid_mcp_names:
                                # --- Route B: Valid MCP Tool ---
                                if not any(cat in t_name.lower() for cat in ALLOWED_TOOL_CATEGORIES):
                                    if DEBUG_MODE:
                                        print(f"[DEBUG-SECURITY] Blocked unauthorized MCP tool: {t_name}")
                                    tool_results_text.append(
                                        f"TOOL RESULT [{t_name}]: BLOCKED — Tool category not authorized."
                                    )
                                    continue
                                    
                                if DEBUG_MODE:
                                    print(f"[DEBUG] Executing MCP Tool: {t_name}")
                                
                                try:
                                    res = await session.call_tool(t_name, arguments=t_args)
                                    executed_tools.append(t_name)
                                    
                                    # Store MCP results in the standard buckets
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
                                    
                                    # Feed truncated result back to R1
                                    res_text = res.content[0].text if res and res.content else "{}"
                                    tool_results_text.append(
                                        f"TOOL RESULT [{t_name}]:\n{res_text[:4000]}"
                                    )
                                except Exception as te:
                                    tool_results_text.append(
                                        f"TOOL RESULT [{t_name}]: ERROR — {str(te)}"
                                    )
                            else:
                                # --- Route C: Hallucinated Tool ---
                                if DEBUG_MODE:
                                    print(f"[DEBUG-HALLUCINATION] R1 called non-existent tool: {t_name}")
                                tool_results_text.append(
                                    f"TOOL RESULT [{t_name}]: ERROR — Tool '{t_name}' does not exist. "
                                    f"Please evaluate your strategy and use only the provided tools."
                                )
                        
                        # Feed all tool results back to R1 for next iteration
                        combined_results = "\n\n".join(tool_results_text)
                        messages.append({"role": "user", "content": (
                            f"Here are the results from your requested tools:\n\n{combined_results}\n\n"
                            "Analyze these results. You may request more tools if needed, or if you have "
                            "enough data, output your FINAL analysis as JSON with an 'information_gap' key "
                            "containing 2-3 sentences about what Page 1 competitors are missing."
                        )})
                    
                    # Circuit Breaker: If we exhausted all iterations without an info_gap
                    if not info_gap_from_loop:
                        if DEBUG_MODE:
                            print(f"[DEBUG] Circuit breaker hit ({MAX_ITERATIONS} iterations). Forcing final output.")
                        messages.append({"role": "user", "content": (
                            f"CIRCUIT BREAKER: You have used {MAX_ITERATIONS} iterations. "
                            "You MUST return your final analysis NOW. Output JSON with an 'information_gap' key."
                        )})
                        final_response = await self._call_deepseek_r1(messages)
                        final_parsed = self._parse_r1_response(final_response)
                        info_gap_from_loop = final_parsed.get("information_gap", final_response[:500])
                    
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
        semantic_entities, golden_kw_stats = self._extract_entities_with_stats(kw_json, serp_json)
        
        long_tail = mcp_results.get("related_keywords")
        long_tail_text = long_tail.content[0].text if long_tail and hasattr(long_tail, 'content') and long_tail.content else None

        # Step E: Use Information Gap from iterative loop, or fallback to dedicated analysis
        # R1 now returns an expanded dict with multiple keys, not just a string
        if info_gap_from_loop:
            # Try to parse as JSON if it's a string (R1 sometimes returns stringified JSON)
            if isinstance(info_gap_from_loop, str):
                try:
                    parsed_gap = json.loads(info_gap_from_loop)
                    if isinstance(parsed_gap, dict) and "information_gap" in parsed_gap:
                        info_gap_from_loop = parsed_gap
                except (json.JSONDecodeError, TypeError):
                    pass  # It's a plain string, that's fine
            info_gap = info_gap_from_loop  # Will be unpacked in the result dict construction
        else:
            compiled_text = self._strip_html(json.dumps({
                "keyword": keyword,
                "competitor_headers": competitor_headers,
                "people_also_ask": paa,
                "semantic_entities": semantic_entities,
                "elite_competitors": exa_results,
                "long_tail_suggestions": long_tail_text,
                "raw_mcp_keywords_fallback": kw_text if not semantic_entities else None,
                "raw_mcp_serp_fallback": serp_text if not competitor_headers else None
            }))
            info_gap = await self._analyze_information_gap(keyword, compiled_text, user_context)

        # Extract real on_page and backlink data from MCP results (if R1 gathered them)
        on_page_data = mcp_results.get("on_page")
        on_page_text = on_page_data.content[0].text if on_page_data and hasattr(on_page_data, 'content') and on_page_data.content else None
        real_on_page = {}
        if on_page_text:
            try:
                real_on_page = json.loads(on_page_text)
            except Exception:
                real_on_page = {"raw": on_page_text[:2000]}

        backlink_data = mcp_results.get("backlinks")
        backlink_text = backlink_data.content[0].text if backlink_data and hasattr(backlink_data, 'content') and backlink_data.content else None
        real_backlinks = {}
        if backlink_text:
            try:
                real_backlinks = json.loads(backlink_text)
            except Exception:
                real_backlinks = {"raw": backlink_text[:2000]}

        # Parse expanded info gap fields from R1's final output
        unique_angles = []
        competitor_weaknesses = []
        data_points = []
        practitioner_insights = []
        if isinstance(info_gap, dict):
            # R1 returned the new expanded format
            unique_angles = info_gap.get("unique_angles", [])
            competitor_weaknesses = info_gap.get("competitor_weaknesses", [])
            data_points = info_gap.get("data_points", [])
            practitioner_insights = info_gap.get("practitioner_insights", [])
            info_gap = info_gap.get("information_gap", str(info_gap))

        result = {
            "keyword": keyword,
            "information_gap": info_gap,
            "unique_angles": unique_angles,
            "competitor_weaknesses": competitor_weaknesses,
            "data_points": data_points,
            "practitioner_insights": practitioner_insights,
            "competitor_headers": competitor_headers,
            "people_also_ask": paa,
            "semantic_entities": semantic_entities,
            "on_page_metrics": real_on_page if real_on_page else {"note": "on_page tool not used this run"},
            "backlink_authority": real_backlinks if real_backlinks else {"note": "backlink tool not used this run"},
            "elite_competitors": exa_results,
            "executed_tools": executed_tools if 'executed_tools' in locals() else [],
        }

        self._save_cache(keyword, profile_name, niche, result)

        run_id = await self._capture_run_telemetry(
            keyword=keyword,
            niche=niche,
            profile_name=profile_name,
            executed_tools=executed_tools if 'executed_tools' in locals() else [],
            iteration_count=iteration_count if 'iteration_count' in locals() else 1,
            exa_queries=exa_queries_log,
            golden_keywords=golden_kw_stats if 'golden_kw_stats' in locals() else [],
            info_gap=info_gap if isinstance(info_gap, str) else "",
            entity_cluster=semantic_entities,
            competitor_count=len(competitor_headers),
        )
        result["research_run_id"] = run_id

        return result

    # ------------------------------------------------------------------
    # DataForSEO Quad-Stack (Phase 1)
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Brave Goggles (Elite Discovery Layer)
    # ------------------------------------------------------------------

    async def _exa_elite_discovery(self, keyword: str, niche: str = "default") -> list[dict]:
        """
        Two-step Full-Text Audit via Exa.ai Neural Search:
        1. Search: Find top 5 elite articles via neural search
        2. Extract: Fetch full article text via get_contents(ids)
        Returns truncated full-text for DeepSeek-R1 Information Gap analysis.
        """
        from ..settings import EXA_API_KEY, DEBUG_MODE
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
        
        async with httpx.AsyncClient(timeout=30) as client:
            try:
                # --- Step 1: Neural Search (discovery only, no inline content) ---
                search_payload = {
                    "query": prompt,
                    "type": "auto",
                    "num_results": 5,
                }
                
                if DEBUG_MODE:
                    print(f"[DEBUG] Exa Step 1: Neural Search for '{keyword}'")
                
                search_resp = await client.post(
                    "https://api.exa.ai/search", headers=headers, json=search_payload
                )
                search_resp.raise_for_status()
                search_data = search_resp.json()
                
                search_results = search_data.get("results", [])
                if not search_results:
                    if DEBUG_MODE:
                        print("[DEBUG] Exa: No search results found.")
                    return []
                
                # Extract IDs for full-text fetch
                result_ids = [r.get("id") for r in search_results if r.get("id")]
                
                if not result_ids:
                    # Fallback: return title/url from search results if no IDs available
                    return [
                        {"title": r.get("title", ""), "url": r.get("url", ""), "content": ""}
                        for r in search_results[:5]
                    ]
                
                if DEBUG_MODE:
                    print(f"[DEBUG] Exa Step 2: Fetching full text for {len(result_ids)} articles")
                
                # --- Step 2: Full-Text Extraction via get_contents ---
                contents_payload = {
                    "ids": result_ids,
                    "text": {
                        "max_characters": 25000  # Generous fetch — full article body
                    }
                }
                
                contents_resp = await client.post(
                    "https://api.exa.ai/contents", headers=headers, json=contents_payload
                )
                contents_resp.raise_for_status()
                contents_data = contents_resp.json()
                
                # --- Step 3: Format & Truncate for DeepSeek-R1 context efficiency ---
                elite_articles = []
                for article in contents_data.get("results", []):
                    full_text = article.get("text", "")
                    elite_articles.append({
                        "title": article.get("title", ""),
                        "url": article.get("url", ""),
                        "content": full_text[:20000]  # Safety cap: ~3,500 words per article
                    })
                
                if DEBUG_MODE:
                    total_chars = sum(len(a["content"]) for a in elite_articles)
                    print(f"[DEBUG] Exa Full-Text Audit complete: {len(elite_articles)} articles, {total_chars} total chars")
                
                return elite_articles
                
            except Exception as e:
                print(f"Exa.ai API Error: {e}")
                return []
    # ------------------------------------------------------------------
    # Native Exa Tool Functions (Scout & Extract)
    # ------------------------------------------------------------------

    async def exa_scout_search(self, query: str) -> list[dict]:
        """
        Native tool: Lightweight Exa.ai neural search.
        Returns only id/title/url/snippet to keep R1 token usage low.
        """
        from ..settings import EXA_API_KEY, DEBUG_MODE
        if not EXA_API_KEY:
            return [{"error": "EXA_API_KEY not configured"}]
        
        headers = {"x-api-key": EXA_API_KEY, "Content-Type": "application/json"}
        payload = {
            "query": query,
            "type": "auto",
            "num_results": 5,
            "use_autoprompt": True
        }
        
        async with httpx.AsyncClient(timeout=30) as client:
            try:
                resp = await client.post("https://api.exa.ai/search", headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                
                results = []
                for r in data.get("results", []):
                    results.append({
                        "id": r.get("id", ""),
                        "title": r.get("title", ""),
                        "url": r.get("url", ""),
                        "snippet": (r.get("text", "") or "")[:300]  # Brief snippet only
                    })
                
                if DEBUG_MODE:
                    print(f"[DEBUG] exa_scout_search: Found {len(results)} results for '{query}'")
                return results
            except Exception as e:
                print(f"Exa Scout Error: {e}")
                return [{"error": str(e)}]

    async def exa_extract_full_text(self, ids: list[str]) -> list[dict]:
        """
        Native tool: Fetch full article body from Exa.ai by IDs.
        Truncates each article to 20,000 chars (~3,500 words).
        """
        from ..settings import EXA_API_KEY, DEBUG_MODE
        if not EXA_API_KEY:
            return [{"error": "EXA_API_KEY not configured"}]
        if not ids:
            return [{"error": "No IDs provided"}]
        
        headers = {"x-api-key": EXA_API_KEY, "Content-Type": "application/json"}
        payload = {
            "ids": ids,
            "text": {"max_characters": 25000}
        }
        
        async with httpx.AsyncClient(timeout=30) as client:
            try:
                resp = await client.post("https://api.exa.ai/contents", headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                
                articles = []
                for article in data.get("results", []):
                    full_text = article.get("text", "")
                    articles.append({
                        "title": article.get("title", ""),
                        "url": article.get("url", ""),
                        "content": full_text[:20000]  # Safety cap: ~3,500 words
                    })
                
                if DEBUG_MODE:
                    total_chars = sum(len(a["content"]) for a in articles)
                    print(f"[DEBUG] exa_extract_full_text: {len(articles)} articles, {total_chars} total chars")
                return articles
            except Exception as e:
                print(f"Exa Extract Error: {e}")
                return [{"error": str(e)}]

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

    @staticmethod
    def _extract_entities_with_stats(kw_data: dict, serp_data: dict) -> tuple[list[str], list[dict]]:
        """Returns (entity_strings, golden_keyword_dicts) — stats needed for telemetry capture."""
        golden_keywords: list[dict] = []
        try:
            tasks = kw_data.get("tasks", [])
            if not tasks:
                return ResearchAgent._extract_entities(kw_data, serp_data), []
            results = tasks[0].get("result", [])
            if not results:
                return ResearchAgent._extract_entities(kw_data, serp_data), []
            items = results[0].get("items", [])
            for r in items:
                kw = r.get("keyword", "")
                info = r.get("keyword_info", {})
                sv = info.get("search_volume") or 0
                kd = info.get("keyword_difficulty") or 99
                cpc = info.get("cpc") or 0.0
                if not kw:
                    continue
                if kd < 65 and sv > 10:
                    opp_score = (sv / (kd + 1)) + (cpc * 10)
                    golden_keywords.append({"keyword": kw, "score": opp_score, "kd": kd, "sv": sv, "cpc": cpc})
            golden_keywords.sort(key=lambda x: x["score"], reverse=True)
            entities = [e["keyword"] for e in golden_keywords[:15]]
            if entities:
                return entities, golden_keywords[:20]
        except Exception:
            pass
        return ResearchAgent._extract_entities(kw_data, serp_data), []

    async def _capture_run_telemetry(
        self,
        keyword: str,
        niche: str,
        profile_name: str,
        executed_tools: list[str],
        iteration_count: int,
        exa_queries: list[str],
        golden_keywords: list[dict],
        info_gap: str,
        entity_cluster: list[str],
        competitor_count: int,
    ) -> int:
        """Store structured telemetry from this research run. Returns ResearchRun.id."""
        import random
        kd_list = [kw["kd"] for kw in golden_keywords if kw.get("kd") is not None]

        run = ResearchRun(
            keyword=keyword,
            niche=niche,
            profile_name=profile_name,
            tool_sequence_json=json.dumps(executed_tools),
            iteration_count=iteration_count,
            exa_queries_json=json.dumps(exa_queries) if exa_queries else None,
            kd_values_json=json.dumps(golden_keywords[:20]) if golden_keywords else None,
            max_kd_used=max(kd_list) if kd_list else None,
            avg_kd=int(sum(kd_list) / len(kd_list)) if kd_list else None,
            entity_cluster_json=json.dumps(entity_cluster[:15]),
            info_gap_text=info_gap[:500] if info_gap else None,
            competitor_count=competitor_count,
        )
        self.db.add(run)
        self.db.commit()

        # Trigger distillation check (fires every 10 undistilled runs per niche)
        from .research_intel_service import ResearchIntelService
        intel = ResearchIntelService(self.db)
        await intel.maybe_distill(niche, profile_name)

        # 5% chance to prune old distilled rows (>90 days) to keep DB lean
        if random.random() < 0.05:
            cutoff = datetime.now(timezone.utc) - timedelta(days=90)
            self.db.query(ResearchRun).filter(
                ResearchRun.is_distilled == True,
                ResearchRun.created_at < cutoff,
            ).delete(synchronize_session=False)
            self.db.commit()

        return run.id

    def _get_niche_playbook(self, niche: str, profile_name: str) -> str | None:
        """Retrieve the distilled playbook for this niche+workspace, formatted as prompt text."""
        playbook_row = (
            self.db.query(NichePlaybook)
            .filter(NichePlaybook.profile_name == profile_name, NichePlaybook.niche == niche)
            .first()
        )
        if playbook_row:
            playbook = json.loads(playbook_row.playbook_json)
            age_note = ""
            if playbook_row.updated_at:
                age_days = (datetime.now(timezone.utc) - playbook_row.updated_at.replace(tzinfo=timezone.utc)).days
                if age_days > 30:
                    age_note = f" (NOTE: Based on data from {age_days} days ago)"
            return self._format_playbook_prompt(playbook, playbook_row.runs_distilled) + age_note

        # Cold-start fallback: aggregate from last 5 raw runs for this workspace+niche
        recent_runs = (
            self.db.query(ResearchRun)
            .filter(ResearchRun.profile_name == profile_name, ResearchRun.niche == niche)
            .order_by(ResearchRun.created_at.desc())
            .limit(5)
            .all()
        )
        if not recent_runs:
            return None
        return self._format_heuristic_playbook(recent_runs)

    @staticmethod
    def _format_playbook_prompt(playbook: dict, runs_count: int) -> str:
        sections = [f"RESEARCH PLAYBOOK (distilled from {runs_count} runs in this niche):"]
        if playbook.get("preferred_tool_sequence"):
            sections.append(f"- Optimal tool order: {' -> '.join(playbook['preferred_tool_sequence'][:5])}")
        if playbook.get("kd_threshold"):
            sections.append(f"- KD ceiling for this niche: {playbook['kd_threshold']} (sweet spot: {playbook.get('kd_sweet_spot', {})})")
        if playbook.get("effective_exa_patterns"):
            sections.append(f"- Proven Exa query patterns: {', '.join(playbook['effective_exa_patterns'][:3])}")
        if playbook.get("recurring_info_gaps"):
            sections.append(f"- Known competitor blind spots: {'; '.join(playbook['recurring_info_gaps'][:3])}")
        if playbook.get("entity_clusters"):
            flat = [e for cluster in playbook["entity_clusters"][:3] for e in cluster[:5]]
            sections.append(f"- High-value entities: {', '.join(flat)}")
        sections.append("Use this intelligence to guide your tool selection. Deviate only if this specific keyword warrants it.")
        return "\n".join(sections)

    @staticmethod
    def _format_heuristic_playbook(runs: list) -> str:
        """Build a minimal playbook prompt from raw runs (cold-start fallback)."""
        from collections import Counter
        tool_counter: Counter = Counter()
        kd_list: list[int] = []
        entity_counter: Counter = Counter()
        exa_patterns: list[str] = []

        for run in runs:
            try:
                tools = json.loads(run.tool_sequence_json or "[]")
                for t in tools:
                    tool_counter[t] += 1
            except Exception:
                pass
            if run.avg_kd is not None:
                kd_list.append(run.avg_kd)
            try:
                entities = json.loads(run.entity_cluster_json or "[]")
                for e in entities:
                    entity_counter[e] += 1
            except Exception:
                pass
            try:
                exa_qs = json.loads(run.exa_queries_json or "[]")
                exa_patterns.extend(exa_qs[:2])
            except Exception:
                pass

        sections = [f"EARLY RESEARCH PATTERNS (from {len(runs)} runs in this niche):"]
        if tool_counter:
            top_tools = [t for t, _ in tool_counter.most_common(5)]
            sections.append(f"- Commonly used tools: {' -> '.join(top_tools)}")
        if kd_list:
            avg_kd = int(sum(kd_list) / len(kd_list))
            sections.append(f"- Average KD encountered: {avg_kd} (consider targeting below this)")
        if entity_counter:
            top_entities = [e for e, _ in entity_counter.most_common(8)]
            sections.append(f"- Recurring high-value entities: {', '.join(top_entities)}")
        if exa_patterns:
            unique_patterns = list(dict.fromkeys(exa_patterns))[:3]
            sections.append(f"- Prior Exa query patterns: {'; '.join(unique_patterns)}")
        sections.append("Use these patterns as a starting point; adapt based on this keyword's specifics.")
        return "\n".join(sections)

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
    # DeepSeek Agentic Logic (Scout & Extract Architecture)
    # ------------------------------------------------------------------

    def _build_agentic_prompt(self, keyword: str, available_tools: list[dict], user_context: str = "", niche: str = "default", niche_intel: str | None = None) -> str:
        """Build the initial system prompt for the iterative R1 agentic loop."""
        niche_hint = f" in the {niche} niche" if niche != "default" else ""
        prompt = (
            f"You are an expert SEO Autonomous Agent. We are researching the keyword '{keyword}'{niche_hint}.\n"
            f"USER DIRECTIVE / INTENT CONTEXT:\n{user_context if user_context else 'None provided. Assume general intent.'}\n\n"
            "You have access to the following tools:\n"
            f"{json.dumps(available_tools, indent=2)}\n\n"
            "CRITICAL: You MUST call tools before producing any final output. Do NOT skip to the final analysis.\n\n"
            "STEP 1 — CALL THESE TOOLS FIRST (mandatory, do these on your first iteration):\n"
            "Return JSON: {\"tool_calls\": [{\"tool_name\": \"dataforseo_labs_google_keyword_ideas\", \"arguments\": {\"keywords\": [\"" + keyword + "\"], \"location_code\": 2840, \"language_code\": \"en\"}}, {\"tool_name\": \"serp_organic_live_advanced\", \"arguments\": {\"keyword\": \"" + keyword + "\", \"location_code\": 2840, \"language_code\": \"en\", \"depth\": 10}}]}\n\n"
            "STEP 2 — AFTER receiving Step 1 results, call at least 2 of these strategic tools:\n"
            "- 'exa_scout_search' with different queries (exact topic, contrarian angle, case studies)\n"
            "- 'exa_extract_full_text' to read the best articles found\n"
            "- Any tool with 'backlink' in the name for authority analysis\n"
            "- Any tool with 'on_page' in the name for competitor structure\n"
            "- Any tool with 'related' or 'long_tail' in the name for underserved angles\n"
            "Use ONLY exact tool names from the tool list above. Do NOT guess names.\n\n"
            "STEP 3 — ONLY after completing Steps 1 and 2, output your final analysis as JSON:\n"
            "{\n"
            '  "information_gap": "2-3 sentences: the specific expert angle Page 1 is ignoring",\n'
            '  "unique_angles": ["3-5 content angles that differentiate from Page 1"],\n'
            '  "competitor_weaknesses": ["2-3 weaknesses in top-ranking content"],\n'
            '  "data_points": ["statistics or benchmarks found in competitor content"],\n'
            '  "practitioner_insights": ["1-2 real-world findings from Exa articles"]\n'
            "}\n\n"
            "RULES:\n"
            "- You MUST call tools in Steps 1 and 2 BEFORE outputting Step 3.\n"
            "- To call tools, return: {\"tool_calls\": [{\"tool_name\": \"...\", \"arguments\": {...}}]}\n"
            "- Return ONLY valid JSON. No markdown, no extra text.\n"
            "- You may call multiple tools per iteration.\n"
            "- ZERO HALLUCINATION: Use only exact tool names from the list above."
        )
        if niche_intel:
            prompt += (
                "\n\n<niche_playbook>\n"
                f"{niche_intel}\n"
                "</niche_playbook>\n\n"
                "CRITICAL INSTRUCTION: The <niche_playbook> above contains historical data and past topics. "
                "You must use it STRICTLY for tone, audience insights, and strategic style. "
                "DO NOT research or write about the specific past topics mentioned in the playbook. "
                f"You must focus EXCLUSIVELY on your current Target Keyword: '{keyword}'"
            )
        return prompt

    async def _call_deepseek_r1(self, messages: list[dict]) -> str:
        """Send messages to DeepSeek-R1 and return raw content string."""
        if not DEEPSEEK_API_KEY:
            raise ValueError("DeepSeek API key missing.")
        
        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "deepseek-reasoner",
            "messages": messages,
            "max_tokens": 4000
        }
        
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(DEEPSEEK_API_URL, headers=headers, json=payload)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]

    @staticmethod
    def _parse_r1_response(content: str) -> dict:
        """
        Parse DeepSeek-R1's response into structured JSON.
        Handles <think> blocks, markdown code fences, and raw JSON.
        """
        # Strip <think> reasoning blocks
        clean = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
        
        # Try markdown code fence first
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', clean, re.DOTALL)
        if json_match:
            clean = json_match.group(1).strip()
        else:
            start = clean.find('{')
            end = clean.rfind('}')
            if start != -1 and end != -1:
                clean = clean[start:end+1]
            else:
                return {}
        
        try:
            return json.loads(clean)
        except json.JSONDecodeError:
            return {}

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

    def _get_cached(self, keyword: str, profile_name: str, niche: str) -> dict | None:
        """Return cached result if it exists and hasn't expired."""
        row = (
            self.db.query(ResearchCache)
            .filter(
                ResearchCache.keyword == keyword.lower(),
                ResearchCache.profile_name == profile_name,
                ResearchCache.niche == niche
            )
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

    def _save_cache(self, keyword: str, profile_name: str, niche: str, result: dict) -> None:
        """Upsert research result into the cache table."""
        row = (
            self.db.query(ResearchCache)
            .filter(
                ResearchCache.keyword == keyword.lower(),
                ResearchCache.profile_name == profile_name,
                ResearchCache.niche == niche
            )
            .first()
        )
        payload = json.dumps(result, ensure_ascii=False)

        if row:
            row.result_json = payload
            row.created_at = datetime.now(timezone.utc)
        else:
            row = ResearchCache(
                keyword=keyword.lower(),
                profile_name=profile_name,
                niche=niche,
                result_json=payload,
                cache_ttl_hours=CACHE_TTL_HOURS,
            )
            self.db.add(row)

        self.db.commit()
