import os
import asyncio
import logging
from pathlib import Path
from dotenv import load_dotenv

# Configure logging so INFO-level messages (scoring breakdowns, verified sources) are visible
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ensure environment is loaded BEFORE importing services
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

import hashlib
import secrets

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from contextlib import asynccontextmanager, AsyncExitStack
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded

from .auth import verify_api_key
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .database import Base, engine, get_db, ensure_db_alive, migrate_research_cache, migrate_posts_readability, migrate_writer_learning, migrate_source_verification, migrate_composite_scoring, migrate_fact_consensus, migrate_domain_credibility_cache, migrate_fact_verification, migrate_style_rule_archive, migrate_writer_verification_telemetry, migrate_profile_settings, migrate_fk_constraints, migrate_version_tracking, migrate_api_keys, record_all_migrations, SessionLocal
from .models import Post, ProfileSettings, ResearchRun, UserStyleRule, Workspace, WriterRun, FactCitation, ApiKey
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
migrate_version_tracking()
migrate_api_keys()
Base.metadata.create_all(bind=engine)
migrate_fk_constraints()
record_all_migrations()

def normalize_niche(niche: str | None) -> str:
    """Single source of truth for niche normalization."""
    if not niche:
        return "general"
    return niche.strip().lower().replace(" ", "-")

def _normalize_url(url: str) -> str:
    """Normalize URL for consistent source_content_map keying."""
    from urllib.parse import urlparse, urlunparse
    try:
        parsed = urlparse(url)
        netloc = parsed.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        path = parsed.path.rstrip("/") or "/"
        return urlunparse((parsed.scheme, netloc, path, "", "", ""))
    except Exception:
        return url

@asynccontextmanager
async def lifespan(app: FastAPI):
    # MCP session initialization for DataForSEO (used by ResearchAgent)
    # Note: Source verification uses tiered domain lists (no MCP needed there)
    from .settings import DATAFORSEO_LOGIN, DATAFORSEO_PASSWORD

    server_params = StdioServerParameters(
        command="node",
        args=[
            "mcp-dataforseo-server/index.js",
        ],
        env={
            "DATAFORSEO_LOGIN": DATAFORSEO_LOGIN,
            "DATAFORSEO_PASSWORD": DATAFORSEO_PASSWORD,
            "PATH": os.environ.get("PATH", ""),
            "NODE_PATH": os.environ.get("NODE_PATH", ""),
        }
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

# --- Security Headers Middleware ---
from starlette.middleware.base import BaseHTTPMiddleware

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "connect-src 'self'; "
            "img-src 'self' data:; "
            "frame-ancestors 'none'"
        )
        return response

app.add_middleware(SecurityHeadersMiddleware)

# --- Rate Limiting ---

def _rate_limit_key(request: Request) -> str:
    api_key = request.headers.get('X-API-Key', '')
    if api_key:
        return hashlib.sha256(api_key.encode()).hexdigest()[:16]
    return request.client.host if request.client else "unknown"

limiter = Limiter(key_func=_rate_limit_key)
app.state.limiter = limiter

@app.exception_handler(RateLimitExceeded)
async def _rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded. Try again later."})

# --- CRUD Endpoints ---

@app.get("/posts", response_model=list[PostResponse])
def list_posts(skip: int = 0, limit: int = 20, profile_name: str = Depends(verify_api_key), db: Session = Depends(get_db)):
    return db.query(Post).filter(Post.profile_name == profile_name).offset(skip).limit(limit).all()

@app.get("/posts/{post_id}", response_model=PostResponse)
def get_post(post_id: int, profile_name: str = Depends(verify_api_key), db: Session = Depends(get_db)):
    post = db.query(Post).filter(Post.id == post_id, Post.profile_name == profile_name).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return post

@app.post("/posts", response_model=PostResponse, status_code=201)
def create_post(data: PostCreate, profile_name: str = Depends(verify_api_key), db: Session = Depends(get_db)):
    post = Post(**{**data.model_dump(), "profile_name": profile_name})
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
    profile_name: str = Depends(verify_api_key),
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
def get_style_rules(profile_name: str = Depends(verify_api_key), db: Session = Depends(get_db)):
    """Fetch all learned style rules from the AI's memory."""
    return db.query(UserStyleRule).filter(UserStyleRule.profile_name == profile_name).order_by(UserStyleRule.id.desc()).all()

