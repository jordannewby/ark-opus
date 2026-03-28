import os
import asyncio
import logging
from pathlib import Path
from dotenv import load_dotenv

# Configure logging so INFO-level messages (scoring breakdowns, verified sources) are visible
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Ensure environment is loaded BEFORE importing services
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from contextlib import asynccontextmanager, AsyncExitStack
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .database import Base, engine, get_db, ensure_db_alive, migrate_research_cache, migrate_posts_readability, migrate_writer_learning, migrate_source_verification, migrate_composite_scoring, migrate_fact_consensus, migrate_domain_credibility_cache, migrate_fact_verification, migrate_style_rule_archive, migrate_writer_verification_telemetry, migrate_profile_settings, SessionLocal
from .models import Post, ProfileSettings, ResearchRun, UserStyleRule, Workspace, WriterRun, FactCitation
from .schemas import (
    BlueprintResponse,
    GenerateFullResponse,
    PostCreate,
    PostResponse,
    PostUpdate,
    ProfileSettingsUpdate,
    ProfileSettingsResponse,
    ResearchResponse,
    StyleRuleCreate,
    StyleRuleResponse,
    WorkspaceCreate,
    WorkspaceResponse,
    CampaignCreateRequest,
    CampaignResponse
)

# Import services AFTER the environment is loaded
from .services.research_service import ResearchAgent
from .services.cartographer_service import CartographerService

migrate_research_cache()
migrate_posts_readability()
migrate_writer_learning()
migrate_source_verification()
migrate_composite_scoring()
migrate_fact_consensus()
migrate_domain_credibility_cache()
migrate_fact_verification()
migrate_style_rule_archive()
migrate_writer_verification_telemetry()
migrate_profile_settings()
Base.metadata.create_all(bind=engine)

def normalize_niche(niche: str | None) -> str:
    """Single source of truth for niche normalization."""
    if not niche:
        return "general"
    return niche.strip().lower().replace(" ", "-")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # MCP session initialization for DataForSEO (used by ResearchAgent)
    # Note: Source verification uses tiered domain lists (no MCP needed there)
    from .settings import DATAFORSEO_LOGIN, DATAFORSEO_PASSWORD

    server_params = StdioServerParameters(
        command="node",
        args=[
            "mcp-dataforseo-server/index.js",
            DATAFORSEO_LOGIN,
            DATAFORSEO_PASSWORD
        ],
        env=None
    )

    exit_stack = AsyncExitStack()

    try:
        # Initialize persistent MCP session for the application lifetime
        stdio_transport = await exit_stack.enter_async_context(stdio_client(server_params))
        stdio, write = stdio_transport
        session = await exit_stack.enter_async_context(ClientSession(stdio, write))
        await session.initialize()

        # Store session in app state for access in endpoints
        app.state.mcp_session = session

        yield
    finally:
        await exit_stack.aclose()

app = FastAPI(title="Ares Engine Console", lifespan=lifespan)

# --- CRUD Endpoints ---

@app.get("/posts", response_model=list[PostResponse])
def list_posts(skip: int = 0, limit: int = 20, profile_name: str = "default", db: Session = Depends(get_db)):
    return db.query(Post).filter(Post.profile_name == profile_name).offset(skip).limit(limit).all()

@app.get("/posts/{post_id}", response_model=PostResponse)
def get_post(post_id: int, profile_name: str = "default", db: Session = Depends(get_db)):
    post = db.query(Post).filter(Post.id == post_id, Post.profile_name == profile_name).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return post

@app.post("/posts", response_model=PostResponse, status_code=201)
def create_post(data: PostCreate, db: Session = Depends(get_db)):
    post = Post(**data.model_dump())
    db.add(post)
    db.commit()
    db.refresh(post)
    return post

from fastapi import BackgroundTasks

