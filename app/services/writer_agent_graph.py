import json
import re
from typing import TypedDict, List, Dict, Any, Optional
from langgraph.graph import StateGraph, END
from pydantic import BaseModel, Field
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from .readability_service import verify_readability
from ..settings import ANTHROPIC_API_KEY

import logging
logger = logging.getLogger(__name__)

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
    
    system = "You are an elite SEO Content Strategist. Create a strict multi-section outline (5-8 sections)."
    
    prompt = f"""
    Based on the following blueprint:
    {json.dumps(blueprint, indent=2)}
    
    Create a detailed section-by-section plan. 
    - First section MUST be the Information Gap hook.
    - Assign 1-3 specific 'entities' and 1-2 'semantic_keywords' to each section so they are evenly distributed.
    - Assign exactly 'markdown_table', 'bulleted_list', or 'numbered_list' to at least 3 distinct sections across the outline.
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
    
    yield_msgs = [{"type": "debug", "message": f"Graph: WriterNode drafting section {idx+1}..."}]
    
    system = (
        "You are an expert B2B copywriter. Write EXACTLY the requested text for ONE section of a larger article. "
        "Do NOT write an introduction or conclusion unless this is the first/last section. "
        "Write in short, punchy, active-voice sentences. Keep sentence lengths strictly between 8-14 words."
    )
    
    prompt = f"""
    Write roughly 200-250 words for this specific section.
    
    Heading: {section.h2}
    Goal: {section.psychological_goal}
    Info trigger: {section.information_gain_trigger}
    Keywords to include: {', '.join(section.assigned_keywords)}
    Entities to include: {', '.join(section.assigned_entities)}
    Required structural element: {section.structural_element}
    
    CRITICAL RESTRICTION - BANNED WORDS:
    Do NOT use: 'delve', 'tapestry', 'landscape', 'multifaceted', 'comprehensive', 'holistic', 'navigate', 'crucial', 'robust', 'seamless', 'synergy', 'leverage', 'scalable', 'foster', 'optimize', 'ecosystem', 'paradigm'.
    
    CRITICAL RESTRICTION - VOCABULARY:
    You MUST NOT use words with more than 3 syllables. Do not use academic or complex B2B jargon. Write exactly as if you were speaking casually to a novice. If you use long words, the readability validation will fail and you will be penalized.
    
    CRITICAL RESTRICTION - FORMATTING:
    Only output the Markdown content for this section. No chat preamble.
    """
    
    style_rules = state.get("style_rules", "")
    if style_rules:
        prompt += f"\nCRITICAL HUMAN STYLE GUIDELINES:\n{style_rules}\n"
    
    if citations:
        prompt += "\nCRITICAL RESTRICTION - CITATIONS:\nYou must use the following facts and cite them INLINE immediately after stating the fact using EXACTLY this Markdown format: `[Anchor Text](URL)`. Do NOT use footnotes.\n\nCRITICAL RESTRICTION - SOURCE ATTRIBUTION:\nDo NOT name specific organizations (e.g., 'McKinsey', 'Gartner', 'Harvard') in the text UNLESS the citation URL actually belongs to that organization. If a fact mentions 'McKinsey says X' but the source URL is a third-party blog, you must rephrase as 'industry research shows X' or 'according to [Blog Name](url)'. Misattributing a claim to an organization while linking to an unrelated blog destroys reader trust.\n\nFacts required:\n"
        for c in citations:
            prompt += f"Fact: {c['fact_text']}\nCitation string to use: [{c['citation_anchor']}]({c['source_url']})\n\n"
    else:
        prompt += "\nCRITICAL RESTRICTION - NO FABRICATION:\nNo mandatory facts for this section. You MUST NOT:\n- Invent any numbers, statistics, or percentages.\n- Fabricate case studies, anecdotes, or success stories.\n- Create fictional people, company names, or quotes.\n- Attribute statements to unnamed sources (e.g., 'one business owner said').\nIf you do not have a provided citation for a claim, DO NOT make the claim. Write only general advice and actionable guidance.\n"
        
    if feedback:
        prompt += f"\nREVISION REQUIRED based on Editor Feedback:\n{feedback}\nYOU MUST REDUCE THE COMPLEXITY OF YOUR VOCABULARY AND SENTENCE LENGTH TO PASS. DO NOT MAKE THESE MISTAKES AGAIN."
        
    llm = get_claude(0.7)
    res = await llm.ainvoke([SystemMessage(content=system), HumanMessage(content=prompt)])
    
    return {"current_section_draft": res.content, "yield_messages": yield_msgs}

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
    if section.structural_element in ['bulleted_list', 'numbered_list'] and not re.search(r'(\n-[ \w]|\n\*[ \w]|\n\d+\.[ \w])', draft):
        errors.append("You failed to include the required list format.")
        
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
