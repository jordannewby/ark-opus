import json
import re
from pathlib import Path
from typing import TypedDict, List, Dict, Any, Optional
from langgraph.graph import StateGraph, END
from pydantic import BaseModel, Field
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from anthropic import AsyncAnthropic

from .readability_service import verify_readability
from ..settings import ANTHROPIC_API_KEY

import logging
logger = logging.getLogger(__name__)

# Raw Anthropic client for extended thinking (writer node)
_anthropic_client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

# Load the writer system prompt once at module level
_WRITER_PROMPT_PATH = Path(__file__).parent / "prompts" / "writer.md"
with open(_WRITER_PROMPT_PATH, "r", encoding="utf-8") as _f:
    _WRITER_SYSTEM_PROMPT = _f.read()

# --- Data Models ---
class SectionPlan(BaseModel):
    h2: str = Field(description="The exactly formatted H2 heading, starting with ##")
    psychological_goal: str = Field(description="The goal of this section")
    information_gain_trigger: str = Field(description="The unique information to reveal")
    assigned_entities: List[str] = Field(description="1-3 SEO entities to weave in")
    assigned_keywords: List[str] = Field(description="1-2 SEO keywords to include")
    structural_element: str = Field(description="One of: 'none', 'markdown_table', 'bulleted_list', 'numbered_list'")

class ArticleOutline(BaseModel):
    sections: List[SectionPlan] = Field(description="List of exactly planned sections. Must be at least 5 sections. At least 3 sections MUST have a structural_element.")

class WriterState(TypedDict):
    blueprint: dict
    profile_name: str
    niche: str
    all_citations: List[dict] # list of dicts with 'citation_anchor', 'source_url', 'fact_text'
    style_rules: str # Dynamic human rules from DB
    
    sections_planned: List[SectionPlan]
    current_section_idx: int
    draft_sections: List[str]
    
    current_section_citations: List[dict]
    current_section_draft: str
    section_feedback: str
    section_retry_count: int
    
    final_article: str
    yield_messages: List[dict]

def get_claude(temperature=0.7):
    return ChatAnthropic(
        model_name="claude-sonnet-4-20250514", 
        temperature=temperature, 
        api_key=ANTHROPIC_API_KEY,
        max_tokens=2048
    )

async def planner_node(state: WriterState) -> dict:
    blueprint = state["blueprint"]
    yield_msgs = [{"type": "debug", "message": "Graph: Running PlannerNode to structure sections..."}]
    
    system = (
        "You are an elite SEO Content Strategist. Create a strict multi-section outline (5-8 sections). "
        "HEADING RULES (strictly enforced): "
        "1. Each H2 heading must be 8 words or fewer. "
        "2. Use simple, common words — no word may exceed 3 syllables. "
        "3. Write headings that a 7th-grader would understand. "
        "4. Do NOT use these banned words in headings: delve, landscape, multifaceted, comprehensive, holistic, navigate, crucial, robust, seamless, synergy, leverage, scalable, foster, optimize, ecosystem, paradigm. "
        "5. Headings must be punchy and direct (e.g., 'Why Most AI Plans Fail' not 'Understanding the Multifaceted Challenges of Artificial Intelligence Implementation')."
    )
    
    prompt = f"""
    Based on the following blueprint:
    {json.dumps(blueprint, indent=2)}
    
    Create a detailed section-by-section plan. 
    - First section MUST be the Information Gap hook.
    - Assign 1-3 specific 'entities' and 1-2 'semantic_keywords' to each section so they are evenly distributed.
    - Assign exactly 'markdown_table', 'bulleted_list', or 'numbered_list' to at least 3 distinct sections across the outline.
    - Keep ALL headings under 8 words. Use simple, short words only.
    """
    
    llm = get_claude(0.2).with_structured_output(ArticleOutline)
    outline = await llm.ainvoke([SystemMessage(content=system), HumanMessage(content=prompt)])
    
    yield_msgs.append({"type": "debug", "message": f"Graph: Planner mapped {len(outline.sections)} sections."})
    return {"sections_planned": outline.sections, "current_section_idx": 0, "draft_sections": [], "yield_messages": yield_msgs}

