import os
from pathlib import Path
from dotenv import load_dotenv

# Ensure environment is loaded BEFORE importing services
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from .database import Base, engine, get_db
from .models import Post
from .schemas import (
    BlueprintResponse,
    GenerateFullResponse,
    PostCreate,
    PostResponse,
    PostUpdate,
    ResearchResponse,
)

# Import services AFTER the environment is loaded
from .services.research_service import ResearchAgent

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Ares Engine Console")

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
        
        # Fire the hitl background task
        from .services.feedback_service import FeedbackAgent
        agent = FeedbackAgent(db=db)
        
        # We must use a detached async background task. 
        # But wait, FastAPI background tasks run in the same session, we can just pass the strings
        background_tasks.add_task(
            agent.analyze_and_store_feedback, 
            post.original_ai_content, 
            data.content
        )
    
    # Update the primary content string
    post.content = data.content
    
    # Allow title updates as well if provided
    if data.title:
        post.title = data.title

    db.commit()
    db.refresh(post)
    return post

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

@app.post("/generate/{keyword}")
async def generate_article(keyword: str, niche: str = "default", db: Session = Depends(get_db)):
    from .services.psychology_agent import PsychologyAgent
    from .services.writer_service import WriterService

    print(f"🚀 [ARES] Starting unified generation for: {keyword} (niche: {niche})")

    async def event_generator():
        try:
            # Phase 1: Research
            yield f"data: {json.dumps({'event': 'phase1_start', 'message': 'Gathering intelligence...'})}\n\n"
            research_agent = ResearchAgent(db)
            research_data_dict = await research_agent.research(keyword, niche=niche)
            
            # Phase 2: Psychology Blueprint
            yield f"data: {json.dumps({'event': 'phase2_start', 'message': 'Mapping psychological blueprint...'})}\n\n"
            psychology_agent = PsychologyAgent(db=db) 
            blueprint_dict = await psychology_agent.generate_blueprint(research_data_dict)
            
            # Send the blueprint back to the client immediately so it can render Phase 01 / Phase 02 visually
            yield f"data: {json.dumps({'event': 'phase2_complete', 'blueprint': blueprint_dict})}\n\n"

            # Phase 3: Content Writer
            yield f"data: {json.dumps({'event': 'phase3_start', 'message': 'Drafting final prose...'})}\n\n"
            writer_service = WriterService(db=db) 
            article_content = await writer_service.produce_article(blueprint_dict)

            # Save the generated article
            post = Post(
                title=keyword, 
                content=article_content, 
                original_ai_content=article_content
            )
            db.add(post)
            db.commit()
            db.refresh(post)

            print(f"✅ [ARES] Generation complete for: {keyword}")
            
            # Use model_dump or dictionary access to serialize the SQLAlchemy object safely
            # Since standard Post output might not be directly JSON serializable without a Pydantic model conversion
            from .schemas import PostResponse
            post_schema = PostResponse.model_validate(post).model_dump()
            # Must convert datetime objects to ISO strings for json.dumps
            post_schema['created_at'] = post_schema['created_at'].isoformat()
            
            final_payload = {
                'event': 'complete',
                'post': post_schema,
                'blueprint': blueprint_dict
            }
            yield f"data: {json.dumps(final_payload)}\n\n"
            
        except Exception as e:
            print(f"❌ [ARES] Generation Error: {e}")
            yield f"data: {json.dumps({'event': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

# ---------------------------------------------------------------------------
# Health check (Synchronized with console.js checkSystemStatus)
# ---------------------------------------------------------------------------

@app.get("/health")
async def health_check():
    """Check if DeepSeek API and Brave Goggles API are reachable concurrently."""
    import httpx
    import asyncio
    from .settings import DEEPSEEK_API_KEY, BRAVE_API_KEY
    from .services.research_service import DEEPSEEK_API_URL

    deepseek_ok = False
    brave_ok = False

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

    async def check_brave():
        if not BRAVE_API_KEY:
            return False
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    headers={
                        "Accept": "application/json",
                        "Accept-Encoding": "gzip",
                        "X-Subscription-Token": BRAVE_API_KEY
                    },
                    params={"q": "health"}
                )
                return resp.status_code == 200
        except Exception:
            return False

    deepseek_ok, brave_ok = await asyncio.gather(check_deepseek(), check_brave())

    # Return structure matching what console.js expects
    return {
        "status": "online" if (deepseek_ok and brave_ok) else "degraded", 
        "brave_search": brave_ok,
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