@app.post("/posts/{post_id}/approve", response_model=PostResponse)
async def approve_and_train_post(
    post_id: int,
    data: PostUpdate,
    background_tasks: BackgroundTasks,
    profile_name: str = "default",
    db: Session = Depends(get_db)
):
    """
    Accepts the human-edited content, updates the database, and spins up the FeedbackAgent
    in the background so the user's browser doesn't have to wait for DeepSeek to extract style rules.
    """
    post = db.query(Post).filter(Post.id == post_id, Post.profile_name == profile_name).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    # The frontend should send the completely human-edited markdown as `data.content`
    if not data.content:
        raise HTTPException(status_code=400, detail="Content is required for approval")

    # Only fire training if changes were actually made
    if post.original_ai_content and post.original_ai_content.strip() != data.content.strip():
        # Set human_edited_content strictly as the new baseline
        post.human_edited_content = data.content

        # Capture scalar values before response returns and session closes
        original_content = post.original_ai_content
        edited_content = data.content
        profile = post.profile_name
        niche = post.niche if post.niche else "general"

        # Background task wrappers that create their own DB sessions
        async def _bg_feedback():
            from .services.feedback_service import FeedbackAgent
            bg_db = SessionLocal()
            try:
                agent = FeedbackAgent(db=bg_db)
                await agent.analyze_and_store_feedback(original_content, edited_content, profile)
            finally:
                bg_db.close()

        def _bg_research_score():
            from .services.research_intel_service import ResearchIntelService
            bg_db = SessionLocal()
            try:
                svc = ResearchIntelService(db=bg_db)
                svc.score_research_run(post_id, original_content, edited_content)
            finally:
                bg_db.close()

        def _bg_writer_score_and_distill():
            from .services.writer_intel_service import WriterIntelService
            bg_db = SessionLocal()
            try:
                WriterIntelService.score_writer_run(post_id, bg_db)
                WriterIntelService.maybe_distill(profile, niche, bg_db)
            finally:
                bg_db.close()

        background_tasks.add_task(_bg_feedback)
        background_tasks.add_task(_bg_research_score)
        background_tasks.add_task(_bg_writer_score_and_distill)

    # Update the primary content string
    post.content = data.content
    
    # Allow title updates as well if provided
    if data.title:
        post.title = data.title

    db.commit()
    db.refresh(post)
    return post

# --- AI BRAIN / STYLE RULE CRUD ---

@app.get("/rules", response_model=list[StyleRuleResponse])
def get_style_rules(profile_name: str = "default", db: Session = Depends(get_db)):
    """Fetch all learned style rules from the AI's memory."""
    return db.query(UserStyleRule).filter(UserStyleRule.profile_name == profile_name).order_by(UserStyleRule.id.desc()).all()

@app.post("/rules", response_model=StyleRuleResponse)
def add_style_rule(rule: StyleRuleCreate, db: Session = Depends(get_db)):
    """Manually inject a new style rule into the AI's memory."""
    new_rule = UserStyleRule(rule_description=rule.rule_description, profile_name=rule.profile_name)
    db.add(new_rule)
    db.commit()
    db.refresh(new_rule)
    return new_rule