async def retriever_node(state: WriterState) -> dict:
    idx = state["current_section_idx"]
    section = state["sections_planned"][idx]
    all_citations = state["all_citations"]
    
    yield_msgs = [{"type": "debug", "message": f"Graph: RetrieverNode finding facts for section {idx+1} ({section.h2})..."}]
    
    if not all_citations:
        return {"current_section_citations": [], "section_retry_count": 0, "section_feedback": "", "yield_messages": yield_msgs}

    system = "You are a Research Assistant. Pick the 0 to 2 most relevant citations for the section described."
    c_list = [f"ID {i}: {c['fact_text']} (Source: {c['source_url']})" for i, c in enumerate(all_citations)]
    
    prompt = f"""
    Section H2: {section.h2}
    Goal: {section.psychological_goal}
    
    Available Citations:
    {json.dumps(c_list, indent=2)}
    
    Return EXACTLY a JSON list of integer IDs for the best 0-2 matches, e.g. [1, 4]. 
    If none match well, return []. ONLY return the JSON list string.
    """
    
    llm = get_claude(0.0)
    try:
        res = await llm.ainvoke([SystemMessage(content=system), HumanMessage(content=prompt)])
        match = re.search(r'\[(.*?)\]', res.content)
        if match:
            ids = [int(x.strip()) for x in match.group(1).split(",") if x.strip().isdigit()]
            ids = ids[:2]
            selected = [all_citations[i] for i in ids if 0 <= i < len(all_citations)]
        else:
            selected = []
    except Exception:
        selected = []
        
    yield_msgs.append({"type": "debug", "message": f"Graph: Retriever found {len(selected)} facts for this section."})
    return {"current_section_citations": selected, "section_retry_count": 0, "section_feedback": "", "yield_messages": yield_msgs}

