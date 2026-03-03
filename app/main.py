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

# --- Orchestration Endpoints ---

@app.get("/research/{keyword}", response_model=ResearchResponse)
async def research_keyword(keyword: str, db: Session = Depends(get_db)):
    agent = ResearchAgent(db)
    return await agent.research(keyword)

@app.post("/blueprint", response_model=BlueprintResponse)
async def generate_blueprint(research_data: ResearchResponse, db: Session = Depends(get_db)):
    from .services.psychology_agent import PsychologyAgent
    agent = PsychologyAgent(db=db) 
    blueprint = await agent.generate_blueprint(research_data.model_dump())
    return blueprint

@app.post("/generate/{keyword}", response_model=GenerateFullResponse)
async def generate_article(keyword: str, db: Session = Depends(get_db)):
    from .services.psychology_agent import PsychologyAgent
    from .services.writer_service import WriterService

    print(f"🚀 [ARES] Starting unified generation for: {keyword}")

    # Phase 1: Research
    research_agent = ResearchAgent(db)
    research_data = await research_agent.research(keyword)

    # Phase 2: Psychology Blueprint
    psychology_agent = PsychologyAgent(db=db) 
    blueprint = await psychology_agent.generate_blueprint(research_data)

    # Phase 3: Content Writer
    writer_service = WriterService(db=db) 
    article_content = await writer_service.produce_article(blueprint)

    # Save the generated article
    post = Post(title=keyword, content=article_content)
    db.add(post)
    db.commit()
    db.refresh(post)

    print(f"✅ [ARES] Generation complete for: {keyword}")
    return {"post": post, "blueprint": blueprint}

# ---------------------------------------------------------------------------
# Health check (Synchronized with console.js checkSystemStatus)
# ---------------------------------------------------------------------------

@app.get("/health")
async def health_check():
    """Check if Brave Search API is reachable."""
    import httpx
    from .services.research_service import BRAVE_API_KEY, BRAVE_SEARCH_URL

    try:
        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": BRAVE_API_KEY,
        }
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(
                BRAVE_SEARCH_URL,
                headers=headers,
                params={"q": "test", "count": 1},
            )
            brave_ok = resp.status_code == 200
    except Exception:
        brave_ok = False

    # Return structure matching what console.js expects
    return {
        "status": "online" if brave_ok else "degraded", 
        "brave_search": brave_ok
    }

# ---------------------------------------------------------------------------
# Static files & frontend
# ---------------------------------------------------------------------------

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

@app.get("/")
async def serve_console():
    return FileResponse(str(STATIC_DIR / "ares_console.html"))

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")