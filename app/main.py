import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# Configure logging so INFO-level messages (scoring breakdowns, verified sources) are visible
logging.basicConfig(level=logging.INFO)

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

from sqlalchemy.exc import OperationalError
from .database import Base, engine, get_db, migrate_research_cache, migrate_posts_readability, migrate_writer_learning, migrate_source_verification, migrate_composite_scoring, migrate_fact_consensus, SessionLocal
from .models import Post, ResearchRun, UserStyleRule, Workspace, WriterRun
from .schemas import (
    BlueprintResponse,
    GenerateFullResponse,
    PostCreate,
    PostResponse,
    PostUpdate,
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
    in the background so the user's browser doesn't have to wait for Gemini to extract style rules.
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

@app.post("/generate/{keyword:path}")
async def generate_article(keyword: str, payload: GeneratePayload, request: Request, db: Session = Depends(get_db)):
    from .services.psychology_agent import PsychologyAgent
    from .services.writer_service import WriterService
    from .settings import DEBUG_MODE
    import time
    import traceback

    niche = payload.niche
    context = payload.context

    print(f"[ARES] Starting unified generation for: {keyword} (niche: {niche})")

    async def event_generator():
        nonlocal db
        start_time = time.time()
        try:
            if DEBUG_MODE:
                yield f"data: {json.dumps({'event': 'debug', 'message': f'Initializing Generation Sequence. Context: {bool(context)}'})}\n\n"
            # Phase 1
            yield f"data: {json.dumps({'event': 'phase1_start', 'message': 'Gathering intelligence and analyzing context...'})}\n\n"
            p1_start = time.time()
            research_agent = ResearchAgent(db)
            research_data_dict = await research_agent.research(
                keyword, 
                niche=niche, 
                user_context=context, 
                profile_name=payload.profile_name,
                mcp_session=request.app.state.mcp_session
            )
            if DEBUG_MODE:
                yield f"data: {json.dumps({'event': 'debug', 'message': f'Phase 1 (DeepSeek-R1 + MCP) completed in {round(time.time() - p1_start, 2)}s'})}\n\n"
            
            tools_used = research_data_dict.get("executed_tools", [])
            if DEBUG_MODE and tools_used:
                tools_str = ", ".join(tools_used)
                yield f"data: {json.dumps({'event': 'debug', 'message': f'MCP Tools Executed: {tools_str}'})}\n\n"

            # Phase 1.5 - Source Verification
            elite_competitors = research_data_dict.get("elite_competitors", [])
            research_run_id = research_data_dict.get("research_run_id", 0)

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
                )

                verified_sources = verification_result["verified_sources"]
                rejected_sources = verification_result["rejected_sources"]

                if DEBUG_MODE:
                    for i, source in enumerate(verified_sources):
                        yield f"data: {json.dumps({'event': 'source_verification', 'source_title': source.title, 'domain': source.domain, 'credibility_score': round(source.credibility_score, 1), 'progress': f'{i+1}/{len(elite_competitors)}'})}\n\n"

                # Backfill if < 3 verified sources
                if len(verified_sources) < 3:
                    yield f"data: {json.dumps({'event': 'source_backfill_start', 'message': f'Only {len(verified_sources)} credible sources found. Searching for alternatives...'})}\n\n"

                    rejected_domains = list({s["domain"] for s in rejected_sources})
                    seen_urls = {s.url for s in verified_sources} | {s["url"] for s in rejected_sources}

                    # Step 1: Try Find Similar from highest-scoring verified source
                    if verified_sources:
                        from datetime import datetime as dt_now, timedelta as td
                        from .services.research_service import EXA_EXCLUDE_DOMAINS

                        best_source = max(verified_sources, key=lambda s: s.credibility_score)
                        if DEBUG_MODE:
                            seed_msg = f"FindSimilar: Using seed URL {best_source.url} (score: {round(best_source.credibility_score, 1)})"
                            yield f"data: {json.dumps({'event': 'debug', 'message': seed_msg})}\n\n"

                        two_years_ago = (dt_now.now() - td(days=730)).strftime('%Y-%m-%d')
                        similar_results = await research_agent.exa_find_similar(
                            url=best_source.url,
                            num_results=5,
                            exclude_domains=list(EXA_EXCLUDE_DOMAINS) + rejected_domains,
                            start_published_date=two_years_ago,
                        )
                        # Find Similar returns search-like results; fetch full text for verification
                        similar_ids = [r.get("id") for r in similar_results if r.get("id") and not r.get("error")]
                        if similar_ids:
                            similar_articles = await research_agent.exa_extract_full_text(similar_ids)
                            similar_new = [s for s in similar_articles if s.get("url") not in seen_urls and not s.get("error")]
                            if similar_new:
                                similar_verification = await verify_sources(
                                    elite_competitors=similar_new,
                                    db=db,
                                    profile_name=payload.profile_name,
                                    research_run_id=research_run_id,
                                    mcp_session=request.app.state.mcp_session,
                                    keyword=keyword,
                                )
                                verified_sources.extend(similar_verification["verified_sources"])
                                rejected_sources.extend(similar_verification["rejected_sources"])
                                elite_competitors.extend(similar_new)
                                seen_urls.update(s.get("url") for s in similar_new)
                                if DEBUG_MODE:
                                    fs_count = len(similar_verification["verified_sources"])
                                    yield f"data: {json.dumps({'event': 'debug', 'message': f'FindSimilar added {fs_count} verified sources'})}\n\n"

                    # Step 2: Niche-filtered backfill (authoritative domains only)
                    if len(verified_sources) < 3:
                        niche_backfill_results = await research_agent.niche_filtered_backfill(keyword, niche, rejected_domains)
                        niche_new = [s for s in niche_backfill_results if s.get("url") not in seen_urls]

                        if niche_new:
                            niche_verification = await verify_sources(
                                elite_competitors=niche_new,
                                db=db,
                                profile_name=payload.profile_name,
                                research_run_id=research_run_id,
                                mcp_session=request.app.state.mcp_session,
                                keyword=keyword,
                            )
                            verified_sources.extend(niche_verification["verified_sources"])
                            rejected_sources.extend(niche_verification["rejected_sources"])
                            elite_competitors.extend(niche_new)
                            seen_urls.update(s.get("url") for s in niche_new)
                            if DEBUG_MODE:
                                nb_count = len(niche_verification["verified_sources"])
                                yield f"data: {json.dumps({'event': 'debug', 'message': f'Niche backfill added {nb_count} verified sources'})}\n\n"

                    # Step 3: Broad search fallback if still < 3
                    if len(verified_sources) < 3:
                        backfill_results = await research_agent.backfill_search(keyword, niche, rejected_domains)
                        new_sources = [s for s in backfill_results if s.get("url") not in seen_urls]

                        if new_sources:
                            backfill_verification = await verify_sources(
                                elite_competitors=new_sources,
                                db=db,
                                profile_name=payload.profile_name,
                                research_run_id=research_run_id,
                                mcp_session=request.app.state.mcp_session,
                                keyword=keyword,
                            )
                            verified_sources.extend(backfill_verification["verified_sources"])
                            rejected_sources.extend(backfill_verification["rejected_sources"])
                            elite_competitors.extend(new_sources)  # Merge for fact extraction

                    backfill_found = len(verified_sources)
                    yield f"data: {json.dumps({'event': 'source_backfill_complete', 'message': f'Backfill complete: {backfill_found} total verified sources', 'verified_count': backfill_found})}\n\n"

                    # Final gate — still fail if <3 after backfill
                    if len(verified_sources) < 3:
                        error_msg = f"Insufficient credible sources after backfill: only {len(verified_sources)} found (need 3 minimum). Rejected: {len(rejected_sources)} sources."
                        yield f"data: {json.dumps({'event': 'error', 'message': error_msg})}\n\n"
                        return

                # Extract facts and link to sources (pass full content for better extraction)
                await link_facts_to_sources(verified_sources, research_run_id, db, elite_competitors=elite_competitors)

                avg_credibility = sum(s.credibility_score for s in verified_sources) / len(verified_sources) if verified_sources else 0

                yield f"data: {json.dumps({'event': 'phase1_5_complete', 'verified_count': len(verified_sources), 'rejected_count': len(rejected_sources), 'avg_credibility': round(avg_credibility, 1)})}\n\n"

                if DEBUG_MODE:
                    yield f"data: {json.dumps({'event': 'debug', 'message': f'Phase 1.5 (Source Verification) completed in {round(time.time() - p1_5_start, 2)}s. Avg credibility: {round(avg_credibility, 1)}/100'})}\n\n"

                # Enrich research_result for downstream phases
                research_data_dict["verified_sources"] = [
                    {"title": s.title, "url": s.url, "credibility_score": s.credibility_score}
                    for s in verified_sources
                ]
            else:
                if DEBUG_MODE:
                    yield f"data: {json.dumps({'event': 'debug', 'message': 'Phase 1.5 skipped: No elite competitors found in research'})}\n\n"

            # Phase 2
            yield f"data: {json.dumps({'event': 'phase2_start', 'message': 'Mapping psychological blueprint...'})}\n\n"
            p2_start = time.time()
            psychology_agent = PsychologyAgent(db=db) 
            blueprint_dict = await psychology_agent.generate_blueprint(research_data_dict)
            yield f"data: {json.dumps({'event': 'phase2_complete', 'blueprint': blueprint_dict})}\n\n"
            if DEBUG_MODE:
                yield f"data: {json.dumps({'event': 'debug', 'message': f'Phase 2 (DeepSeek-V3) completed in {round(time.time() - p2_start, 2)}s'})}\n\n"

            # Phase 3
            yield f"data: {json.dumps({'event': 'phase3_start', 'message': 'Drafting final prose...'})}\n\n"
            p3_start = time.time()
            writer_service = WriterService(db=db)
            article_content = ""
            run_id = research_data_dict.get("research_run_id")
            async for result in writer_service.produce_article(blueprint_dict, payload.profile_name, normalize_niche(payload.niche), research_run_id=run_id):
                if result.get("type") == "content":
                    yield f"data: {json.dumps({'event': 'content', 'data': result['data']})}\n\n"
                elif result.get("type") == "debug":
                    yield f"data: {json.dumps({'event': 'debug', 'message': result['message']})}\n\n"
                elif result.get("status") == "error":
                    yield f"data: {json.dumps({'event': 'error', 'message': result['message']})}\n\n"
                    return
                elif result.get("status") == "success":
                    article_content = result["text"]
                    readability_scores = result.get("readability_score")  # Extract readability scores

            if DEBUG_MODE:
                yield f"data: {json.dumps({'event': 'debug', 'message': f'Phase 3 (Claude 3.5 Sonnet) completed in {round(time.time() - p3_start, 2)}s'})}\n\n"

            # Save the generated article
            post = Post(
                title=keyword,
                content=article_content,
                original_ai_content=article_content,
                profile_name=payload.profile_name,
                niche=normalize_niche(payload.niche),
                readability_score=readability_scores,  # Save readability analytics
            )
            db.add(post)
            try:
                db.commit()
            except OperationalError:
                db.rollback()
                db.close()
                db = SessionLocal()
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
                    avg_sentence_length=readability_scores["avg_sentence_length"]
                )
                db.add(writer_run)
                db.commit()

            # Link Post ↔ ResearchRun for quality scoring feedback loop
            run_id = research_data_dict.get("research_run_id")
            if run_id:
                post.research_run_id = run_id
                research_run = db.get(ResearchRun, run_id)
                if research_run:
                    research_run.post_id = post.id
                try:
                    db.commit()
                except OperationalError:
                    db.rollback()
                    db.close()
                    db = SessionLocal()
                    post = db.merge(post)
                    research_run = db.get(ResearchRun, run_id) if run_id else None
                    if research_run:
                        research_run.post_id = post.id
                    post.research_run_id = run_id
                    db.commit()
                db.refresh(post)

            print(f"[ARES] Generation complete for: {keyword}")
            
            # Use model_dump or dictionary access to serialize the SQLAlchemy object safely
            # Since standard Post output might not be directly JSON serializable without a Pydantic model conversion
            from .schemas import PostResponse
            post_schema = PostResponse.model_validate(post).model_dump(mode='json')
            
            if DEBUG_MODE:
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
            if DEBUG_MODE:
                tb = traceback.format_exc()
                print(f"\n[CRITICAL ERROR TRACEBACK]\n{tb}\n")
                error_msg = f"{str(e)} | Check backend terminal for full traceback."
            else:
                print(f"[ARES] Generation Error: {e}")
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