async def writer_node(state: WriterState) -> dict:
    idx = state["current_section_idx"]
    section = state["sections_planned"][idx]
    citations = state["current_section_citations"]
    feedback = state.get("section_feedback", "")
    
    yield_msgs = [{"type": "debug", "message": f"Graph: WriterNode drafting section {idx+1} (extended thinking)..."}]
    
    # --- System prompt: writer.md + section-mode override ---
    system = _WRITER_SYSTEM_PROMPT + (
        "\n\n# SECTION-MODE OVERRIDE\n"
        "You are writing ONE section of a larger article, not the full article. "
        "Do NOT write an introduction or conclusion unless this is the first/last section. "
        "Do NOT output an H1 title — only the ## H2 heading for this section. "
        "Target 200-250 words for this section.\n\n"
        "# THINKING INSTRUCTIONS\n"
        "Think thoroughly before writing. In your thinking, analyze the available facts, "
        "plan the section structure, check every word against the banned list, and verify "
        "readability. Before you finish, self-check your output against ALL restrictions: "
        "banned words, readability (8-12 words per sentence), no fabrication, proper citations, "
        "and required structural elements. Fix any violations before outputting."
    )
    
    # --- Build structural element instruction ---
    struct_instruction = ""
    if section.structural_element == 'bulleted_list':
        struct_instruction = (
            "REQUIRED FORMAT: You MUST include a Markdown bulleted list in this section. "
            "Use this exact syntax (dash + space + text), one item per line:\n"
            "- First item here\n"
            "- Second item here\n"
            "- Third item here\n"
            "The list MUST have at least 3 items."
        )
    elif section.structural_element == 'numbered_list':
        struct_instruction = (
            "REQUIRED FORMAT: You MUST include a Markdown numbered list in this section. "
            "Use this exact syntax (number + period + space + text), one item per line:\n"
            "1. First item here\n"
            "2. Second item here\n"
            "3. Third item here\n"
            "The list MUST have at least 3 items."
        )
    elif section.structural_element == 'markdown_table':
        struct_instruction = (
            "REQUIRED FORMAT: You MUST include a Markdown table in this section. "
            "Use this exact syntax with pipe characters:\n"
            "| Column A | Column B |\n"
            "| --- | --- |\n"
            "| Data 1 | Data 2 |\n"
            "The table MUST have at least 2 columns and 3 data rows."
        )

    # --- Build user prompt ---
    prompt = f"""Write roughly 200-250 words for this specific section.

<section_requirements>
Heading: {section.h2}
Goal: {section.psychological_goal}
Info trigger: {section.information_gain_trigger}
Keywords to include: {', '.join(section.assigned_keywords)}
Entities to include: {', '.join(section.assigned_entities)}
</section_requirements>

{struct_instruction}

<restrictions>
VOCABULARY: Write at a 7th-grade reading level. Use short, common words only.
BANNED WORDS (instant fail if used): delve, tapestry, landscape, multifaceted, comprehensive, holistic, navigate, crucial, robust, seamless, synergy, leverage, scalable, foster, optimize, ecosystem, paradigm.
WORD SWAPS: implement→use, utilize→use, demonstrate→show, methodology→method, subsequently→then, approximately→about, requirements→needs, functionality→features, facilitate→help, organizations→firms, recommendations→tips, establishing→setting up.
SENTENCES: Target 8-12 words. Max 15 words. Vary rhythm: short-punchy-long.
FORMATTING: Only output the Markdown. Start with ## heading. No chat preamble. No sign-off.
</restrictions>
"""
    
    style_rules = state.get("style_rules", "")
    if style_rules:
        prompt += f"\n<human_style_rules>\n{style_rules}\n</human_style_rules>\n"
    
    # NO FABRICATION — always applies
    prompt += """\n<no_fabrication>
ZERO TOLERANCE: You MUST NOT invent ANY claim not backed by a citation below.
- No invented numbers, statistics, or percentages.
- No fabricated case studies, anecdotes, or success stories.
- No fictional people, company names, or quotes.
- No attribution to unnamed sources (e.g., 'one business owner said').
- If a fact is not in the citation list, DO NOT state it. Use general advice instead.
VIOLATION = IMMEDIATE REJECTION.
</no_fabrication>
"""

    if citations:
        citation_block = "\n".join(
            f"- Fact: {c['fact_text']}\n  Cite as: [{c['citation_anchor']}]({c['source_url']})"
            for c in citations
        )
        prompt += f"""\n<citations>
Use these facts INLINE with Markdown links: [Anchor](URL). No footnotes.
These are the ONLY facts you may state as data-backed claims.
Do NOT name organizations (McKinsey, Gartner, etc.) unless the URL belongs to them.

{citation_block}
</citations>
"""
    else:
        prompt += "\n<citations>\nNo citations available. Write only general advice. Do NOT state any statistics or data-backed claims.\n</citations>\n"
        
    if feedback:
        prompt += (
            f"\n<revision_feedback>\n{feedback}\n"
            "REMINDER: Do NOT invent statistics not in the citation list. "
            "REDUCE vocabulary complexity and sentence length.\n"
            "</revision_feedback>\n"
        )

    prompt += """\n<self_check>
Before you output your final text, verify:
1. No banned words used.
2. Every sentence is 8-15 words.
3. Every statistic has an inline [Source](URL) citation.
4. No fabricated claims.
5. Required structural element (list/table) is present if specified.
Fix any violations before outputting.
</self_check>

Output ONLY the final Markdown section text."""

    # --- Call Claude with extended thinking ---
    try:
        response = await _anthropic_client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=16000,
            thinking={
                "type": "enabled",
                "budget_tokens": 10000,
            },
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        
        # Extract thinking and text content from response
        draft_text = ""
        thinking_text = ""
        for block in response.content:
            if block.type == "thinking":
                thinking_text = block.thinking
            elif block.type == "text":
                draft_text = block.text
        
        # Log thinking for debug visibility
        if thinking_text:
            # Truncate for log readability
            thinking_preview = thinking_text[:500] + "..." if len(thinking_text) > 500 else thinking_text
            yield_msgs.append({"type": "debug", "message": f"Graph: [THINKING] {thinking_preview}"})
            logger.debug(f"[WRITER-THINKING] Section {idx+1} full thinking ({len(thinking_text)} chars):\n{thinking_text}")
        
    except Exception as e:
        logger.error(f"[WRITER] Extended thinking call failed: {e}. Falling back to standard call.")
        # Fallback to standard LangChain call if extended thinking fails
        llm = get_claude(0.7)
        res = await llm.ainvoke([SystemMessage(content=system), HumanMessage(content=prompt)])
        draft_text = res.content
    
    return {"current_section_draft": draft_text, "yield_messages": yield_msgs}