@app.post("/rules", response_model=StyleRuleResponse)
def add_style_rule(rule: StyleRuleCreate, profile_name: str = Depends(verify_api_key), db: Session = Depends(get_db)):
    """Manually inject a new style rule into the AI's memory."""
    new_rule = UserStyleRule(rule_description=rule.rule_description, profile_name=profile_name)
    db.add(new_rule)
    db.commit()
    db.refresh(new_rule)
    return new_rule

@app.delete("/rules/{rule_id}")
def delete_style_rule(rule_id: int, profile_name: str = Depends(verify_api_key), db: Session = Depends(get_db)):
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
def get_workspaces(_profile: str = Depends(verify_api_key), db: Session = Depends(get_db)):
    """Fetch all saved workspaces."""
    return db.query(Workspace).order_by(Workspace.name.asc()).all()

@app.post("/workspaces", response_model=WorkspaceResponse)
def create_workspace(workspace: WorkspaceCreate, _profile: str = Depends(verify_api_key), db: Session = Depends(get_db)):
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
def get_campaigns(profile_name: str = Depends(verify_api_key), db: Session = Depends(get_db)):
    """Fetch structured campaigns from DB."""
    service = CartographerService(db)
    return service.get_campaigns(profile_name)

@app.post("/campaigns/plan", response_model=CampaignResponse)
@limiter.limit("10/minute")
async def plan_campaign(req: CampaignCreateRequest, request: Request, _profile: str = Depends(verify_api_key), db: Session = Depends(get_db)):
    """Generate a Pillar/Spoke map via DataForSEO & DeepSeek."""
    service = CartographerService(db)
    return await service.plan_campaign(req.seed_topic, _profile, req.niche_context)

# --- Orchestration Endpoints ---

@app.get("/research/{keyword:path}", response_model=ResearchResponse)
@limiter.limit("10/minute")
async def research_keyword(keyword: str, request: Request, niche: str = "default", profile_name: str = Depends(verify_api_key), db: Session = Depends(get_db)):
    agent = ResearchAgent(db)
    return await agent.research(keyword, niche=niche, profile_name=profile_name)

@app.post("/blueprint", response_model=BlueprintResponse)
async def generate_blueprint(research_data: ResearchResponse, _profile: str = Depends(verify_api_key), db: Session = Depends(get_db)):
    from .services.psychology_agent import PsychologyAgent
    agent = PsychologyAgent(db=db) 
    # research_data is a Pydantic model here, so we dump it to a dict
    blueprint = await agent.generate_blueprint(research_data.model_dump())
    return blueprint

import json
from .schemas import GeneratePayload

@app.get("/clarify")
async def clarify_intent(keyword: str, _profile: str = Depends(verify_api_key)):
    from .services.briefing_agent import BriefingAgent
    agent = BriefingAgent()
    questions = await agent.get_clarifying_questions(keyword)
    return {"questions": questions}

# --- Settings Endpoints ---

@app.get("/settings", response_model=ProfileSettingsResponse)
def get_settings(profile_name: str = Depends(verify_api_key), db: Session = Depends(get_db)):
    from .settings import CONFIGURABLE_SETTINGS, resolve_settings
    row = db.query(ProfileSettings).filter_by(profile_name=profile_name).first()
    merged = resolve_settings(row)
    return ProfileSettingsResponse(
        profile_name=profile_name,
        settings=merged,
        configurable=CONFIGURABLE_SETTINGS,
    )