@app.delete("/rules/{rule_id}")
def delete_style_rule(rule_id: int, profile_name: str = "default", db: Session = Depends(get_db)):
    """Delete a specific style rule from memory."""
    rule = db.get(UserStyleRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    if rule.profile_name != profile_name:
        raise HTTPException(status_code=404, detail="Rule not found")
    db.delete(rule)
    db.commit()
    return {"status": "deleted"}

# --- WORKSPACE ENDPOINTS ---

@app.get("/workspaces", response_model=list[WorkspaceResponse])
def get_workspaces(db: Session = Depends(get_db)):
    """Fetch all saved workspaces."""
    return db.query(Workspace).order_by(Workspace.name.asc()).all()

@app.post("/workspaces", response_model=WorkspaceResponse)
def create_workspace(workspace: WorkspaceCreate, db: Session = Depends(get_db)):
    """Create a new workspace if the slug does not exist."""
    existing = db.query(Workspace).filter(Workspace.slug == workspace.slug).first()
    if existing:
        return existing
    
    new_workspace = Workspace(name=workspace.name, slug=workspace.slug)
    db.add(new_workspace)
    db.commit()
    db.refresh(new_workspace)
    return new_workspace

# --- CARTOGRAPHER ENDPOINTS ---

@app.get("/campaigns", response_model=list[CampaignResponse])
def get_campaigns(profile_name: str = "default", db: Session = Depends(get_db)):
    """Fetch structured campaigns from DB."""
    service = CartographerService(db)
    return service.get_campaigns(profile_name)

@app.post("/campaigns/plan", response_model=CampaignResponse)
async def plan_campaign(req: CampaignCreateRequest, db: Session = Depends(get_db)):
    """Generate a Pillar/Spoke map via DataForSEO & DeepSeek."""
    service = CartographerService(db)
    return await service.plan_campaign(req.seed_topic, req.profile_name, req.niche_context)

# --- Orchestration Endpoints ---

@app.get("/research/{keyword:path}", response_model=ResearchResponse)
async def research_keyword(keyword: str, niche: str = "default", profile_name: str = "default", db: Session = Depends(get_db)):
    agent = ResearchAgent(db)
    return await agent.research(keyword, niche=niche, profile_name=profile_name)

@app.post("/blueprint", response_model=BlueprintResponse)
async def generate_blueprint(research_data: ResearchResponse, db: Session = Depends(get_db)):
    from .services.psychology_agent import PsychologyAgent
    agent = PsychologyAgent(db=db) 
    # research_data is a Pydantic model here, so we dump it to a dict
    blueprint = await agent.generate_blueprint(research_data.model_dump())
    return blueprint

import json
from .schemas import GeneratePayload

@app.get("/clarify")
async def clarify_intent(keyword: str):
    from .services.briefing_agent import BriefingAgent
    agent = BriefingAgent()
    questions = await agent.get_clarifying_questions(keyword)
    return {"questions": questions}

# --- Settings Endpoints ---

@app.get("/settings", response_model=ProfileSettingsResponse)
def get_settings(profile_name: str = "default", db: Session = Depends(get_db)):
    from .settings import CONFIGURABLE_SETTINGS, resolve_settings
    row = db.query(ProfileSettings).filter_by(profile_name=profile_name).first()
    merged = resolve_settings(row)
    return ProfileSettingsResponse(
        profile_name=profile_name,
        settings=merged,
        configurable=CONFIGURABLE_SETTINGS,
    )

@app.put("/settings", response_model=ProfileSettingsResponse)
def update_settings(payload: ProfileSettingsUpdate, profile_name: str = "default", db: Session = Depends(get_db)):
    import json as _json
    from .settings import CONFIGURABLE_SETTINGS, resolve_settings

    # Validate bounds/choices
    updates = payload.model_dump(exclude_none=True)
    for key, val in updates.items():
        meta = CONFIGURABLE_SETTINGS.get(key)
        if not meta:
            raise HTTPException(status_code=422, detail=f"Unknown setting: {key}")
        if "choices" in meta and val not in meta["choices"]:
            raise HTTPException(status_code=422, detail=f"{key} must be one of {meta['choices']}")
        if "min" in meta and val < meta["min"]:
            raise HTTPException(status_code=422, detail=f"{key} must be >= {meta['min']}")
        if "max" in meta and val > meta["max"]:
            raise HTTPException(status_code=422, detail=f"{key} must be <= {meta['max']}")

    row = db.query(ProfileSettings).filter_by(profile_name=profile_name).first()
    if row:
        existing = {}
        try:
            existing = _json.loads(row.settings_json)
        except (ValueError, TypeError):
            pass
        existing.update(updates)
        row.settings_json = _json.dumps(existing)
    else:
        row = ProfileSettings(
            profile_name=profile_name,
            settings_json=_json.dumps(updates),
        )
        db.add(row)
    db.commit()

    merged = resolve_settings(row)
    return ProfileSettingsResponse(
        profile_name=profile_name,
        settings=merged,
        configurable=CONFIGURABLE_SETTINGS,
    )


@app.post("/generate/{keyword:path}")
async def generate_article(keyword: str, payload: GeneratePayload, request: Request, db: Session = Depends(get_db)):
    from .services.psychology_agent import PsychologyAgent
    from .services.writer_service import WriterService
    from .settings import CONFIGURABLE_SETTINGS, resolve_settings
    import time
    import traceback

    niche = payload.niche
    context = payload.context

    # Resolve per-profile runtime settings (DB overrides + defaults)
    settings_row = db.query(ProfileSettings).filter_by(profile_name=payload.profile_name).first()
    runtime = resolve_settings(settings_row)

    logger.info(f"[ARES] Starting unified generation for: {keyword} (niche: {niche})")

    async def event_generator():
        nonlocal db
        start_time = time.time()
        try:
            if runtime["debug_mode"]:
                yield f"data: {json.dumps({'event': 'debug', 'message': f'Initializing Generation Sequence. Context: {bool(context)}'})}\n\n"
            # Phase 1
            yield f"data: {json.dumps({'event': 'phase1_start', 'message': 'Gathering intelligence and analyzing context...'})}\n\n"
            p1_start = time.time()
            research_agent = ResearchAgent(db)
            try:
                research_data_dict = await asyncio.wait_for(
                    research_agent.research(
                        keyword,
                        niche=niche,
                        user_context=context,
                        profile_name=payload.profile_name,
                        mcp_session=request.app.state.mcp_session,
                        settings_override=runtime,
                    ),
                    timeout=300
                )
            except asyncio.TimeoutError:
                yield f"data: {json.dumps({'event': 'error', 'message': 'Research phase timed out after 5 minutes. Try a more specific keyword or check your API connections.'})}\n\n"
                return
            if runtime["debug_mode"]:
                yield f"data: {json.dumps({'event': 'debug', 'message': f'Phase 1 (DeepSeek-R1 + MCP) completed in {round(time.time() - p1_start, 2)}s'})}\n\n"
            
            tools_used = research_data_dict.get("executed_tools", [])
            if runtime["debug_mode"] and tools_used:
                tools_str = ", ".join(tools_used)
                yield f"data: {json.dumps({'event': 'debug', 'message': f'MCP Tools Executed: {tools_str}'})}\n\n"

            # Phase 1.5 - Source Verification
            elite_competitors = research_data_dict.get("elite_competitors", [])
            research_run_id = research_data_dict.get("research_run_id", 0)

            source_content_map = {}  # Built during Phase 1.5, passed to writer for claim verification

            if elite_competitors:
                yield f"data: {json.dumps({'event': 'phase1_5_start', 'message': 'Verifying source credibility...'})}\n\n"
                p1_5_start = time.time()

                from .services.source_verification_service import verify_sources, link_facts_to_sources

                verification_result = await verify_sources(
                    elite_competitors=elite_competitors,
                    db=db,
                    profile_name=payload.profile_name,
                    research_run_id=research_run_id,
                    mcp_session=request.app.state.mcp_session,
                    keyword=keyword,
                    niche=niche,
                    min_score_threshold=runtime["source_credibility_threshold"],
                )

                verified_sources = verification_result["verified_sources"]
                rejected_sources = verification_result["rejected_sources"]

                if runtime["debug_mode"]:
                    for i, source in enumerate(verified_sources):
                        yield f"data: {json.dumps({'event': 'source_verification', 'source_title': source.title, 'domain': source.domain, 'credibility_score': round(source.credibility_score, 1), 'progress': f'{i+1}/{len(elite_competitors)}'})}\n\n"

                # Iterative source search if < 3 verified sources
                if len(verified_sources) < 3:
                    yield f"data: {json.dumps({'event': 'source_backfill_start', 'message': f'Only {len(verified_sources)} credible sources found. Starting iterative search...'})}\n\n"

                    from .services.source_verification_service import iterative_source_search

                    search_result = await iterative_source_search(
                        keyword=keyword,
                        niche=niche,
                        profile_name=payload.profile_name,
                        research_run_id=research_run_id,
                        db=db,
                        mcp_session=request.app.state.mcp_session,
                        research_agent=research_agent,
                        initial_sources=verified_sources,
                        target_count=3,
                        max_iterations=3,
                    )

                    verified_sources = search_result["verified_sources"]
                    rejected_sources.extend(search_result["rejected_sources"])

                    # Merge new sources into elite_competitors for fact extraction
                    for source in verified_sources:
                        elite_competitors.append({
                            "url": source.url,
                            "title": source.title,
                            "content": source.content_snippet or "",
                            "credibility_score": source.credibility_score,
                            "domain_authority": source.domain_authority,
                            "freshness_score": source.freshness_score,
                            "publish_date": source.publish_date.isoformat() if source.publish_date else None,
                            "domain": source.domain,
                        })

                    backfill_found = len(verified_sources)
                    iterations_used = search_result["iterations_used"]
                    yield f"data: {json.dumps({'event': 'source_backfill_complete', 'message': f'Iterative search complete: {backfill_found} total verified sources after {iterations_used} iterations', 'verified_count': backfill_found, 'iterations': iterations_used})}\n\n"

                    # Softer gate: allow 1-2 high-quality sources if avg credibility is very high
                    if len(verified_sources) == 0:
                        error_msg = f"Insufficient credible sources after iterative search: 0 sources found (need at least 1). Rejected: {len(rejected_sources)} sources."
                        yield f"data: {json.dumps({'event': 'error', 'message': error_msg})}\n\n"
                        return
                    elif len(verified_sources) < 3:
                        avg_score = sum(s.credibility_score for s in verified_sources) / len(verified_sources)
                        if avg_score >= 60.0:
                            logger.info(f"[GATE] Allowing {len(verified_sources)} sources (avg credibility: {avg_score:.1f})")
                            yield f"data: {json.dumps({'event': 'debug', 'message': f'Proceeding with {len(verified_sources)} high-quality sources (avg credibility: {avg_score:.1f}/100)'})}\n\n"
                        else:
                            error_msg = f"Insufficient credible sources: only {len(verified_sources)} found with avg credibility {avg_score:.1f} < 60.0 threshold."
                            yield f"data: {json.dumps({'event': 'error', 'message': error_msg})}\n\n"
                            return

                # Extract facts and link to sources (pass full content for better extraction)
                yield f"data: {json.dumps({'event': 'fact_verification_start', 'message': 'Verifying extracted facts against authoritative sources...'})}\n\n"

                fact_link_result = await link_facts_to_sources(
                    verified_sources, research_run_id, db,
                    elite_competitors=elite_competitors, niche=niche,
                )

                # Emit fact verification SSE events
                if fact_link_result:
                    fv = fact_link_result.get("fact_verification", {})
                    total_checked = fv.get("total_checked", 0)
                    fv_verified = fv.get("verified", 0)
                    fv_unverifiable = fv.get("unverifiable", 0)
                    fv_corrected = fv.get("corrected", 0)

                    if total_checked > 0:
                        yield f"data: {json.dumps({'event': 'fact_verification_complete', 'message': f'{fv_verified}/{total_checked} facts independently verified, {fv_unverifiable} unverifiable, {fv_corrected} corrected', 'verified': fv_verified, 'unverifiable': fv_unverifiable, 'corrected': fv_corrected, 'total_checked': total_checked})}\n\n"
                    else:
                        yield f"data: {json.dumps({'event': 'fact_verification_complete', 'message': 'All facts from trusted sources (Tier 1-2) - independent verification skipped', 'verified': 0, 'unverifiable': 0, 'corrected': 0, 'total_checked': 0})}\n\n"

                # Build source_content_map for post-writer claim cross-referencing
                source_content_map = {}
                for comp in elite_competitors:
                    url = comp.get("url", "")
                    content = comp.get("content", "")
                    if url and content:
                        source_content_map[url] = content
                # Fallback: fill gaps from VerifiedSource.content_snippet
                for vs in verified_sources:
                    if vs.url not in source_content_map and vs.content_snippet:
                        source_content_map[vs.url] = vs.content_snippet

                avg_credibility = sum(s.credibility_score for s in verified_sources) / len(verified_sources) if verified_sources else 0

                yield f"data: {json.dumps({'event': 'phase1_5_complete', 'verified_count': len(verified_sources), 'rejected_count': len(rejected_sources), 'avg_credibility': round(avg_credibility, 1)})}\n\n"

                if runtime["debug_mode"]:
                    yield f"data: {json.dumps({'event': 'debug', 'message': f'Phase 1.5 (Source Verification) completed in {round(time.time() - p1_5_start, 2)}s. Avg credibility: {round(avg_credibility, 1)}/100'})}\n\n"

                # Enrich research_result for downstream phases
                research_data_dict["verified_sources"] = [
                    {"title": s.title, "url": s.url, "credibility_score": s.credibility_score}
                    for s in verified_sources
                ]

                # Gap 15: Enrich with fact category distribution for psychology agent
                db = ensure_db_alive(db)
                fact_citations = db.query(FactCitation).filter_by(research_run_id=research_run_id).all()
                if fact_citations:
                    fact_type_counts = {}
                    for fc in fact_citations:
                        ft = fc.fact_type or "unknown"
                        fact_type_counts[ft] = fact_type_counts.get(ft, 0) + 1
                    research_data_dict["fact_categories"] = {
                        "distribution": fact_type_counts,
                        "total_facts": len(fact_citations),
                        "dominant_type": max(fact_type_counts, key=fact_type_counts.get),
                        "has_stats": fact_type_counts.get("stat", 0) > 0,
                        "has_case_studies": fact_type_counts.get("case_study", 0) > 0,
                        "has_expert_quotes": fact_type_counts.get("expert_quote", 0) > 0,
                    }
            else:
                if runtime["debug_mode"]:
                    yield f"data: {json.dumps({'event': 'debug', 'message': 'Phase 1.5 skipped: No elite competitors found in research'})}\n\n"

            # Phase 2
            yield f"data: {json.dumps({'event': 'phase2_start', 'message': 'Mapping psychological blueprint...'})}\n\n"
            p2_start = time.time()
            psychology_agent = PsychologyAgent(db=db) 
            blueprint_dict = await psychology_agent.generate_blueprint(research_data_dict)
            yield f"data: {json.dumps({'event': 'phase2_complete', 'blueprint': blueprint_dict})}\n\n"
            if runtime["debug_mode"]:
                yield f"data: {json.dumps({'event': 'debug', 'message': f'Phase 2 (DeepSeek-V3) completed in {round(time.time() - p2_start, 2)}s'})}\n\n"

            # Phase 3
            yield f"data: {json.dumps({'event': 'phase3_start', 'message': 'Drafting final prose...'})}\n\n"
            p3_start = time.time()
            writer_service = WriterService(db=db)
            article_content = ""
            readability_scores = None
            run_id = research_data_dict.get("research_run_id")
            async for result in writer_service.produce_article(blueprint_dict, payload.profile_name, normalize_niche(payload.niche), research_run_id=run_id, source_content_map=source_content_map, settings_override=runtime):
                if result.get("type") == "content":
                    yield f"data: {json.dumps({'event': 'content', 'data': result['data']})}\n\n"
                elif result.get("type") == "debug":
                    yield f"data: {json.dumps({'event': 'debug', 'message': result['message']})}\n\n"
                elif result.get("type") == "control":
                    yield f"data: {json.dumps({'event': 'control', 'action': result.get('action', '')})}\n\n"
                elif result.get("status") == "error":
                    yield f"data: {json.dumps({'event': 'error', 'message': result['message']})}\n\n"
                    return
                elif result.get("status") == "success":
                    article_content = result["text"]
                    readability_scores = result.get("readability_score")  # Extract readability scores

            # Fix 5: Fallback readability if all writer iterations failed at SEO gate
            if article_content and not readability_scores:
                from .services.readability_service import analyze_readability
                fallback_read = analyze_readability(article_content)
                if fallback_read and fallback_read.passed is not None:
                    readability_scores = {
                        "ari": fallback_read.ari_grade,
                        "fk": fallback_read.flesch_kincaid_grade,
                        "cli": fallback_read.coleman_liau_grade,
                        "avg_sentence_length": fallback_read.avg_sentence_length,
                    }

            if runtime["debug_mode"]:
                yield f"data: {json.dumps({'event': 'debug', 'message': f'Phase 3 (Claude Sonnet 4) completed in {round(time.time() - p3_start, 2)}s'})}\n\n"

            # Phase 4: Post-Writer Claim Verification Gate
            # Initialize claim verification variables for telemetry (may not run if no research)
            xref_result = None
            uncited_count = None
            claim_gate_failed = None

            if article_content and research_run_id:
                from .services.claim_verification_agent import (
                    extract_article_claims,
                    detect_uncited_claims,
                    cross_reference_claims,
                    verify_claim_with_llm,
                    format_claim_verification_feedback,
                )
                from .settings import MAX_UNCITED_CLAIMS

                yield f"data: {json.dumps({'event': 'claim_verification_start', 'message': 'Cross-referencing claims against verified facts...'})}\n\n"

                article_claims = extract_article_claims(article_content, verify_qualitative=runtime["verify_qualitative_claims"])

                # Attribution-URL mismatch detection: flag "Gartner says X" linked to random-blog.com
                from .services.source_verification_service import KNOWN_RESEARCH_ORGS, extract_domain
                import re as _re
                _org_pattern = _re.compile(
                    r'\b(' + '|'.join(_re.escape(org) for org in sorted(KNOWN_RESEARCH_ORGS.keys(), key=len, reverse=True)) + r')\b',
                    _re.IGNORECASE,
                )
                attribution_mismatches = []
                for claim in article_claims:
                    matches = _org_pattern.findall(claim.get("claim_text", ""))
                    if not matches:
                        matches = _org_pattern.findall(claim.get("citation_anchor", ""))
                    if matches:
                        cite_domain = extract_domain(claim.get("citation_url", ""))
                        for org_name in matches:
                            org_key = org_name.lower()
                            canonical_domains = KNOWN_RESEARCH_ORGS.get(org_key, [])
                            if not canonical_domains:
                                continue
                            if not any(cite_domain == cd or cite_domain.endswith("." + cd) for cd in canonical_domains):
                                attribution_mismatches.append({
                                    "claim_text": claim["claim_text"][:120],
                                    "named_org": org_key,
                                    "citation_url": claim["citation_url"],
                                    "citation_domain": cite_domain,
                                })
                                break

                uncited_claims = detect_uncited_claims(article_content, article_claims, verify_qualitative=runtime["verify_qualitative_claims"])

                # Fetch fact citations for this research run
                db = ensure_db_alive(db)
                run_fact_citations = db.query(FactCitation).filter_by(research_run_id=research_run_id).all()

                xref_result = cross_reference_claims(
                    article_claims, run_fact_citations, source_content_map
                )

                # Resolve ambiguous claims via LLM (max 2 calls)
                ambiguous = xref_result.get("ambiguous_claims", [])
                llm_resolved = 0
                for amb in ambiguous[:2]:
                    try:
                        llm_verdict = await verify_claim_with_llm(
                            amb["claim_text"],
                            amb.get("candidate_facts", []),
                            source_content_map.get(amb.get("source_url", ""), "")[:5000] if source_content_map else None,
                        )
                        if llm_verdict.get("supported"):
                            xref_result["verified"] = xref_result.get("verified", 0) + 1
                            xref_result["ambiguous"] = max(0, xref_result.get("ambiguous", 0) - 1)
                            llm_resolved += 1
                            # Update the detail entry
                            for d in xref_result.get("details", []):
                                if d.get("claim_text") == amb["claim_text"] and d.get("status") == "ambiguous":
                                    d["status"] = "verified"
                                    d["reason"] = f"LLM verified: {llm_verdict.get('reasoning', '')}"
                                    break
                    except Exception as e:
                        logger.warning(f"[CLAIM-VERIFY] LLM verification failed: {e}")

                # Add uncited claims and attribution mismatches to the result
                xref_result["uncited"] = len(uncited_claims)
                xref_result["uncited_details"] = uncited_claims
                xref_result["attribution_mismatches"] = attribution_mismatches

                fabricated = xref_result.get("fabricated", 0)
                ungrounded = xref_result.get("ungrounded", 0)
                uncited_count = len(uncited_claims)
                mismatch_count = len(attribution_mismatches)
                verified_count = xref_result.get("verified", 0)
                total_claims = xref_result.get("total_claims", 0)

                if mismatch_count:
                    logger.warning(f"[CLAIM-VERIFY] {mismatch_count} attribution-URL mismatches: {[m['named_org'] + ' -> ' + m['citation_domain'] for m in attribution_mismatches[:3]]}")

                yield f"data: {json.dumps({'event': 'claim_verification_complete', 'message': f'Claims: {verified_count}/{total_claims} verified, {fabricated} fabricated, {ungrounded} ungrounded, {uncited_count} uncited, {mismatch_count} attribution mismatches', 'verified': verified_count, 'fabricated': fabricated, 'ungrounded': ungrounded, 'uncited': uncited_count, 'mismatches': mismatch_count, 'total': total_claims})}\n\n"

                # Gate: reject if fabricated citations, too many uncited claims, or attribution mismatches
                claim_gate_failed = fabricated > 0 or uncited_count > MAX_UNCITED_CLAIMS or mismatch_count > 0
                claim_retry_count = 0
                max_claim_retries = 2

                while claim_gate_failed and claim_retry_count < max_claim_retries:
                    claim_retry_count += 1
                    feedback = format_claim_verification_feedback(xref_result)
                    logger.warning(f"[CLAIM-VERIFY] Gate failed (attempt {claim_retry_count}/{max_claim_retries}): {fabricated} fabricated, {uncited_count} uncited. Sending feedback to writer.")
                    yield f"data: {json.dumps({'event': 'claim_verification_retry', 'message': f'Claim verification failed. Retrying writer (attempt {claim_retry_count}/{max_claim_retries})...'})}\n\n"

                    # Re-run writer with claim feedback
                    article_content = ""
                    async for result in writer_service.produce_article(
                        blueprint_dict, payload.profile_name, normalize_niche(payload.niche),
                        research_run_id=run_id, source_content_map=source_content_map,
                        claim_feedback=feedback, settings_override=runtime,
                    ):
                        if result.get("type") == "content":
                            yield f"data: {json.dumps({'event': 'content', 'data': result['data']})}\n\n"
                        elif result.get("type") == "debug":
                            yield f"data: {json.dumps({'event': 'debug', 'message': result['message']})}\n\n"
                        elif result.get("type") == "control":
                            yield f"data: {json.dumps({'event': 'control', 'action': result.get('action', '')})}\n\n"
                        elif result.get("status") == "error":
                            yield f"data: {json.dumps({'event': 'error', 'message': result['message']})}\n\n"
                            return
                        elif result.get("status") == "success":
                            article_content = result["text"]
                            readability_scores = result.get("readability_score")

                    if not article_content:
                        break

                    # Re-verify
                    article_claims = extract_article_claims(article_content, verify_qualitative=runtime["verify_qualitative_claims"])
                    # Re-check attribution mismatches
                    attribution_mismatches = []
                    for claim in article_claims:
                        matches = _org_pattern.findall(claim.get("claim_text", ""))
                        if not matches:
                            matches = _org_pattern.findall(claim.get("citation_anchor", ""))
                        if matches:
                            cite_domain = extract_domain(claim.get("citation_url", ""))
                            for org_name in matches:
                                org_key = org_name.lower()
                                canonical_domains = KNOWN_RESEARCH_ORGS.get(org_key, [])
                                if not canonical_domains:
                                    continue
                                if not any(cite_domain == cd or cite_domain.endswith("." + cd) for cd in canonical_domains):
                                    attribution_mismatches.append({
                                        "claim_text": claim["claim_text"][:120],
                                        "named_org": org_key,
                                        "citation_url": claim["citation_url"],
                                        "citation_domain": cite_domain,
                                    })
                                    break

                    uncited_claims = detect_uncited_claims(article_content, article_claims, verify_qualitative=runtime["verify_qualitative_claims"])
                    xref_result = cross_reference_claims(
                        article_claims, run_fact_citations, source_content_map
                    )
                    xref_result["uncited"] = len(uncited_claims)
                    xref_result["uncited_details"] = uncited_claims
                    xref_result["attribution_mismatches"] = attribution_mismatches

                    fabricated = xref_result.get("fabricated", 0)
                    ungrounded = xref_result.get("ungrounded", 0)
                    uncited_count = len(uncited_claims)
                    mismatch_count = len(attribution_mismatches)
                    verified_count = xref_result.get("verified", 0)
                    total_claims = xref_result.get("total_claims", 0)

                    claim_gate_failed = fabricated > 0 or uncited_count > MAX_UNCITED_CLAIMS or mismatch_count > 0

                    yield f"data: {json.dumps({'event': 'claim_verification_complete', 'message': f'Retry {claim_retry_count}: {verified_count}/{total_claims} verified, {fabricated} fabricated, {uncited_count} uncited, {mismatch_count} mismatches', 'verified': verified_count, 'fabricated': fabricated, 'ungrounded': ungrounded, 'uncited': uncited_count, 'mismatches': mismatch_count, 'total': total_claims})}\n\n"

                if claim_gate_failed:
                    if runtime["claim_gate_hard_block"]:
                        logger.error(f"[CLAIM-VERIFY] Gate still failing after {max_claim_retries} retries. BLOCKING article save.")
                        yield f"data: {json.dumps({'event': 'error', 'message': f'Article rejected: claim verification failed after {max_claim_retries} retries. {fabricated} fabricated, {uncited_count} uncited, {mismatch_count} attribution mismatches. Article NOT saved.'})}\n\n"
                        return
                    else:
                        logger.error(f"[CLAIM-VERIFY] Gate still failing after {max_claim_retries} retries. Proceeding with warnings.")
                        yield f"data: {json.dumps({'event': 'claim_verification_warning', 'message': f'WARNING: Article has {fabricated} fabricated and {uncited_count} uncited claims after {max_claim_retries} retries. Review carefully.'})}\n\n"

            # Save the generated article
            post = Post(
                title=keyword,
                content=article_content,
                original_ai_content=article_content,
                profile_name=payload.profile_name,
                niche=normalize_niche(payload.niche),
                readability_score=readability_scores,  # Save readability analytics
            )
            # Clear any dirty transaction state from prior queries (e.g. claim verification DB errors)
            try:
                db.rollback()
            except Exception:
                pass
            db = ensure_db_alive(db)
            db.add(post)
            db.commit()
            db.refresh(post)

            # Capture WriterRun telemetry for learning loop
            if readability_scores:
                writer_run = WriterRun(
                    profile_name=payload.profile_name,
                    niche=normalize_niche(payload.niche),
                    post_id=post.id,
                    ari_score=readability_scores["ari"],
                    flesch_kincaid_score=readability_scores["fk"],
                    coleman_liau_score=readability_scores["cli"],
                    avg_sentence_length=readability_scores["avg_sentence_length"],
                    # Claim verification telemetry
                    claims_verified=xref_result.get("verified", 0) if xref_result else None,
                    claims_fabricated=xref_result.get("fabricated", 0) if xref_result else None,
                    claims_uncited=uncited_count if uncited_count is not None else None,
                    claims_total=xref_result.get("total_claims", 0) if xref_result else None,
                    claim_gate_passed=not claim_gate_failed if claim_gate_failed is not None else None,
                )
                db.add(writer_run)
                db.commit()

            # Link Post ↔ ResearchRun for quality scoring feedback loop
            run_id = research_data_dict.get("research_run_id")
            if run_id:
                db = ensure_db_alive(db)
                post = db.merge(post)
                post.research_run_id = run_id
                research_run = db.get(ResearchRun, run_id)
                if research_run:
                    research_run.post_id = post.id
                db.commit()
                db.refresh(post)

            logger.info(f"[ARES] Generation complete for: {keyword}")
            
            # Use model_dump or dictionary access to serialize the SQLAlchemy object safely
            # Since standard Post output might not be directly JSON serializable without a Pydantic model conversion
            from .schemas import PostResponse
            post_schema = PostResponse.model_validate(post).model_dump(mode='json')
            
            if runtime["debug_mode"]:
                total_time = round(time.time() - start_time, 2)
                yield f"data: {json.dumps({'event': 'debug', 'message': f'Total Engine Execution Time: {total_time}s'})}\n\n"

            final_payload = {
                'event': 'complete',
                'post': post_schema,
                'blueprint': blueprint_dict
            }
            yield f"data: {json.dumps(final_payload)}\n\n"
            
        except Exception as e:
            error_msg = str(e)
            if runtime["debug_mode"]:
                tb = traceback.format_exc()
                logger.error(f"[CRITICAL ERROR TRACEBACK]\n{tb}")
                error_msg = f"{str(e)} | Check backend terminal for full traceback."
            else:
                logger.error(f"[ARES] Generation Error: {e}")
            yield f"data: {json.dumps({'event': 'error', 'message': error_msg})}\n\n"
        finally:
            # If db was reassigned via SSL retry (nonlocal db = SessionLocal()),
            # the original get_db() dependency won't close it. Close explicitly.
            try:
                db.close()
            except Exception:
                pass

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Health check (Synchronized with console.js checkSystemStatus)
# ---------------------------------------------------------------------------

@app.get("/health")
async def health_check():
    """Check if DeepSeek API and Exa.ai API are reachable concurrently."""
    import httpx
    import asyncio
    from .settings import DEEPSEEK_API_KEY, EXA_API_KEY
    from .services.research_service import DEEPSEEK_API_URL

    deepseek_ok = False
    exa_ok = False

    async def check_deepseek():
        if not DEEPSEEK_API_KEY:
            return False
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(
                    "https://api.deepseek.com/models",
                    headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}"}
                )
                return resp.status_code == 200
        except Exception:
            return False

    async def check_exa():
        if not EXA_API_KEY:
            return False
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.post(
                    "https://api.exa.ai/search",
                    headers={"x-api-key": EXA_API_KEY, "Content-Type": "application/json"},
                    json={"query": "health", "type": "auto", "num_results": 1}
                )
                return resp.status_code == 200
        except Exception:
            return False

    deepseek_ok, exa_ok = await asyncio.gather(check_deepseek(), check_exa())

    # Return structure matching what console.js expects
    return {
        "status": "online" if (deepseek_ok and exa_ok) else "degraded", 
        "exa_search": exa_ok,
        "deepseek": deepseek_ok
    }

# ---------------------------------------------------------------------------
# Static files & frontend
# ---------------------------------------------------------------------------

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

@app.get("/")
async def serve_console():
    return FileResponse(str(STATIC_DIR / "ares_console.html"))

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")