async def editor_node(state: WriterState) -> dict:
    draft = state["current_section_draft"]
    section = state["sections_planned"][state["current_section_idx"]]
    citations = state["current_section_citations"]
    retries = state.get("section_retry_count", 0)
    
    yield_msgs = [{"type": "debug", "message": "Graph: EditorNode validating draft..."}]
    
    errors = []
    
    # 1. Banned words check
    banned = ['delve', 'tapestry', 'landscape', 'multifaceted', 'comprehensive', 'holistic', 'navigate', 'crucial', 'robust', 'seamless', 'synergy', 'leverage', 'scalable', 'foster', 'optimize', 'ecosystem', 'paradigm']
    found_banned = [w for w in banned if re.search(r'\b' + w + r'\b', draft, re.IGNORECASE)]
    if found_banned:
        errors.append(f"You used banned words: {', '.join(found_banned)}. Replace them with simpler terms.")
        
    # 2. ARI check
    read_result = verify_readability(draft)
    details = read_result.get("details", {})
    ari = details.get("ari_grade", 0)
    if ari > 11.5:
        errors.append(f"Readability is too complex (ARI: {ari}). Shorten your sentences to 8-12 words.")
        
    # 3. Citation check
    for c in citations:
        expected_url = c['source_url']
        if expected_url not in draft:
            errors.append(f"Missing or malformed citation for URL: {expected_url}. You MUST include the exact markdown link.")
            
    # 4. Structure check
    if section.structural_element == 'markdown_table' and '|' not in draft:
        errors.append("You failed to include a markdown table.")
    if section.structural_element in ['bulleted_list', 'numbered_list']:
        # Match list markers at start of string OR after newline, followed by any non-empty content
        list_pattern = r'(^|\n)\s*(-|\*|\d+\.)\s+\S'
        if not re.search(list_pattern, draft, re.MULTILINE):
            errors.append("You failed to include the required list format. Use '- item' or '1. item' Markdown syntax.")

    # 5. Uncited claims check — detect fabricated statistics
    # Find all percentage/number claims and check they're adjacent to a citation link
    stat_pattern = r'\b\d+(?:\.\d+)?\s*%'
    stat_matches = list(re.finditer(stat_pattern, draft))
    if stat_matches:
        citation_link_pattern = r'\[[^\]]+\]\(https?://[^)]+\)'
        uncited_stats = []
        for m in stat_matches:
            # Check if there's a citation link within 200 chars after the stat
            after_stat = draft[m.start():min(len(draft), m.end() + 200)]
            if not re.search(citation_link_pattern, after_stat):
                # Also check 100 chars before (citation might precede the stat)
                before_stat = draft[max(0, m.start() - 100):m.end()]
                if not re.search(citation_link_pattern, before_stat):
                    uncited_stats.append(m.group())
        if uncited_stats:
            errors.append(f"You stated statistics without citations: {', '.join(uncited_stats[:3])}. Every statistic MUST have an inline [Source](URL) citation immediately adjacent, or be removed.")

    # 6. Unverified entity check — detect hallucinated product/tool names
    from .claim_verification_agent import detect_unverified_entities
    citation_urls = [c['source_url'] for c in state['all_citations']]
    citation_anchors = [c.get('citation_anchor', '') for c in state['all_citations']]
    unverified = detect_unverified_entities(draft, citation_urls, citation_anchors)
    if unverified:
        errors.append(f"Unverified product/tool names not found in any citation source: {', '.join(unverified[:5])}. Remove these or replace with tools mentioned in your citation sources.")
        
    if errors and retries < 2:
        fb = "\n".join(errors)
        yield_msgs.append({"type": "debug", "message": f"Graph: Section failed validation, returning to Writer. Errors:\n{fb}"})
        return {"section_feedback": fb, "section_retry_count": retries + 1, "yield_messages": yield_msgs}
        
    if errors:
        yield_msgs.append({"type": "debug", "message": "Graph: Section failed validation but max retries reached. Moving on."})
    else:
        yield_msgs.append({"type": "debug", "message": "Graph: Section passed all validations!"})
        
    drafts = list(state["draft_sections"]) # copy the list to avoid mutations on the same reference
    drafts.append(draft)
    
    # Check if this is the last section
    is_done = (state["current_section_idx"] + 1) >= len(state["sections_planned"])
    final_article = ""
    if is_done:
        final_article = "\n\n".join(drafts)
        yield_msgs.append({"type": "content", "data": "\n\n" + draft}) # Yield final chunk
        yield_msgs.append({"type": "debug", "message": "Graph: Finished all sections!"})
    else:
        # yield this chunk to the UI immediately!
        yield_msgs.append({"type": "content", "data": "\n\n" + draft + "\n\n"})
    
    return {
        "draft_sections": drafts, 
        "current_section_idx": state["current_section_idx"] + 1,
        "section_feedback": "",
        "section_retry_count": 0,
        "yield_messages": yield_msgs,
        "final_article": final_article
    }

def route_editor(state: WriterState) -> str:
    if state["section_feedback"]:
        return "writer"
    if state["current_section_idx"] >= len(state["sections_planned"]):
        return "end"
    return "retriever"

workflow = StateGraph(WriterState)
workflow.add_node("planner", planner_node)
workflow.add_node("retriever", retriever_node)
workflow.add_node("writer", writer_node)
workflow.add_node("editor", editor_node)

workflow.set_entry_point("planner")
workflow.add_edge("planner", "retriever")
workflow.add_edge("retriever", "writer")
workflow.add_edge("writer", "editor")

workflow.add_conditional_edges("editor", route_editor, {"writer": "writer", "retriever": "retriever", "end": END})
app_graph = workflow.compile()