@app.put("/settings", response_model=ProfileSettingsResponse)
def update_settings(payload: ProfileSettingsUpdate, profile_name: str = Depends(verify_api_key), db: Session = Depends(get_db)):
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
@limiter.limit("5/minute")
async def generate_article(keyword: str, payload: GeneratePayload, request: Request, profile_name: str = Depends(verify_api_key), db: Session = Depends(get_db)):
    from .services.psychology_agent import PsychologyAgent
    from .services.writer_service import WriterService
    from .settings import CONFIGURABLE_SETTINGS, resolve_settings, EXA_RESEARCH_ENABLED, MAX_USER_CONTEXT_CHARS, RESEARCH_TIMEOUT, MAX_DAILY_GENERATIONS
    import time
    import traceback

    niche = payload.niche
    context = payload.context[:MAX_USER_CONTEXT_CHARS] if payload.context else None

    # Daily generation cap per profile
    from datetime import datetime, date
    today = date.today()
    gen_count = db.query(Post).filter(
        Post.profile_name == profile_name,
        Post.created_at >= datetime(today.year, today.month, today.day),
    ).count()
    if gen_count >= MAX_DAILY_GENERATIONS:
        raise HTTPException(status_code=429, detail=f"Daily generation limit ({MAX_DAILY_GENERATIONS}) reached for this profile.")

    # Resolve per-profile runtime settings (DB overrides + defaults)
    settings_row = db.query(ProfileSettings).filter_by(profile_name=profile_name).first()
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
                        profile_name=profile_name,
                        mcp_session=request.app.state.mcp_session,
                        settings_override=runtime,
                    ),
                    timeout=RESEARCH_TIMEOUT
                )
            except asyncio.TimeoutError:
                yield f"data: {json.dumps({'event': 'error', 'message': f'Research phase timed out after {RESEARCH_TIMEOUT}s. Try a more specific keyword or check your API connections.'})}\n\n"
                return
            if runtime["debug_mode"]:
                yield f"data: {json.dumps({'event': 'debug', 'message': f'Phase 1 (GLM-5 + MCP) completed in {round(time.time() - p1_start, 2)}s'})}\n\n"
            
            tools_used = research_data_dict.get("executed_tools", [])
            if runtime["debug_mode"] and tools_used:
                tools_str = ", ".join(tools_used)
                yield f"data: {json.dumps({'event': 'debug', 'message': f'MCP Tools Executed: {tools_str}'})}\n\n"

            # Phase 1.5 - Fact Discovery + Verification via Exa Research API
            elite_competitors = research_data_dict.get("elite_competitors", [])
            research_run_id = research_data_dict.get("research_run_id", 0)

            # Build source_content_map from Phase 1 raw articles (for post-writer claim gate)
            # URLs are normalized (strip www, query params, trailing slash) for consistent lookup
            source_content_map = {}
            for comp in elite_competitors:
                comp_url = comp.get("url", "")
                comp_content = comp.get("content", "")
                if comp_url and comp_content:
                    source_content_map[_normalize_url(comp_url)] = comp_content

            if research_run_id and EXA_RESEARCH_ENABLED:
                from .services.exa_research_service import research_facts, create_citations_from_research, ExaResearchError

                yield f"data: {json.dumps({'event': 'phase1_5_start', 'message': 'Researching and verifying facts...'})}\n\n"
                p1_5_start = time.time()

                try:
                    # Single async Research API call (~45-90s)
                    research_result = await research_facts(keyword=keyword, niche=niche)

                    cost = research_result.get("cost_dollars", 0)
                    num_facts = len(research_result.get("facts", []))
                    yield f"data: {json.dumps({'event': 'fact_verification_start', 'message': f'Processing {num_facts} verified facts (${cost:.3f})...'})}\n\n"

                    # Create VerifiedSource + FactCitation DB rows
                    db = ensure_db_alive(db)
                    citation_result = await create_citations_from_research(
                        research_result=research_result,
                        research_run_id=research_run_id,
                        profile_name=profile_name,
                        db=db,
                    )

                    verified_sources = citation_result["verified_sources"]
                    fact_citations = citation_result["fact_citations"]

                    # SSE: fact verification complete
                    yield f"data: {json.dumps({'event': 'fact_verification_complete', 'message': f'{len(fact_citations)} facts verified from {len(verified_sources)} authoritative sources', 'verified': len(fact_citations), 'unverifiable': 0, 'corrected': 0, 'total_checked': len(fact_citations)})}\n\n"

                    # Enrich research_data_dict for downstream phases
                    research_data_dict["verified_sources"] = [
                        {"title": s.title, "url": s.url, "credibility_score": s.credibility_score}
                        for s in verified_sources
                    ]
                    research_data_dict["fact_categories"] = citation_result["fact_categories"]

                    # CRITICAL-1 fix: Add Phase 1.5 fact texts to source_content_map
                    # so claim cross-referencing (Phase 4) can verify citations from Research API sources
                    for fact in research_result.get("facts", []):
                        fact_url = fact.get("source_url", "")
                        fact_text = fact.get("fact_text", "")
                        if fact_url and fact_text:
                            norm_url = _normalize_url(fact_url)
                            if norm_url not in source_content_map:
                                source_content_map[norm_url] = fact_text
                            else:
                                source_content_map[norm_url] += "\n" + fact_text

                    avg_credibility = (
                        sum(s.credibility_score for s in verified_sources) / len(verified_sources)
                    ) if verified_sources else 0

                    yield f"data: {json.dumps({'event': 'phase1_5_complete', 'verified_count': len(verified_sources), 'rejected_count': 0, 'avg_credibility': round(avg_credibility, 1)})}\n\n"

                    if runtime["debug_mode"]:
                        yield f"data: {json.dumps({'event': 'debug', 'message': f'Phase 1.5 (Exa Research) completed in {round(time.time() - p1_5_start, 2)}s. Cost: ${cost:.3f}. Facts: {len(fact_citations)}. source_content_map: {len(source_content_map)} URLs'})}\n\n"

                except (ExaResearchError, asyncio.TimeoutError) as e:
                    logger.error(f"[RESEARCH-API] Phase 1.5 failed (non-fatal): {e}")
                    yield f"data: {json.dumps({'event': 'phase1_5_warning', 'message': f'Fact research unavailable: {e}. Continuing with general research data.'})}\n\n"

            elif runtime["debug_mode"]:
                yield f"data: {json.dumps({'event': 'debug', 'message': 'Phase 1.5 skipped'})}\n\n"

            # Phase 2
            yield f"data: {json.dumps({'event': 'phase2_start', 'message': 'Mapping psychological blueprint...'})}\n\n"
            p2_start = time.time()
            psychology_agent = PsychologyAgent(db=db)
            try:
                blueprint_dict = await asyncio.wait_for(
                    psychology_agent.generate_blueprint(research_data_dict),
                    timeout=90
                )
            except asyncio.TimeoutError:
                yield f"data: {json.dumps({'event': 'error', 'message': 'Psychology blueprint timed out after 90s. Try again.'})}\n\n"
                return
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
            async for result in writer_service.produce_article(blueprint_dict, profile_name, normalize_niche(payload.niche), research_run_id=run_id, source_content_map=source_content_map, settings_override=runtime):
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
                from .settings import MAX_UNCITED_CLAIMS, MAX_CLAIM_RETRIES, MAX_UNGROUNDED_RATIO

                yield f"data: {json.dumps({'event': 'claim_verification_start', 'message': 'Cross-referencing claims against verified facts...'})}\n\n"

                article_claims = extract_article_claims(article_content, verify_qualitative=runtime["verify_qualitative_claims"])

                # Attribution-URL mismatch detection: flag "Gartner says X" linked to random-blog.com
                from .services.source_verification_service import detect_attribution_mismatches
                attribution_mismatches = detect_attribution_mismatches(article_claims)

                uncited_claims = detect_uncited_claims(article_content, article_claims, verify_qualitative=runtime["verify_qualitative_claims"])

                # Fetch fact citations for this research run
                db = ensure_db_alive(db)
                run_fact_citations = db.query(FactCitation).filter_by(research_run_id=research_run_id).all()

                # C-2 fix: skip claim verification if no fact citations exist (Phase 1.5 may have failed)
                if not run_fact_citations:
                    logger.warning("[CLAIM-VERIFY] No fact citations found for research run %s -- skipping claim verification (Phase 1.5 may have failed)", research_run_id)
                    yield f"data: {json.dumps({'event': 'claim_verification_complete', 'message': 'Claim verification skipped: no verified facts available (Phase 1.5 may have been unavailable)', 'verified': 0, 'fabricated': 0, 'ungrounded': 0, 'uncited': 0, 'mismatches': 0, 'total': 0})}\n\n"
                else:
                    xref_result = cross_reference_claims(
                        article_claims, run_fact_citations, source_content_map
                    )

                    # Resolve ambiguous claims via LLM (max 2 calls)
                    ambiguous = xref_result.get("ambiguous_claims", [])
                    llm_resolved = 0
                    for amb in ambiguous[:2]:
                        try:
                            claim_dict = amb["claim"]
                            llm_verdict = await verify_claim_with_llm(
                                claim_dict["claim_text"],
                                amb.get("candidate_facts", []),
                                source_content_map.get(claim_dict.get("citation_url", ""), "")[:5000] if source_content_map else None,
                            )
                            if llm_verdict.get("supported"):
                                xref_result["verified"] = xref_result.get("verified", 0) + 1
                                xref_result["ambiguous"] = max(0, xref_result.get("ambiguous", 0) - 1)
                                llm_resolved += 1
                                # Update the detail entry
                                for d in xref_result.get("details", []):
                                    if d.get("claim_text") == claim_dict["claim_text"] and d.get("status") == "ambiguous":
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

                    # Gate: reject if fabricated citations, too many uncited/ungrounded claims, or attribution mismatches
                    max_ungrounded = max(2, int(total_claims * MAX_UNGROUNDED_RATIO)) if total_claims > 0 else 2
                    claim_gate_failed = fabricated > 0 or uncited_count > MAX_UNCITED_CLAIMS or mismatch_count > 0 or ungrounded > max_ungrounded
                    claim_retry_count = 0
                    max_claim_retries = MAX_CLAIM_RETRIES

                    while claim_gate_failed and claim_retry_count < max_claim_retries:
                        claim_retry_count += 1
                        feedback = format_claim_verification_feedback(xref_result)
                        logger.warning(f"[CLAIM-VERIFY] Gate failed (attempt {claim_retry_count}/{max_claim_retries}): {fabricated} fabricated, {uncited_count} uncited. Sending feedback to writer.")
                        yield f"data: {json.dumps({'event': 'claim_verification_retry', 'message': f'Claim verification failed. Retrying writer (attempt {claim_retry_count}/{max_claim_retries})...'})}\n\n"

                        # Re-run writer with claim feedback
                        article_content = ""
                        async for result in writer_service.produce_article(
                            blueprint_dict, profile_name, normalize_niche(payload.niche),
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
                        attribution_mismatches = detect_attribution_mismatches(article_claims)

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

                        max_ungrounded = max(2, int(total_claims * MAX_UNGROUNDED_RATIO)) if total_claims > 0 else 2
                        claim_gate_failed = fabricated > 0 or uncited_count > MAX_UNCITED_CLAIMS or mismatch_count > 0 or ungrounded > max_ungrounded

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
                profile_name=profile_name,
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
                    profile_name=profile_name,
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
                db = ensure_db_alive(db)
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
            logger.error(f"[ARES] Generation Error: {e}")
            if runtime["debug_mode"]:
                tb = traceback.format_exc()
                logger.error(f"[CRITICAL ERROR TRACEBACK]\n{tb}")
            error_msg = "An internal error occurred during generation. Check backend logs for details."
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
# Admin: API Key Management
# ---------------------------------------------------------------------------

from pydantic import BaseModel as _PydanticBase

class _CreateApiKeyRequest(_PydanticBase):
    profile_name: str
    label: str = "default"

@app.post("/admin/api-keys")
def create_api_key(req: _CreateApiKeyRequest, request: Request, db: Session = Depends(get_db)):
    from .settings import ADMIN_SECRET
    if not ADMIN_SECRET:
        raise HTTPException(status_code=503, detail="ADMIN_SECRET not configured")
    admin_secret = request.headers.get("X-Admin-Secret")
    if not admin_secret or not secrets.compare_digest(admin_secret, ADMIN_SECRET):
        raise HTTPException(status_code=401, detail="Invalid admin secret")

    raw_key = secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    api_key = ApiKey(key_hash=key_hash, profile_name=req.profile_name, label=req.label)
    db.add(api_key)
    db.commit()

    return {"api_key": raw_key, "profile_name": req.profile_name, "label": req.label}

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
            from .exa_client import exa_search
            await exa_search({"query": "health", "type": "auto", "num_results": 1}, timeout=5)
            return True
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