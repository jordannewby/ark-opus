import os
from pathlib import Path
from dotenv import load_dotenv

# Ensure environment is loaded BEFORE importing services
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from contextlib import asynccontextmanager, AsyncExitStack
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .database import Base, engine, get_db
from .models import Post, ResearchRun, UserStyleRule, Workspace
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

Base.metadata.create_all(bind=engine)

@asynccontextmanager
async def lifespan(app: FastAPI):
    from .settings import DATAFORSEO_LOGIN, DATAFORSEO_PASSWORD
    import os
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
    
    async with AsyncExitStack() as stack:
        read, write = await stack.enter_async_context(stdio_client(server_params))
        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        app.state.mcp_session = session
        yield

app = FastAPI(title="Ares Engine Console", lifespan=lifespan)

# --- CRUD Endpoints ---

@app.get("/posts", response_model=list[PostResponse])
def list_posts(skip: int = 0, limit: int = 20, db: Session = Depends(get_db)):
    return db.query(Post).offset(skip).limit(limit).all()

@app.get("/posts/{post_id}", response_model=PostResponse)
def get_post(post_id: int, db: Session = Depends(get_db)):
    post = db.get(Post, post_id)
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
    db: Session = Depends(get_db)
):
    """
    Accepts the human-edited content, updates the database, and spins up the FeedbackAgent
    in the background so the user's browser doesn't have to wait for Gemini to extract style rules.
    """
    post = db.get(Post, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
        
    # The frontend should send the completely human-edited markdown as `data.content`
    if not data.content:
        return post

    # Only fire training if changes were actually made
    if post.original_ai_content and post.original_ai_content.strip() != data.content.strip():
        # Set human_edited_content strictly as the new baseline
        post.human_edited_content = data.content

        # Fire the style-learning background task
        from .services.feedback_service import FeedbackAgent
        agent = FeedbackAgent(db=db)
        background_tasks.add_task(
            agent.analyze_and_store_feedback,
            post.original_ai_content,
            data.content,
            post.profile_name
        )

        # Fire research quality scoring (edit-distance ratio → ResearchRun.quality_score)
        from .services.research_intel_service import ResearchIntelService
        intel_service = ResearchIntelService(db=db)
        background_tasks.add_task(
            intel_service.score_research_run,
            post_id,
            post.original_ai_content,
            data.content,
        )
    
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
def delete_style_rule(rule_id: int, db: Session = Depends(get_db)):
    """Delete a specific style rule from memory."""
    rule = db.get(UserStyleRule, rule_id)
    if not rule:
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

@app.get("/research/{keyword}", response_model=ResearchResponse)
async def research_keyword(keyword: str, niche: str = "default", db: Session = Depends(get_db)):
    agent = ResearchAgent(db)
    return await agent.research(keyword, niche=niche)

@app.post("/blueprint", response_model=BlueprintResponse)
async def generate_blueprint(research_data: ResearchResponse, db: Session = Depends(get_db)):
    from .services.psychology_agent import PsychologyAgent
    agent = PsychologyAgent(db=db) 
    # research_data is a Pydantic model here, so we dump it to a dict
    blueprint = await agent.generate_blueprint(research_data.model_dump())
    return blueprint

import json
from fastapi.responses import FileResponse, StreamingResponse
from .schemas import GeneratePayload

@app.get("/clarify")
async def clarify_intent(keyword: str):
    from .services.briefing_agent import BriefingAgent
    agent = BriefingAgent()
    questions = await agent.get_clarifying_questions(keyword)
    return {"questions": questions}

@app.post("/generate/{keyword}")
async def generate_article(keyword: str, payload: GeneratePayload, request: Request, db: Session = Depends(get_db)):
    from .services.psychology_agent import PsychologyAgent
    from .services.writer_service import WriterService
    from .settings import DEBUG_MODE
    import time
    import traceback

    niche = payload.niche
    context = payload.context

    print(f"🚀 [ARES] Starting unified generation for: {keyword} (niche: {niche})")

    async def event_generator():
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
            async for result in writer_service.produce_article(blueprint_dict, payload.profile_name):
                if result.get("type") == "content":
                    yield f"data: {json.dumps({'event': 'content', 'data': result['data']})}\n\n"
                elif result.get("type") == "debug":
                    yield f"data: {json.dumps({'event': 'debug', 'message': result['message']})}\n\n"
                elif result.get("status") == "error":
                    yield f"data: {json.dumps({'event': 'error', 'message': result['message']})}\n\n"
                    return
                elif result.get("status") == "success":
                    article_content = result["text"]
                    
            if DEBUG_MODE:
                yield f"data: {json.dumps({'event': 'debug', 'message': f'Phase 3 (Claude 3.5 Sonnet) completed in {round(time.time() - p3_start, 2)}s'})}\n\n"

            # Save the generated article
            post = Post(
                title=keyword,
                content=article_content,
                original_ai_content=article_content,
                profile_name=payload.profile_name,
            )
            db.add(post)
            db.commit()
            db.refresh(post)

            # Link Post ↔ ResearchRun for quality scoring feedback loop
            run_id = research_data_dict.get("research_run_id")
            if run_id:
                post.research_run_id = run_id
                research_run = db.get(ResearchRun, run_id)
                if research_run:
                    research_run.post_id = post.id
                db.commit()
                db.refresh(post)

            print(f"✅ [ARES] Generation complete for: {keyword}")
            
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
                print(f"❌ [ARES] Generation Error: {e}")
            yield f"data: {json.dumps({'event': 'error', 'message': error_msg})}\n\n"

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