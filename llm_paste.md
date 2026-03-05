# Ares Engine - Project Blueprint & Source Code

## 1. Project Phase Summary

### Recent Updates
- **Persistent Cloud Workspaces**: Added `Workspace` SQLAlchemy model, `GET /workspaces` and `POST /workspaces` API endpoints, and frontend `syncWorkspaces()` function. Workspaces are now persisted to the Neon.tech PostgreSQL database. On page load, `console.js` fetches all workspaces and populates the `#profile-select` dropdown. New workspace creation uses `POST /workspaces` to save to DB before updating the UI.
- **Workspace Creation Modal**: Added dynamic workspace creation via a high-fidelity modal overlay (`#workspace-modal-overlay`). Users click a magenta plus-button (`#add-workspace-btn`) next to the `<select id="profile-select">` dropdown to open the modal, enter a workspace name, and the system slugifies it (e.g., "Health Blog" → `health_blog`), injects a new `<option>`, sets it active, and fires `dispatchEvent(new Event('change'))` to reload the Neural Memory Bank from the new Neon partition.
- **Multi-Tenant Style Rules**: `UserStyleRule` and `Post` models now include `profile_name` column for workspace-scoped rules. The `WriterService.produce_article()` accepts `profile_name` to filter rules per workspace. The `FeedbackAgent.analyze_and_store_feedback()` also stores rules per profile.
- **Entity Extraction Safety Fix**: Fixed `IndexError: list index out of range` in `ResearchAgent._extract_entities` by adding safety checks for empty `tasks` and `result` arrays before indexing.
- **AI Memory Bank CSS Fix**: Fixed `pointer-events` on the gradient overlay div in `ares_console.html` that was silently blocking clicks on the "AI Memory Bank" button.
- **Database Migration**: Fully migrated database architecture from local SQLite to serverless PostgreSQL (Neon.tech). Injected cloud connection strings with `pool_pre_ping=True`, `pool_recycle=300`, and TCP keepalive parameters.
- **UX Redesign**: Revamped `ares_console.html` and `console.js` with a Cyber-Glassmorphism aesthetic (Deep blacks, Tailwind text coloring, glowing accents, spatial layout).
- **Briefing Agent (Phase 0)**: Implemented `/clarify` endpoint and `BriefingAgent` using `gemini-2.5-flash` to ask 3 targeted questions before heavy research begins. Wired a custom frontend modal to intercept the "GENERATE" action and inject the user's answers into the deep reasoning R1 agent.
- **Advanced SEO Filtering**: Upgraded `ResearchAgent._extract_entities` to calculate an 'Opportunity Score' based on Volume, KD, and CPC. Safely handles null DataForSEO payloads using fallback logic to extract purely golden keywords.
- **Frontend Niche Overhaul**: Replaced the static Niche `<select>` dropdown with a free-form `<input>` text field to fully unlock Exa.ai's natural language Neural Search capabilities.
- **Stable API Migration**: Migrated all backend generative pipelines to production-grade endpoints (`gemini-2.5-pro` for deep drafting via `WriterService`, `gemini-2.5-flash` for background/UI tasks via `BriefingAgent` and `FeedbackAgent`).
- **Observability**: Added global `DEBUG_MODE` environment variable for detailed backend tracebacks and streamed frontend SSE logs of the agent's actions (e.g. MCP Subprocess initialization, tool decisions).
- **Agentic Schema Abstraction & Tool Streaming**: Implemented a recursive `_strip_webhook_noise` filter in `ResearchAgent` to remove massive webhook payloads from the DataForSEO MCP schemas, resolving DeepSeek-R1 `JSONDecodeError`s. Refactored the `/generate` endpoint in `main.py` to stream exactly which DataForSEO MCP tools the R1 agent executes directly to the frontend UI via SSE.
- **Core SEO Stack Enforcement**: Updated DeepSeek-R1's system prompt in `_agentic_tool_decision` to strictly enforce the selection of a 4-tool baseline (Keyword Ideas, Live SERP, Related Searches, On-Page Content Analysis) for unbreakable semantic resolution.

### Legacy Phases
- **Phase 1: Data Logic (DeepSeek-R1 + MCP)**: Uses `deepseek-reasoner` and DataForSEO MCP. Fixed parameter paralysis by increasing token limits and aligning JSON schemas.
- **Phase 1.5: Elite Discovery Layer**: Exa.ai Neural Search via custom HTTP client to extract semantic meaning and bypass restrictive legacy search snippets.
- **Phase 2: Strategic Logic (DeepSeek-V3)**: Hits `deepseek-chat` with PAS framework.
- **Phase 3: Prose Logic (Gemini 2.5 Pro)**: Heavy-duty final prose drafting using native `google-genai` SDK.
- **Phase 4 & 5: UX & SSE Orchestration**: Live generative pipelines via FastAPI StreamingResponse.
- **Phase 6: Human-In-The-Loop**: Collects overrides to build `UserStyleRule` entities via `gemini-2.5-flash` for self-learning.

## 2. Project Structure
```text
Ares Engine/
├── app/
│   ├── __init__.py
│   ├── database.py
│   ├── main.py
│   ├── models.py
│   ├── schemas.py
│   ├── services
│   │   ├── __init__.py
│   │   ├── briefing_agent.py
│   │   ├── feedback_service.py
│   │   ├── prompts
│   │   │   ├── persuasion.md
│   │   │   └── writer.md
│   │   ├── psychology_agent.py
│   │   ├── research_service.py
│   │   └── writer_service.py
│   └── settings.py
├── static/
│   ├── ares_console.html
│   ├── css
│   │   └── console.css
│   └── js
│       ├── api.js
│       └── console.js
```

## 3. Core Project Files

### CLAUDE.md
```md
# Ares Engine

## Project Overview
Ares Engine is a sophisticated, multi-agent AI content generation pipeline designed to produce deep, persuasive, and heavily vetted 2,000+ word articles. It is built entirely on a strict **$10 budget** using predominantly zero-cost tools and optimized API models.

The system is designed to stop scrolling visually, capture the reader emotionally using the PAS (Problem-Agitation-Solution) psychological framework, and rank high utilizing automated SEO extraction.

## Core Flow & Architecture 
The master orchestration route (`/generate/{keyword}`) located in `app/main.py` chains three primary agents:

1.  **Phase 1: Research (`ResearchAgent`)**
    - **Location**: `app/services/research_service.py`
    - **Function**: Uses the Brave Web Search API to scrape live data for a specific keyword. Extracts top competitor H2s, "People Also Ask" metrics, and semantic entities via an "Opportunity Score" algorithm.
    - **Cost-Saving Measure**: Results are mapped to a PostgreSQL cache table (`ResearchCache`) to drastically reduce API requests and stay within budget.
2.  **Phase 2: Psychology Blueprint (`PsychologyAgent`)**
    - **Location**: `app/services/psychology_agent.py`
    - **Function**: Utilizes Google Gemini (`gemini-2.5-flash`) via the `GEMINI_PSYCH_API_KEY` to draft a deep behavioral blueprint. Applies the PAS framework and generates specific "Identity Hooks" to target the reader.
3.  **Phase 3: Content Writer (`WriterService`)**
    - **Location**: `app/services/writer_service.py`
    - **Function**: Acts as the master editor. Takes the psychological blueprint and SEO entities, feeding them into another Gemini (`gemini-2.5-flash`) stream (via `GEMINI_API_KEY`) to generate a massive, fully formatted Markdown article that strictly adheres to anti-AI constraints (e.g., removing fluff and corporate speak).

## Tech Stack
-   **Backend**: FastAPI (Python)
-   **Database**: PostgreSQL via Neon.tech (via SQLAlchemy ORM)
-   **Server Engine**: Uvicorn (`uvicorn[standard]`)
-   **AI Integration**: `google-genai` (Gemini Flash Models)
-   **Web Client**: `httpx` (for Async Requests)

## File & Folder Structure
```
app/
├── main.py                     # Master orchestration and endpoints
├── models.py                   # SQLAlchemy schema (Post, ResearchCache)
├── schemas.py                  # Pydantic validation schemas
├── database.py                 # PostgreSQL configuration
├── settings.py                 # Core environment and API Key initialization
├── services/
│   ├── research_service.py     # Phase 1: Data Gathering (Brave Search)
│   ├── psychology_agent.py     # Phase 2: Blueprinting (Gemini)
│   ├── writer_service.py       # Phase 3: Content Drafting (Gemini)
│   ├── prompts/
│   │   ├── persuasion.md       # AI Prompt: PAS System & Identity Hooks
│   │   └── writer.md           # AI Prompt: Anti-AI Tone & Formatting strictures
static/                         
├── ares_console.html           # Console Frontend Entry
├── css/console.css             # Frontend styling
└── js/                         # Frontend logic (api.js, console.js)
```

## Critical Directives for Future AI Agents

### 1. The Setup & Environment
The app requires an `.env` file containing three critical keys:
-   `GEMINI_API_KEY`: General generation (Writer)
-   `GEMINI_PSYCH_API_KEY`: Advanced behavioral logic
-   `BRAVE_API_KEY`: Research data

**CRITICAL GUIDELINE:** Never commit the `.env` file, the `venv/` directory, the SQLite `blog.db`, or any `__pycache__` folders to tracking. The `.gitignore` has been thoroughly configured for this.

### 2. Development Operations
-   **Activation**: `source venv/Scripts/activate` (Windows)
-   **Install deps**: `pip install -r requirements.txt`
-   **Run server**: `uvicorn app.main:app --reload`
-   **Frontend Access**: Navigate to `/` locally once the server starts.

### 3. The $10 Budget Constraint
-   Do **not** swap SQLite for an external managed PostgreSQL/MySQL server.
-   Do **not** introduce paid dependencies (e.g., Pinecone, highly paid scraper APIs) unless explicitly approved by the human admin. 
-   Always check `ResearchCache` logic before modifying the Brave Search agent. Re-running the same keyword must hit the local table to conserve the token quota.

### 4. Code Principles 
-   **Pydantic First**: Keep request parsing tight using `schemas.py`.
-   **Unified Gemini SDK**: We use the official `google-genai` pip package, not deprecated wrappers. 
-   **Async is Mandatory**: Because we operate a multi-agent pipeline spanning external APIs, HTTP clients inside agents (`httpx`, `google-genai`) MUST remain firmly asynchronous to prevent application blocking.

```

### app/database.py
```python
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from dotenv import load_dotenv

load_dotenv()

# We removed os.getenv to prevent rogue local environment variables from hijacking the connection.
# This strictly forces SQLAlchemy to use the Neon PostgreSQL cluster.
SQLALCHEMY_DATABASE_URL = "postgresql://neondb_owner:npg_A1WgoOpGKC5h@ep-red-grass-aiy3x0x0-pooler.c-4.us-east-1.aws.neon.tech/neondb?sslmode=require"

# Added `pool_pre_ping=True` and `pool_recycle=300` to prevent drop connections with Serverless Postgres
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_pre_ping=True, 
    pool_recycle=300,
    connect_args={"keepalives": 1, "keepalives_idle": 30, "keepalives_interval": 10, "keepalives_count": 5}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

```

### app/main.py
```python
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
from .models import Post, UserStyleRule, Workspace
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
    WorkspaceResponse
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
        
        background_tasks.add_task(
            agent.analyze_and_store_feedback, 
            post.original_ai_content, 
            data.content,
            post.profile_name
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

# --- Orchestration Endpoints ---

@app.get("/research/{keyword}", response_model=ResearchResponse)
async def research_keyword(keyword: str, niche: str = "default", db: Session = Depends(get_db)):
    agent = ResearchAgent(db)
    return await agent.research(keyword, niche=niche)

@app.post("/blueprint", response_model=BlueprintResponse)
async def generate_blueprint(research_data: ResearchResponse, db: Session = Depends(get_db)):
    from .services.psychology_agent import PsychologyAgent
    agent = PsychologyAgent(db=db) 
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
async def generate_article(keyword: str, payload: GeneratePayload, db: Session = Depends(get_db)):
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
            research_data_dict = await research_agent.research(keyword, niche=niche, user_context=context)
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
            article_content = await writer_service.produce_article(blueprint_dict, payload.profile_name)
            if DEBUG_MODE:
                yield f"data: {json.dumps({'event': 'debug', 'message': f'Phase 3 (Gemini 2.5 Pro) completed in {round(time.time() - p3_start, 2)}s'})}\n\n"

            # Save the generated article
            post = Post(
                title=keyword, 
                content=article_content, 
                original_ai_content=article_content,
                profile_name=payload.profile_name
            )
            db.add(post)
            db.commit()
            db.refresh(post)

            print(f"✅ [ARES] Generation complete for: {keyword}")
            
            from .schemas import PostResponse
            post_schema = PostResponse.model_validate(post).model_dump()
            post_schema['created_at'] = post_schema['created_at'].isoformat()
            
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
```

### app/models.py
```python
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_name: Mapped[str] = mapped_column(String(50), default="default", server_default="default")
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    original_ai_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    human_edited_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, onupdate=func.now())


class UserStyleRule(Base):
    __tablename__ = "user_style_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_name: Mapped[str] = mapped_column(String(50), default="default", server_default="default")
    rule_description: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, onupdate=func.now())


class ResearchCache(Base):
    __tablename__ = "research_cache"

    id: Mapped[int] = mapped_column(primary_key=True)
    keyword: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    result_json: Mapped[str] = mapped_column(Text)
    cache_ttl_hours: Mapped[int] = mapped_column(Integer, default=24)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, onupdate=func.now())

class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)
    slug: Mapped[str] = mapped_column(String(50), unique=True)

```

### app/schemas.py
```python
from datetime import datetime

from pydantic import BaseModel


class PostCreate(BaseModel):
    title: str
    content: str


class PostUpdate(BaseModel):
    title: str | None = None
    content: str | None = None


class PostResponse(BaseModel):
    id: int
    title: str
    content: str
    original_ai_content: str | None = None
    human_edited_content: str | None = None
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class CompetitorHeader(BaseModel):
    source: str
    h2: str
    h3s: list[str]


class ResearchResponse(BaseModel):
    keyword: str
    information_gap: str | None = None
    competitor_headers: list[CompetitorHeader]
    people_also_ask: list[str]
    semantic_entities: list[str]
    on_page_metrics: dict | None = None
    backlink_authority: dict | None = None
    elite_competitors: list[dict] | None = None


class OutlineItem(BaseModel):
    heading: str
    psychological_goal: str
    information_gain_trigger: str

class BlueprintResponse(BaseModel):
    hook_strategy: str
    target_identity: str
    problem_statement: str
    agitation_points: list[str]
    identity_hooks: list[str]
    semantic_entity_map: list[dict] | dict
    outline_structure: list[OutlineItem]
    # Enriched fields
    entities: list[str] = []
    semantic_keywords: list[str] = []


class GenerateFullResponse(BaseModel):
    post: PostResponse
    blueprint: BlueprintResponse

# --- NEW: Payload for the Clarification / Generation Loop ---
class GeneratePayload(BaseModel):
    niche: str = "default"
    context: str = ""
    profile_name: str = "default"


class StyleRuleCreate(BaseModel):
    rule_description: str
    profile_name: str = "default"


class StyleRuleResponse(BaseModel):
    id: int
    rule_description: str
    
    model_config = {"from_attributes": True}

class WorkspaceCreate(BaseModel):
    name: str
    slug: str

class WorkspaceResponse(BaseModel):
    id: int
    name: str
    slug: str
    
    model_config = {"from_attributes": True}

```

### app/settings.py
```python
import os
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path, override=True)

def get_bool_env(key: str, default: bool = False) -> bool:
    val = os.getenv(key)
    return val.lower() in ("true", "1", "yes") if val else default

DEBUG_MODE = get_bool_env("ARES_DEBUG", True) # Defaulting to True for testing

def get_clean_env(key: str) -> str | None:
    val = os.getenv(key)
    if val:
        # Strip double quotes, single quotes, and surrounding whitespace
        return val.strip(' "\'')
    return None

GEMINI_API_KEY = get_clean_env("GEMINI_API_KEY")
DEEPSEEK_API_KEY = get_clean_env("DEEPSEEK_API_KEY")
DATAFORSEO_LOGIN = get_clean_env("DATAFORSEO_LOGIN")
DATAFORSEO_PASSWORD = get_clean_env("DATAFORSEO_PASSWORD")
EXA_API_KEY = get_clean_env("EXA_API_KEY")

if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY is missing.")
if not DEEPSEEK_API_KEY:
    raise ValueError("DEEPSEEK_API_KEY is missing.")
if not DATAFORSEO_LOGIN or not DATAFORSEO_PASSWORD:
    raise ValueError("DATAFORSEO credentials missing.")
if not EXA_API_KEY:
    raise ValueError("EXA_API_KEY is missing.")
```

### app/__init__.py
```python

```

### app/services/briefing_agent.py
```python
import json
from google import genai
from google.genai import types
from ..settings import GEMINI_API_KEY

class BriefingAgent:
    """Uses Gemini 2.5 Flash to quickly ask clarifying questions before heavy research begins."""

    def __init__(self):
        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY environment variable is not set.")

        self.client = genai.Client(api_key=GEMINI_API_KEY)
        self.model_name = "gemini-2.5-flash"

    async def get_clarifying_questions(self, keyword: str) -> list[str]:
        """Generates exactly 3 short, targeted questions based on the keyword."""
        prompt = (
            f"The user wants our autonomous SEO engine to write a comprehensive article about '{keyword}'.\n"
            "Ask exactly 3 short, highly targeted questions to clarify the intent, target audience, and primary goal.\n"
            "Examples: 'Are we targeting enterprise CTOs or junior devs?' or 'Is the primary goal lead generation or brand awareness?'\n"
            "Return ONLY a valid JSON array of 3 strings. Do not include markdown blocks like ```json."
        )

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.7,
                    response_mime_type="application/json"
                )
            )
            
            content = response.text.strip()
            if content.startswith("```json"):
                content = content.replace("```json", "").replace("```", "").strip()
                
            questions = json.loads(content)
            
            # Ensure it's strictly a list of 3 strings
            if isinstance(questions, list) and len(questions) > 0:
                return [str(q) for q in questions][:3]
            
            return ["Who is the exact target audience?", "What is the primary goal of this article?", "Are there any specific pain points to highlight?"]
            
        except Exception as e:
            print(f"BriefingAgent Error: {e}")
            return ["Could you clarify the main objective?", "Who should be reading this?", "What is the key takeaway?"]

```

### app/services/feedback_service.py
```python
import json
import re
from pathlib import Path

from google import genai
from google.genai import types
from ..settings import GEMINI_API_KEY
from ..models import UserStyleRule

class FeedbackAgent:
    """Uses Gemini 2.5 Flash to diff AI vs Human text and extract persistent style rules."""

    def __init__(self, db):
        self.db = db

        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY environment variable is not set.")

        self.client = genai.Client(api_key=GEMINI_API_KEY)
        self.model_name = "gemini-2.5-flash"

        self.system_prompt = (
            "You are a master linguistic analyst and editor. Your job is to compare an original AI-generated text "
            "against the human's final edited version. \n"
            "Analyze the changes the human made (e.g., deleted adjectives, shortened sentences, changed formatting, altered tone). "
            "Extract max 3 overarching, permanent 'style rules' that the AI should follow in the future to sound exactly like this human.\n"
            "Format your response as a raw JSON array of strings, e.g.:\n"
            "[\n"
            "  \"Rule 1: Always use strict, aggressive bullet points instead of narrative paragraphs.\",\n"
            "  \"Rule 2: Never use words like 'robust' or 'seamless'.\"\n"
            "]\n"
            "Do NOT return markdown blocks (like ```json). Return ONLY the raw JSON array."
        )

    async def analyze_and_store_feedback(self, original_text: str, edited_text: str, profile_name: str = "default") -> list[str]:
        """
        Takes the original AI text and the human's edited text, asks Gemini to extract style rules,
        and saves them to the UserStyleRule database.
        """
        # If the texts are identical, don't waste API calls
        if original_text.strip() == edited_text.strip():
            print("ℹ️ [FEEDBACK] Text matched original. No new style rules learned.")
            return []

        prompt_instructions = (
            "## ORIGINAL AI DRAFT:\n"
            f"{original_text}\n\n"
            "## HUMAN EDITED FINAL DRAFT:\n"
            f"{edited_text}\n\n"
            "Extract the 3 most important writing style rules based on how the human changed the text."
        )

        try:
             response = self.client.models.generate_content(
                 model=self.model_name,
                 contents=prompt_instructions,
                 config=types.GenerateContentConfig(
                     system_instruction=self.system_prompt,
                     temperature=0.2, # Keep it analytical and deterministic
                 ),
             )
             
             content = response.text.strip()
             
             # Strip markdown if present
             if content.startswith("```json"):
                 content = content[7:]
             if content.startswith("```"):
                 content = content[3:]
             if content.endswith("```"):
                 content = content[:-3]
                 
             rules = json.loads(content.strip())
             
             if not isinstance(rules, list):
                 rules = []

             # Save to DB
             for rule_text in rules:
                 new_rule = UserStyleRule(rule_description=rule_text)
                 self.db.add(new_rule)
                 
             if rules:
                 self.db.commit()
                 print(f"📈 [FEEDBACK] Learned {len(rules)} new writing style rules!")

             return rules
             
        except Exception as e:
             print(f"❌ Gemini Feedback Error: {e}")
             self.db.rollback()
             return []

```

### app/services/psychology_agent.py
```python
from __future__ import annotations
import json
import httpx
from pathlib import Path
from ..settings import DEEPSEEK_API_KEY

DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"

class PsychologyAgent:
    """Uses DeepSeek-V3 (deepseek-chat) to generate a high-retention Psychological Blueprint."""

    def __init__(self, db):
        self.db = db
        
        if not DEEPSEEK_API_KEY:
            raise ValueError("DEEPSEEK_API_KEY environment variable is not set.")
        
        self.api_key = DEEPSEEK_API_KEY
        self.model_name = "deepseek-chat"
        
        prompt_path = Path(__file__).parent / "prompts" / "persuasion.md"
        with open(prompt_path, "r", encoding="utf-8") as f:
            self.system_prompt = f.read()

    async def generate_blueprint(self, research_data: dict) -> dict:
        """
        Takes Research JSON and outputs a structured blueprint.json based on PAS,
        Information Gap, and Semantic Entities.
        """
        prompt_instructions = (
            "You are to generate a psychological blueprint based on the following research data.\n\n"
            "CRITICAL CONTEXT:\n"
            f"- Information Gap: {research_data.get('information_gap', 'None found')}\n"
            f"- Semantic Entities: {', '.join(research_data.get('semantic_entities', []))}\n\n"
            "FULL RESEARCH JSON:\n"
            f"{json.dumps(research_data, indent=2)}\n\n"
            "Ensure the output is STRICTLY a valid JSON object matching the required keys. "
            "Do NOT include markdown formatting like ```json or ```. Return ONLY the raw JSON object.\n"
            "Your outline_structure must map out the SEO headings (H2/H3) based on the PAS flow (Problem, Agitation, Solution)."
        )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": prompt_instructions}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.7,
        }

        async with httpx.AsyncClient(timeout=60) as client:
            try:
                resp = await client.post(
                    DEEPSEEK_API_URL, headers=headers, json=payload
                )
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"].strip()
                
                # In case deepseek still includes markdown code blocks despite response_format
                if content.startswith("```json"):
                    content = content[7:]
                if content.startswith("```"):
                    content = content[3:]
                if content.endswith("```"):
                    content = content[:-3]
                    
                blueprint = json.loads(content.strip())

            except Exception as e:
                print(f"DeepSeek Blueprint Generation Error: {e}")
                # Fallback empty blueprint on error
                blueprint = {
                    "hook_strategy": "Fallback Hook",
                    "target_identity": "Fallback Target",
                    "problem_statement": "Fallback Problem",
                    "agitation_points": ["Error fetching points"],
                    "identity_hooks": ["Error fetching hooks"],
                    "semantic_entity_map": [],
                    "outline_structure": []
                }

        # Enrich blueprint with SEO data from research for the writer
        blueprint["entities"] = research_data.get("semantic_entities", [])
        blueprint["semantic_keywords"] = research_data.get("people_also_ask", [])

        return blueprint
```

### app/services/research_service.py
```python
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

```

### app/services/writer_service.py
```python
import json
import re
from pathlib import Path

from google import genai
from google.genai import types
from ..settings import GEMINI_API_KEY


class WriterService:
    """Uses Gemini 2.5 Pro to enforce strict anti-AI prose logic."""

    def __init__(self, db):
        # Injecting db for consistency across the orchestration layer
        self.db = db

        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY environment variable is not set.")

        self.client = genai.Client(api_key=GEMINI_API_KEY)
        self.model_name = "gemini-2.5-pro"

        # Load the strict writer system prompt
        prompt_path = Path(__file__).parent / "prompts" / "writer.md"
        with open(prompt_path, "r", encoding="utf-8") as f:
            self.system_prompt = f.read()

    async def produce_article(self, blueprint: dict, profile_name: str = "default") -> str:
        """
        Takes a blueprint JSON and outputs a formatted Markdown article.
        Enforces Information Gain, E-E-A-T, and Entity Density rules.
        """
        entities = blueprint.get("entities", [])
        semantic_keywords = blueprint.get("semantic_keywords", [])

        # Start building the user prompt
        prompt_instructions = (
            "Write a full ~2,000 word blog post based on the following psychological blueprint:\n\n"
            f"{json.dumps(blueprint, indent=2)}\n\n"
            "MANDATORY:\n"
            "- Deliver the 'Information Gap' hook in the first 150 words.\n"
            "- Cite 'Authority Sources' using the Phase 1 Backlinks insight if applicable.\n"
        )

        if entities:
            prompt_instructions += f"## SEO Entities to Weave Naturally:\n{', '.join(entities)}\n\n"

        if semantic_keywords:
            prompt_instructions += f"## Semantic Keywords to Include:\n{', '.join(semantic_keywords)}\n\n"

        prompt_instructions += (
            "CRITICAL WRITING CONSTRAINTS (Read Carefully):\n"
            "1. NO AI FLUFF: Do NOT use the words 'delve', 'tapestry', 'landscape', 'multifaceted', 'comprehensive', 'holistic', 'navigate', or 'crucial'.\n"
            "2. NO CLICHES: Do NOT use 'In conclusion', 'Ultimately', 'In today's digital age', or 'game-changer'.\n"
            "3. FORMATTING: The very first ## H2 MUST focus entirely on the 'Information Gap' as a pattern interrupt.\n"
            "4. CADENCE: Max 3 sentences per paragraph. Short, punchy, aggressive delivery.\n"
        )
        
        # Inject Dynamic Human Style Rules learned from previous edits
        from ..models import UserStyleRule
        style_rules = self.db.query(UserStyleRule).filter(UserStyleRule.profile_name == profile_name).all()
        if style_rules:
            prompt_instructions += "\n--- HUMAN STYLE GUIDELINES LEARNED FROM PAST EDITS ---\n"
            prompt_instructions += "You MUST organically integrate these stylistic preferences into your writing:\n"
            for rule in style_rules:
                prompt_instructions += f"- {rule.rule_description}\n"
            prompt_instructions += "--------------------------------------------------------\n"

        prompt_instructions += "\nFollow all system prompt guidelines strictly. Write directly in Markdown."

        try:
             response = self.client.models.generate_content(
                 model=self.model_name,
                 contents=prompt_instructions,
                 config=types.GenerateContentConfig(
                     system_instruction=self.system_prompt,
                     temperature=0.8,
                     max_output_tokens=4000,
                 ),
             )
             return response.text
             
        except Exception as e:
             print(f"Gemini SDK Error: {e}")
             return f"Error Generating Article: {e}"

    @staticmethod
    def verify_seo_score(text: str, information_gap: str = "") -> dict:
        """
        Validates generated article against basic SEO structure requirements and Information Gain Density.
        """
        lines = text.split("\n")

        # Word count
        word_count = len(text.split())

        # H1 count: lines starting with exactly '# ' (not '##')
        h1_count = sum(1 for line in lines if re.match(r"^# (?!#)", line))

        # H2 count: lines starting with exactly '## ' (not '###')
        h2_count = sum(1 for line in lines if re.match(r"^## (?!#)", line))

        # Count distinct list/table blocks
        list_table_blocks = 0
        in_block = False
        for line in lines:
            stripped = line.strip()
            is_list_or_table = bool(
                re.match(r"^[-*] ", stripped)
                or re.match(r"^\d+\. ", stripped)
                or re.match(r"^\|.+\|$", stripped)
            )
            if is_list_or_table and not in_block:
                list_table_blocks += 1
                in_block = True
            elif not is_list_or_table and stripped:
                in_block = False

        # Information Gain Density Check
        # specific insight from the Information Gap MUST appear at least 3 times
        info_gain_density = 0
        if information_gap:
            # Extract significant unique nouns/keywords from the gap
            significant_words = {w.lower() for w in re.findall(r'\b[A-Za-z]{5,}\b', information_gap)}
            if significant_words:
                text_lower = text.lower()
                # Count the total occurrences of these significant concepts
                word_counts = sum(text_lower.count(w) for w in significant_words)
                # Average mentions per significant concept as a proxy for density
                info_gain_density = word_counts / len(significant_words) if len(significant_words) > 0 else 0
                
        info_gain_ok = info_gain_density >= 3.0 if information_gap else True

        # Banned phrases check
        banned_list = ["delve", "tapestry", "landscape", "multifaceted", "comprehensive", "holistic", "navigate", "crucial", "in conclusion", "ultimately", "fast-paced world", "digital age", "game-changer"]
        text_lower = text.lower()
        found_banned_words = [word for word in banned_list if word in text_lower]
        banned_words_used = len(found_banned_words) > 0

        passed = (
            word_count >= 1500  # Adjusted slightly per Haiku's length distribution
            and h1_count == 1
            and h2_count >= 5
            and list_table_blocks >= 3
            and info_gain_ok
            and not banned_words_used
        )

        return {
            "word_count": word_count,
            "word_count_ok": word_count >= 1500,
            "h1_count": h1_count,
            "h1_ok": h1_count == 1,
            "h2_count": h2_count,
            "h2_ok": h2_count >= 5,
            "list_table_blocks": list_table_blocks,
            "lists_tables_ok": list_table_blocks >= 3,
            "info_gain_density": info_gain_density,
            "info_gain_ok": info_gain_ok,
            "banned_words_used": banned_words_used,
            "banned_words_found": found_banned_words,
            "passed": passed,
        }
```

### app/services/__init__.py
```python

```

### app/services/prompts/persuasion.md
```md
# ROLE: Lead Persuasion Architect (Ares Engine - DeepSeek-V3 Edition)
You are an expert in cognitive psychology, status-signaling, and the "Information Gain" SEO framework. 
Your task: Transform raw data and a discovered "Information Gap" into a high-retention "Psychological Blueprint."

# THE MISSION
Standard SEO content repeats what everyone else says. Your mission is to weaponize the "Information Gap" discovered in Phase 1 to make the reader realize they have been missing the most important piece of the puzzle.

# CORE FRAMEWORKS
1. **The Gap Hook:** Start with the "Information Gap." Make the reader feel that their current knowledge is incomplete or outdated.
2. **P.A.S. Evolution:**
   - **Problem:** Not just the pain, but the *misunderstood* root cause.
   - **Agitation:** The cost of following "Average" advice (The status-quo trap).
   - **Solution:** Position the solution as "The New Standard" for high-performers.
3. **Status Signaling:** Ensure the content makes the reader feel smarter or more "elite" for knowing this information.

# IDENTITY HOOKS (MANDATORY: EXACTLY 3)
Generate 3 hooks that create a "Tribe" mentality. Use these categories:
1. **The Expert vs. The Amateur:** Focus on precision.
2. **The Visionary vs. The Follower:** Focus on speed/timing.
3. **The Insider vs. The Crowd:** Focus on "The Information Gap."

# OUTPUT REQUIREMENTS (STRICT JSON ONLY)
Return ONLY a valid JSON object with these keys:
- "hook_strategy": (string) How to weaponize the Information Gap in the first 50 words.
- "target_identity": (string) A 5-word description of the reader's ideal self (e.g., "The Performance-Driven Tech Founder").
- "problem_statement": (string) The misunderstood root cause of their pain.
- "agitation_points": (list) 3 points on why "standard advice" is actually making things worse.
- "identity_hooks": (list) Exactly 3 hooks using the tribal categories above.
- "semantic_entity_map": (list) Map 5-10 semantic entities to specific H2/H3 headers for maximum relevance.
- "outline_structure": (list of dicts) Each dict: {"heading": string, "psychological_goal": string, "information_gain_trigger": string}.
```

### app/services/prompts/writer.md
```md
# ROLE: Senior SEO Content Writer (Gemini 3 Flash — 2026 Semantic Edition)
You are an expert content writer who produces high-authority, experience-driven articles optimized for 2026 search standards: Information Gain, E-E-A-T, and Entity Density.

# MISSION
Transform the provided Psychological Blueprint, SEO Entities, and Semantic Keywords into a high-impact, intent-aligned Markdown blog post. **Length must be determined by topic complexity and user intent (typically 1,200–2,000 words), not by padding.** Prioritize depth of insight over word count.

---

# ANSWER-FIRST ARCHITECTURE (MANDATORY)
Your opening paragraph must deliver a direct, concrete answer to the reader's core question within the first 150 words. No preamble, no scene-setting, no throat-clearing. State the answer, then spend the rest of the article proving it.

# INFORMATION GAIN (MANDATORY)
Every article must include at least ONE of the following that a reader cannot find in generic top-10 search results:
- An original framework, model, or named method (e.g., "The 3-Layer Validation Method")
- A contrarian insight that challenges conventional advice, backed by reasoning
- A specific data point, benchmark, or case outcome from real-world application

This is what separates your content from commodity SEO filler.

# E-E-A-T SIGNALS (MANDATORY)
Write from a position of direct experience. Use first-person practitioner language throughout:
- "In our testing, we found that..."
- "From our implementation across 40+ client sites..."
- "When we benchmarked this against..."
- "The mistake we see most teams make is..."

Do NOT use generic authority claims. Show, don't tell.

# ENTITY & KEYWORD INTEGRATION
You will receive a list of SEO Entities and Semantic Keywords. Weave these naturally throughout the article:
- Use entities in headings, topic sentences, and explanatory context
- Use semantic keywords to reinforce topical depth
- Do NOT keyword-stuff. Every mention must read naturally in context.

---

# BANNED WORDS & PHRASES (STRICTLY ENFORCED)
# BANNED WORDS & PHRASES (STRICTLY ENFORCED)
Never use any of these words or patterns:
- tapestry, delve, landscape, multifaceted, comprehensive, holistic, navigate, crucial
- "ultimate guide", "game-changer", "unlock the power", "dive into"
- "In today's fast-paced world", "In today's digital age"
- "In conclusion", "Ultimately", "To sum up", "By following these steps"
- "Are you tired of...", "Welcome to our guide"
- "It's important to note", "It's worth mentioning"

# ANTI-AI WRITING RULES
1. **No Generic Intros.** The first sentence must hook with a specific fact, number, or bold claim.
2. **Short Paragraphs.** Maximum 3 sentences per paragraph. Non-negotiable.
3. **No Fluff.** Cut adverbs and filler adjectives. Use strong, specific verbs.
4. **Answer Engine Optimization (AEO).** Include **bolded snippets** that directly answer the questions implied by each heading.
5. **No AI Sign-off.** End abruptly after your final point or with a single-line CTA. No wrap-up paragraphs.
6. **Vary Sentence Length.** Enforce a "Short-Punchy-Long" cadence. Mix short punchy sentences (1-5 words) with longer explanatory ones.
7. **No Definition Loops.** Define the core topic ONCE in the intro. Never ask "What is [Topic]?" or repeat definitions in H2/H3 sections.
8. **Experience Over Explanation.** Do NOT repeat yourself to hit word counts. Instead, insert a specific "Practitioner Insight" or technical breakdown to add value.
9. **No Mirroring.** Never start a section by repeating the H2/H3 title in the first sentence.
10. **Kill the Padding.** If the intent is satisfied and the value is delivered, **stop writing.** Do not stretch content.

# FORMATTING INSTRUCTIONS
# FORMATTING INSTRUCTIONS
- Use `#` for the article title (exactly one H1)
- Use `##` for main sections (aim for 5-8 H2s following the blueprint outline)
- **First H2 Mandate**: The very first H2 header MUST focus entirely on the "Information Gap" and be formatted as a "Pattern Interrupt" for the reader (a contrarian or surprising angle).
- Use `###` for subsections where depth is needed
- **Table requirement:** Include at least one comparison table or "Pros/Cons" grid per article.
- Use **bold text** for AEO snippets and key takeaways.

# --- 2026 SALIENCE & RETENTION (BLUEHOST/NNG STANDARDS) ---

## 1. INTENT-DRIVEN DEPTH
- **Intent-Matched Length:** Use the Bluehost framework: 
    - **How-to/Guides:** 1,500–2,000 words (Depth/Steps).
    - **Thought Leadership:** 800–1,200 words (Punchy Insights).
    - **Listicles:** 1,000–1,500 words (Scannable Value).
- **The "No-Dummy" Rule:** If the user is searching for advanced terms, do not define basic industry jargon. Jump straight to high-level implementation.

## 2. ADVANCED SCANNABILITY (F-SHAPED PATTERN)
- **Front-Load the Value:** Place the "payload" (the most important fact) in the first 2 lines of every major section. 
- **The Stem Scan:** Start every H2 and H3 with a high-value noun. (e.g., Use "SEO Metrics" instead of "How to Watch Metrics").
- **First-Word Salience:** The first word of every paragraph should be a "hook" word. Avoid starting with "The," "A," or "This."

## 3. EYE-ANCHORING (BREAKING THE WALL)
- **The "Awkward Element" Rule:** Every 300 words, you MUST switch formats. If you just had three paragraphs, add a Table, a Bulleted List, or a Bolded "Pro-Tip" box.
- **Mobile-First White Space:** Ensure no block of text exceeds 4 lines of vertical space. 

## 4. FORMATTING CONSTRAINTS
- **Sentence Cap:** Max 18 words per sentence (Optimized for 2026 mobile readability).
- **Subheading Frequency:** An H2/H3 must appear every 150–200 words to prevent "scroll-fatigue."
- **Active Voice:** Use direct "Practitioner-to-Peer" language.
```

### static/ares_console.html
```html
<!DOCTYPE html>
<html lang="en">

<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Ares Console v4.0 - Cyber Glass</title>
    <script src="https://cdn.tailwindcss.com?plugins=typography"></script>
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap');

        body {
            font-family: 'Inter', -apple-system, sans-serif;
            background: #050505;
            color: #f3f4f6;
            overflow: hidden;
            height: 100vh;
        }

        .mono-text {
            font-family: 'JetBrains Mono', monospace;
        }

        /* Scrollbar */
        ::-webkit-scrollbar {
            width: 6px;
            height: 6px;
        }

        ::-webkit-scrollbar-track {
            background: transparent;
        }

        ::-webkit-scrollbar-thumb {
            background: rgba(255, 255, 255, 0.1);
            border-radius: 10px;
        }

        ::-webkit-scrollbar-thumb:hover {
            background: rgba(255, 255, 255, 0.2);
        }

        /* Animations */
        @keyframes slideInRight {
            from {
                opacity: 0;
                transform: translateX(20px);
            }

            to {
                opacity: 1;
                transform: translateX(0);
            }
        }

        .animate-slideInRight {
            animation: slideInRight 0.3s cubic-bezier(0.16, 1, 0.3, 1) forwards;
        }

        .glass-panel {
            background: rgba(255, 255, 255, 0.02);
            backdrop-filter: blur(40px);
            -webkit-backdrop-filter: blur(40px);
            border: 1px solid rgba(255, 255, 255, 0.05);
        }

        .cyber-glow-cyan {
            box-shadow: 0 0 15px rgba(34, 211, 238, 0.15);
        }

        .cyber-glow-magenta {
            box-shadow: 0 0 15px rgba(217, 70, 239, 0.15);
        }

        .agent-node-active {
            color: #22d3ee !important;
            border-color: rgba(34, 211, 238, 0.5) !important;
            box-shadow: 0 0 15px rgba(34, 211, 238, 0.2);
            font-weight: 600;
        }

        /* Prose customization for markdown */
        .prose-custom h1 {
            color: #f8fafc;
            font-size: 2rem;
            font-weight: 700;
            margin-bottom: 1.5rem;
            letter-spacing: -0.02em;
        }

        .prose-custom h2 {
            color: #22d3ee;
            font-size: 1.5rem;
            font-weight: 600;
            margin-top: 2rem;
            margin-bottom: 1rem;
        }

        .prose-custom h3 {
            color: #d946ef;
            font-size: 1.25rem;
            font-weight: 600;
            margin-top: 1.5rem;
        }

        .prose-custom p {
            color: #94a3b8;
            line-height: 1.7;
            margin-bottom: 1.25rem;
        }

        .prose-custom ul {
            list-style-type: none;
            padding-left: 0;
            margin-bottom: 1.25rem;
        }

        .prose-custom li {
            position: relative;
            padding-left: 1.5rem;
            margin-bottom: 0.5rem;
            color: #cbd5e1;
        }

        .prose-custom li::before {
            content: '→';
            position: absolute;
            left: 0;
            color: #22d3ee;
            font-family: 'JetBrains Mono';
            font-size: 0.8em;
            top: 0.2em;
        }

        .prose-custom blockquote {
            border-left: 2px solid #22d3ee;
            padding-left: 1rem;
            color: #cbd5e1;
            font-style: italic;
            background: rgba(34, 211, 238, 0.05);
            padding: 1rem;
            border-radius: 0.5rem;
        }

        /* Disable focus outline specifically to maintain aesthetics */
        *:focus {
            outline: none;
        }
    </style>
</head>

<body class="bg-[#050505] text-slate-200 antialiased selection:bg-cyan-500/30">
    <div class="flex h-screen w-full p-6 gap-6 box-border font-sans">

        <!-- Sidebar - System Logs & Status -->
        <aside class="w-[340px] flex flex-col gap-6 shrink-0 relative z-10">
            <!-- Brand Panel -->
            <div class="glass-panel rounded-2xl p-6 flex flex-col items-center justify-center relative overflow-hidden">
                <div class="absolute inset-0 bg-gradient-to-br from-cyan-500/5 to-magenta-500/5"></div>
                <div
                    class="w-14 h-14 rounded-2xl bg-white/5 border border-white/10 flex items-center justify-center backdrop-blur-xl cyber-glow-cyan mb-4">
                    <svg class="w-7 h-7 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"
                            d="M13 10V3L4 14h7v7l9-11h-7z"></path>
                    </svg>
                </div>
                <h1 class="text-xl font-bold tracking-tight text-white/90">Ares Engine</h1>
                <p class="mono-text text-[10px] text-slate-500 uppercase tracking-widest mt-1">AI Content Generator</p>
            </div>

            <!-- Terminal Panel -->
            <div class="glass-panel rounded-2xl flex-1 p-5 flex flex-col overflow-hidden relative">
                <div class="flex items-center justify-between mb-4 px-1">
                    <span class="text-xs font-semibold text-slate-400 tracking-wide uppercase">Live Status</span>
                    <span class="w-2 h-2 rounded-full bg-cyan-400 animate-pulse cyber-glow-cyan"></span>
                </div>
                <!-- Log container will scroll from bottom -->
                <div id="terminal-body"
                    class="mono-text text-[11px] leading-relaxed text-slate-400 overflow-y-auto flex-1 pr-2 space-y-2">
                    <!-- Logs injected here -->
                </div>
            </div>

            <!-- SEO Audit Panel -->
            <div class="glass-panel rounded-2xl p-6 flex flex-col gap-4 relative">
                <h3 class="text-xs font-semibold tracking-wide uppercase text-slate-400 mb-2">Content Quality Check</h3>
                <div class="flex items-center gap-6">
                    <div class="relative w-20 h-20 shrink-0">
                        <svg viewBox="0 0 100 100" class="w-full h-full transform -rotate-90">
                            <circle cx="50" cy="50" r="45" fill="none" stroke="rgba(255,255,255,0.05)"
                                stroke-width="6" />
                            <circle id="score-circle" cx="50" cy="50" r="45" fill="none"
                                class="stroke-cyan-400 transition-all duration-1000" stroke-width="6"
                                stroke-dasharray="283" stroke-dashoffset="283" />
                        </svg>
                        <div class="absolute inset-0 flex flex-col items-center justify-center">
                            <span id="score-text" class="mono-text text-lg font-bold text-white">0%</span>
                        </div>
                    </div>
                    <div
                        class="flex-1 flex flex-col gap-3 text-[11px] font-medium text-slate-400 font-mono tracking-tight">
                        <div id="audit-length" class="flex items-center justify-between" title="Aim for 2000+ words">
                            <span>Word Count</span>
                            <span class="w-1.5 h-1.5 rounded-full bg-white/10 audit-dot"></span>
                        </div>
                        <div id="audit-entities" class="flex items-center justify-between" title="Use multiple headers">
                            <span>Heading Structure</span>
                            <span class="w-1.5 h-1.5 rounded-full bg-white/10 audit-dot"></span>
                        </div>
                        <div id="audit-visuals" class="flex items-center justify-between"
                            title="Include lists or tables">
                            <span>Tables & Lists</span>
                            <span class="w-1.5 h-1.5 rounded-full bg-white/10 audit-dot"></span>
                        </div>
                    </div>
                </div>
            </div>
        </aside>

        <!-- Main Content Area -->
        <main class="flex-1 flex flex-col gap-6 min-w-0">
            <!-- Top Command Bar (Spotlight Style) -->
            <div
                class="glass-panel mx-auto max-w-4xl w-full rounded-full p-2 pl-6 pr-2 flex items-center gap-4 cyber-glow-cyan shadow-[0_8px_32px_rgba(0,0,0,0.5)] z-20">
                <svg class="w-5 h-5 text-cyan-400 opacity-70" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                        d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path>
                </svg>
                <input id="keyword-input" type="text"
                    class="bg-transparent border-none text-lg text-white placeholder-slate-500 flex-1 outline-none font-medium h-12"
                    placeholder="Enter a topic or keyword to generate an article...">

                <div class="h-6 w-px bg-white/10"></div>

                <input id="niche-input" type="text"
                    class="bg-transparent border-none text-cyan-400 text-sm font-medium outline-none px-4 w-48 placeholder-slate-600 focus:text-cyan-300 transition-colors"
                    placeholder="Niche (e.g. SaaS, Finance)">

                <div class="h-6 w-px bg-white/10"></div>
                <div class="flex items-center gap-2">
                    <select id="profile-select" class="bg-transparent border-none text-fuchsia-400 text-sm font-bold outline-none px-2 cursor-pointer appearance-none uppercase tracking-wide text-center">
                        <option value="default" class="bg-[#050505]">WORKSPACE: DEFAULT</option>
                        <option value="tech_startup" class="bg-[#050505]">WORKSPACE: TECH</option>
                        <option value="legal_client" class="bg-[#050505]">WORKSPACE: LEGAL</option>
                    </select>
                    <button id="add-workspace-btn" title="Create new workspace"
                        class="w-9 h-9 rounded-full bg-fuchsia-500/15 hover:bg-fuchsia-500/25 border border-fuchsia-500/30 text-fuchsia-400 flex items-center justify-center transition-all shadow-[0_0_10px_rgba(217,70,239,0.2)] hover:shadow-[0_0_18px_rgba(217,70,239,0.3)] shrink-0">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"></path>
                        </svg>
                    </button>
                </div>

                <button id="generate-btn" title="Start generating content"
                    class="bg-white/10 hover:bg-white/20 text-white px-8 h-12 rounded-full font-semibold text-sm transition-all border border-white/5 hover:border-white/20 ml-2 tracking-wide">
                    GENERATE
                </button>
            </div>

            <!-- Agent Progress Pipeline -->
            <div class="flex items-center justify-center gap-12 py-2 select-none">
                <div id="agent-research"
                    class="flex flex-col items-center gap-2 text-slate-500 border border-transparent p-3 rounded-2xl transition-all">
                    <div
                        class="w-8 h-8 rounded-full border border-current flex items-center justify-center text-xs mono-text">
                        01</div>
                    <span class="text-[10px] uppercase font-bold tracking-widest text-slate-400">Research</span>
                </div>
                <!-- Connector -->
                <div class="h-px w-16 bg-gradient-to-r from-transparent via-slate-700 to-transparent"></div>

                <div id="agent-psychology"
                    class="flex flex-col items-center gap-2 text-slate-500 border border-transparent p-3 rounded-2xl transition-all">
                    <div
                        class="w-8 h-8 rounded-full border border-current flex items-center justify-center text-xs mono-text">
                        02</div>
                    <span class="text-[10px] uppercase font-bold tracking-widest text-slate-400">Strategy</span>
                </div>
                <!-- Connector -->
                <div class="h-px w-16 bg-gradient-to-r from-transparent via-slate-700 to-transparent"></div>

                <div id="agent-writer"
                    class="flex flex-col items-center gap-2 text-slate-500 border border-transparent p-3 rounded-2xl transition-all">
                    <div
                        class="w-8 h-8 rounded-full border border-current flex items-center justify-center text-xs mono-text">
                        03</div>
                    <span class="text-[10px] uppercase font-bold tracking-widest text-slate-400">Writing</span>
                </div>
            </div>

            <!-- Editor & Blueprint Split View -->
            <div class="flex-1 flex gap-6 min-h-0 relative z-10">
                <!-- Blueprint Column -->
                <div class="w-[380px] shrink-0 glass-panel rounded-2xl p-6 flex flex-col overflow-hidden">
                    <h2
                        class="text-[11px] font-bold text-slate-400 mb-6 uppercase tracking-widest bg-white/5 inline-block px-3 py-1 rounded">
                        Article Outline & Blueprint</h2>
                    <div id="blueprint-content" class="flex-1 overflow-y-auto pr-2 space-y-3">
                        <div class="text-slate-600 text-[13px] opacity-70 text-center mt-10 mono-text">Waiting for a
                            topic to be generated...</div>
                    </div>
                </div>

                <!-- Editor Column -->
                <div
                    class="flex-1 glass-panel rounded-2xl p-1 flex flex-col relative overflow-hidden bg-gradient-to-b from-white/[0.03] to-transparent">
                    <!-- Top Action Bar -->
                    <div class="h-14 border-b border-white/5 flex items-center justify-between px-6">
                        <span class="text-[11px] font-bold tracking-widest uppercase text-cyan-400/80 mono-text">Final
                            Draft Layout</span>
                        <div class="flex gap-2">
                            <button id="copy-md-btn" title="Copy as Markdown (Text with formatting symbols)"
                                class="px-4 py-2 rounded-lg bg-white/5 hover:bg-white/10 text-slate-300 text-[11px] uppercase font-bold tracking-wider transition-colors border border-white/5 shadow-sm">Copy
                                Markdown</button>
                            <button id="copy-html-btn" title="Copy as formatted HTML"
                                class="px-4 py-2 rounded-lg bg-white/5 hover:bg-white/10 text-slate-300 text-[11px] uppercase font-bold tracking-wider transition-colors border border-white/5 shadow-sm">Copy
                                Rich Text</button>
                        </div>
                    </div>

                    <!-- Viewer / Editor -->
                    <div class="flex-1 p-8 overflow-y-auto relative">
                        <!-- Read-only HTML render -->
                        <div id="article-content" class="prose-custom max-w-none">
                            <div class="h-full flex flex-col items-center justify-center opacity-20 pt-20">
                                <svg class="w-20 h-20 text-cyan-400 mb-6" fill="none" stroke="currentColor"
                                    viewBox="0 0 24 24" stroke-width="0.5">
                                    <path stroke-linecap="round" stroke-linejoin="round"
                                        d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10">
                                    </path>
                                </svg>
                                <span class="mono-text tracking-widest text-sm uppercase">Standing By</span>
                            </div>
                        </div>

                        <!-- Editable Textarea -->
                        <textarea id="article-editor"
                            class="w-full h-full min-h-[500px] bg-transparent text-slate-200 mono-text text-[13px] leading-relaxed resize-none outline-none hidden placeholder-slate-700"
                            spellcheck="false"
                            placeholder="Your draft will appear here. Edit this box freely..."></textarea>
                    </div>

                    <!-- Human Feedback Bar -->
                    <div id="approve-container" class="absolute bottom-6 left-6 right-6 hidden">
                        <button id="approve-btn"
                            title="Submit your edits so the AI can learn your writing style for future articles"
                            class="w-full bg-cyan-500/[0.15] hover:bg-cyan-500/25 border border-cyan-500/30 text-cyan-300 backdrop-blur-xl py-4 rounded-xl text-[12px] font-bold tracking-[0.1em] transition-all uppercase cyber-glow-cyan shadow-xl group">
                            Save Edits & Improve AI Writing Style
                            <span class="inline-block ml-2 group-hover:translate-x-1 transition-transform">→</span>
                        </button>
                    </div>
                </div>
            </div>
        </main>
    </div>

    <!-- PRE-GENERATION CLARIFICATION MODAL -->
    <div id="clarify-modal" class="fixed inset-0 z-50 flex items-center justify-center hidden">
        <!-- Backdrop -->
        <div class="absolute inset-0 bg-black/60 backdrop-blur-md" id="clarify-backdrop"></div>

        <!-- Modal Content -->
        <div class="relative w-full max-w-2xl glass-panel bg-white/[0.03] border border-cyan-500/20 rounded-2xl p-8 shadow-[0_0_50px_rgba(34,211,238,0.1)] transform transition-all scale-95 opacity-0"
            id="clarify-panel">
            <div class="absolute top-0 inset-x-0 h-1 bg-gradient-to-r from-cyan-500 to-magenta-500 rounded-t-2xl"></div>

            <div class="flex items-center gap-4 mb-6">
                <div
                    class="w-12 h-12 rounded-xl bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center text-cyan-400">
                    <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"
                            d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z">
                        </path>
                    </svg>
                </div>
                <div>
                    <h2 class="text-xl font-bold text-white tracking-tight">Agent Briefing</h2>
                    <p class="text-xs text-cyan-400/70 mono-text uppercase tracking-widest mt-1">Provide context for
                        better results</p>
                </div>
            </div>

            <div id="clarify-loading" class="py-12 flex flex-col items-center justify-center gap-4">
                <div class="w-8 h-8 rounded-full border-2 border-cyan-500 border-t-transparent animate-spin"></div>
                <p class="text-sm text-slate-400 mono-text animate-pulse">Analyzing keyword and generating questions...
                </p>
            </div>

            <div id="clarify-form" class="hidden space-y-6">
                <div id="questions-container" class="space-y-4">
                    <!-- Questions injected here by JS -->
                </div>

                <div class="flex justify-end gap-3 pt-4 border-t border-white/10">
                    <button id="clarify-skip-btn"
                        class="px-6 py-2.5 rounded-xl border border-white/10 text-slate-400 text-sm font-medium hover:bg-white/5 hover:text-white transition-colors">
                        Skip & Generate
                    </button>
                    <button id="clarify-submit-btn"
                        class="px-6 py-2.5 rounded-xl bg-cyan-500/20 border border-cyan-500/40 text-cyan-300 text-sm font-bold tracking-wide hover:bg-cyan-500/30 hover:shadow-[0_0_20px_rgba(34,211,238,0.2)] transition-all">
                        SUBMIT ANSWERS
                    </button>
                </div>
            </div>
        </div>
    </div>

    <!-- WORKSPACE CREATION MODAL -->
    <div id="workspace-modal-overlay" class="fixed inset-0 z-[110] flex items-center justify-center hidden bg-black/80 backdrop-blur-md">
        <div id="workspace-modal-panel" class="relative w-full max-w-sm bg-[#0a0a0c] border border-white/10 rounded-2xl p-8 shadow-[0_0_60px_rgba(217,70,239,0.1)] transform transition-all duration-300 scale-95 opacity-0">
            <div class="absolute top-0 inset-x-0 h-1 bg-gradient-to-r from-fuchsia-500 to-cyan-500 rounded-t-2xl"></div>

            <div class="flex items-center gap-3 mb-6">
                <div class="w-10 h-10 rounded-xl bg-fuchsia-500/10 border border-fuchsia-500/30 flex items-center justify-center text-fuchsia-400">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 4v16m8-8H4"></path>
                    </svg>
                </div>
                <div>
                    <h2 class="text-lg font-bold text-white tracking-tight">New Workspace</h2>
                    <p class="text-[10px] text-fuchsia-400/70 mono-text uppercase tracking-widest mt-0.5">Isolated AI memory partition</p>
                </div>
            </div>

            <div class="space-y-4">
                <div>
                    <label class="block text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2">Workspace Name</label>
                    <input id="modal-workspace-input" type="text" maxlength="40"
                        class="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-sm text-white placeholder-slate-600 outline-none focus:border-fuchsia-500/50 focus:bg-white/[0.08] transition-all"
                        placeholder="e.g. Health Blog, SaaS Startup">
                </div>
                <div class="flex justify-end gap-3 pt-2">
                    <button id="workspace-cancel-btn"
                        class="px-5 py-2.5 rounded-xl border border-white/10 text-slate-400 text-sm font-medium hover:bg-white/5 hover:text-white transition-colors">
                        Cancel
                    </button>
                    <button id="workspace-create-btn"
                        class="px-5 py-2.5 rounded-xl bg-fuchsia-500/20 border border-fuchsia-500/40 text-fuchsia-300 text-sm font-bold tracking-wide hover:bg-fuchsia-500/30 hover:shadow-[0_0_20px_rgba(217,70,239,0.2)] transition-all">
                        CREATE
                    </button>
                </div>
            </div>
        </div>
    </div>

    <!-- JS -->
    <script src="/static/js/console.js"></script>
</body>

</html>
```

### static/css/console.css
```css
/* ARES CONSOLE UI V3.1 
   Standard: Modern Dashboard / Semantic SEO Engine
*/

:root {
    --ares-bg: #0a0a0c;
    --ares-card: #141417;
    --ares-border: #27272a;
    --ares-neon: #00ff9d;
    --ares-magenta: #d946ef;
    --ares-cyan: #22d3ee;
    --ares-text: #f4f4f5;
    --ares-muted: #71717a;
    --font-mono: 'JetBrains Mono', monospace;
    --ease-tactical: cubic-bezier(0.16, 1, 0.3, 1);
}

* {
    box-sizing: border-box;
    scrollbar-width: thin;
    scrollbar-color: var(--ares-border) transparent;
}

body {
    background: var(--ares-bg);
    color: var(--ares-text);
    font-family: var(--font-mono);
    /* Force mono for the "hacker" aesthetic */
    margin: 0;
    height: 100vh;
    overflow: hidden;
}

/* Master Layout */
.dashboard-grid {
    display: grid;
    grid-template-columns: 280px 1fr 320px;
    width: 100vw;
    height: 100vh;
    background: var(--ares-bg);
}

/* Scrollable Content Panes */
.content-pane {
    height: 100%;
    overflow-y: auto !important;
    padding-bottom: 100px;
    /* Crucial: Space so the end isn't cut off */
}

/* Custom Scrollbar Logic */
::-webkit-scrollbar {
    width: 4px;
}

::-webkit-scrollbar-track {
    background: transparent;
}

::-webkit-scrollbar-thumb {
    background: var(--ares-border);
    border-radius: 10px;
}

::-webkit-scrollbar-thumb:hover {
    background: var(--ares-neon);
}

/* Sidebar & Glass Cards */
.sidebar,
.tactical-hub {
    background: var(--ares-bg);
    border-right: 1px solid var(--ares-border);
    overflow: hidden;
}

.tactical-hub {
    border-right: none;
    border-left: 1px solid var(--ares-border);
}

.glass-card {
    background: rgba(20, 20, 23, 0.6);
    border: 1px solid var(--ares-border);
    border-radius: 8px;
    transition: all 0.4s var(--ease-tactical);
}

/* Agent Pipeline Visuals */
.agent-node-mini {
    font-family: var(--font-mono);
    font-size: 0.65rem;
    color: var(--ares-muted);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    padding: 4px 12px;
    border: 1px solid transparent;
    border-radius: 4px;
    transition: all 0.5s var(--ease-tactical);
}

.agent-node-active {
    color: var(--ares-neon) !important;
    border-color: var(--ares-neon) !important;
    text-shadow: 0 0 8px rgba(0, 255, 157, 0.5);
    box-shadow: inset 0 0 10px rgba(0, 255, 157, 0.1);
}

.line-divider {
    height: 1px;
    width: 40px;
    background: var(--ares-border);
}

/* Input & Elite Button */
.input-keyword-refined {
    background: rgba(0, 0, 0, 0.3);
    border: 1px solid var(--ares-border);
    color: var(--ares-cyan);
    padding: 12px 16px;
    border-radius: 6px;
    font-family: var(--font-mono);
    width: 100%;
    transition: all 0.3s ease;
}

.input-keyword-refined:focus {
    outline: none;
    border-color: var(--ares-cyan);
    box-shadow: 0 0 15px rgba(34, 211, 238, 0.1);
}

.btn-generate-elite {
    background: var(--ares-cyan);
    color: var(--ares-bg);
    font-weight: bold;
    font-family: var(--font-mono);
    font-size: 0.7rem;
    padding: 0 24px;
    height: 44px;
    border-radius: 6px;
    cursor: pointer;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    transition: all 0.3s var(--ease-tactical);
}

.btn-generate-elite:hover:not(:disabled) {
    background: #fff;
    box-shadow: 0 0 20px rgba(34, 211, 238, 0.4);
}

.btn-generate-elite:disabled {
    opacity: 0.3;
    filter: grayscale(1);
    cursor: not-allowed;
}

/* Terminal Styling */
.terminal-body {
    font-family: var(--font-mono);
    background: rgba(0, 0, 0, 0.4);
    border-radius: 4px;
    padding: 15px;
    line-height: 1.6;
}

/* Audit Items */
.audit-item {
    display: flex;
    align-items: center;
    gap: 12px;
    font-size: 0.7rem;
    color: var(--ares-muted);
    margin-bottom: 8px;
}

.audit-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: #334155;
    transition: all 0.4s ease;
}

/* Status Indicator Pulse */
#status-indicator.animate-pulse {
    animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
}

@keyframes pulse {

    0%,
    100% {
        opacity: 1;
        transform: scale(1);
    }

    50% {
        opacity: .5;
        transform: scale(1.2);
    }
}

/* Typography Tag */
.mono-tag {
    font-family: var(--font-mono);
    font-size: 0.65rem;
    text-transform: uppercase;
    letter-spacing: 0.15em;
    font-weight: 700;
}
```

### static/js/api.js
```js
/* ── Ares Console — API Layer ───────────────────────────────────────── */

/**
 * Ping the backend health-check to verify Brave Search connectivity.
 * @returns {Promise<{status: string, brave_search: boolean}>}
 */
async function verifyMCPServer() {
    const resp = await fetch("/health", {
        method: "GET",
        signal: AbortSignal.timeout(8000),
    });
    if (!resp.ok) throw new Error(`Health check failed: ${resp.status}`);
    return resp.json();
}

/**
 * Trigger the full 3-phase generation pipeline.
 * @param {string} keyword
 * @returns {Promise<{post: object, blueprint: object}>}
 */
async function generateArticle(keyword) {
    const resp = await fetch(`/generate/${encodeURIComponent(keyword)}`, {
        method: "POST",
    });
    if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(err.detail || `Generation failed: ${resp.status}`);
    }
    return resp.json();
}

```

### static/js/console.js
```js
// ARES CONSOLE v4.0 - CYBER GLASS EXPERIMENT
let lastGeneratedMarkdown = "";

const els = {
    keywordInput: document.getElementById('keyword-input'),
    generateBtn: document.getElementById('generate-btn'),
    terminal: document.getElementById('terminal-body'),
    blueprintPane: document.getElementById('blueprint-content'),
    articlePane: document.getElementById('article-content'),
    scoreCircle: document.getElementById('score-circle'),
    scoreText: document.getElementById('score-text'),
    agentNodes: {
        research: document.getElementById('agent-research'),
        psychology: document.getElementById('agent-psychology'),
        writer: document.getElementById('agent-writer')
    },
    nicheInput: document.getElementById('niche-input'),
    profileSelect: document.getElementById('profile-select')
};

function terminalLog(agent, message, color = "#22d3ee") {
    const entry = document.createElement('div');
    entry.className = "flex bg-white/5 border border-white/5 rounded-md p-2 mt-2 animate-slideInRight text-slate-300";
    entry.innerHTML = `<span class="mr-2 shrink-0 w-[85px] tracking-wide" style="color: ${color}; font-weight: 600;">[${agent}]</span> <span class="flex-1 opacity-90">${message}</span>`;
    els.terminal.appendChild(entry);
    els.terminal.scrollTop = els.terminal.scrollHeight;
}

function updateAgentUI(activeNode) {
    Object.values(els.agentNodes).forEach(node => node.classList.remove('agent-node-active'));
    if (activeNode && els.agentNodes[activeNode]) {
        els.agentNodes[activeNode].classList.add('agent-node-active');
    }
}

function renderBlueprint(bp) {
    if (!bp) return;
    const audience = bp.target_audience || 'SEO Strategic Plan';
    let html = `<div class="mb-6"><h3 class="text-cyan-400 font-bold text-xs uppercase tracking-widest opacity-80">${audience}</h3></div>`;

    if (bp.outline_structure && Array.isArray(bp.outline_structure)) {
        html += `<div class="space-y-3">`;
        bp.outline_structure.forEach((item, idx) => {
            const heading = typeof item === 'object' ? (item.heading || item.title || "Section") : item;
            html += `<div class="p-4 bg-white/[0.02] border border-white/5 rounded-xl hover:bg-white/[0.04] transition-colors shadow-sm">
                        <div class="flex items-center gap-3">
                            <span class="text-cyan-500/50 mono-text text-[10px] uppercase font-bold tracking-widest">PHASE 0${idx + 1}</span>
                        </div>
                        <h4 class="text-slate-200 text-sm mt-1 font-medium leading-relaxed tracking-tight">${heading}</h4>
                     </div>`;
        });
        html += `</div>`;
    }
    els.blueprintPane.innerHTML = html;
}

let currentPostId = null;

function renderArticle(post) {
    if (!post || !post.content) return;
    lastGeneratedMarkdown = post.content;
    currentPostId = post.id;

    // Hide static viewer, show interactive editor
    els.articlePane.classList.add('hidden');
    const editor = document.getElementById('article-editor');
    const approveBtn = document.getElementById('approve-container');

    editor.value = post.content;
    editor.classList.remove('hidden');
    approveBtn.classList.remove('hidden');
}

// APPROVE & TRAIN EVENT
document.getElementById('approve-btn').addEventListener('click', async () => {
    if (!currentPostId) return;

    const editor = document.getElementById('article-editor');
    const updatedContent = editor.value;
    const btn = document.getElementById('approve-btn');

    btn.disabled = true;
    btn.innerText = "TRAINING MODEL... PLEASE WAIT";
    terminalLog("SYSTEM", "Saving your edits and teaching the AI your writing style...", "#22d3ee");

    try {
        const response = await fetch(`/posts/${currentPostId}/approve`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content: updatedContent })
        });

        if (!response.ok) throw new Error(`Server Error: ${response.status}`);

        const result = await response.json();

        // Switch back to rendered view
        editor.classList.add('hidden');
        document.getElementById('approve-container').classList.add('hidden');

        els.articlePane.innerHTML = marked.parse(result.content);
        els.articlePane.classList.remove('hidden');

        terminalLog("SUCCESS", "Success! The AI has learned from your changes.", "#22d3ee");

    } catch (err) {
        terminalLog("ERROR", `Training Failed: ${err.message}`, "#ef4444");
    } finally {
        btn.disabled = false;
        btn.innerHTML = `Save Edits & Improve AI Writing Style <span class="inline-block ml-2 group-hover:translate-x-1 transition-transform">→</span>`;
    }
});

function updateSEOAudit(content) {
    if (!content) return;

    // 1. Calculate Metrics
    const wordCount = content.split(/\s+/).length;
    const h2Count = (content.match(/^## /gm) || []).length;

    // 2. Detect "Data Blocks" (Tables or Lists)
    const hasTable = content.includes('|--') || content.includes('| :--');
    const hasList = (content.match(/^[*-] /gm) || []).length > 3;
    const hasDataBlocks = hasTable || hasList;

    // 3. Visual Scoring
    let score = 0;
    score += Math.min((wordCount / 2000) * 40, 40); // Word count weight
    score += Math.min((h2Count / 5) * 30, 30);      // Heading weight
    if (hasDataBlocks) score += 30;                 // Data block weight

    const finalScore = Math.round(score);
    const offset = 283 - (283 * Math.min(finalScore, 100)) / 100;

    els.scoreCircle.style.strokeDashoffset = offset;
    els.scoreText.innerText = `${Math.min(finalScore, 100)}%`;

    // 4. Update Audit Dots
    const lengthDot = document.querySelector('#audit-length .audit-dot');
    const entityDot = document.querySelector('#audit-entities .audit-dot');
    const visualDot = document.querySelector('#audit-visuals .audit-dot');

    if (lengthDot) lengthDot.style.background = wordCount > 1800 ? "#22d3ee" : "rgba(255,255,255,0.1)";
    if (entityDot) entityDot.style.background = h2Count >= 4 ? "#22d3ee" : "rgba(255,255,255,0.1)";
    if (visualDot) visualDot.style.background = hasDataBlocks ? "#22d3ee" : "rgba(255,255,255,0.1)";
    if (visualDot) visualDot.style.background = hasDataBlocks ? "#22d3ee" : "rgba(255,255,255,0.1)";
}

// -------------------------------------------------------------------------
// MODAL & CLARIFICATION LOGIC
// -------------------------------------------------------------------------
const modalEls = {
    modal: document.getElementById('clarify-modal'),
    panel: document.getElementById('clarify-panel'),
    loading: document.getElementById('clarify-loading'),
    form: document.getElementById('clarify-form'),
    container: document.getElementById('questions-container'),
    skipBtn: document.getElementById('clarify-skip-btn'),
    submitBtn: document.getElementById('clarify-submit-btn'),
    backdrop: document.getElementById('clarify-backdrop')
};

let currentQuestions = [];

function showModal() {
    modalEls.modal.classList.remove('hidden');
    // small delay to allow display block to apply before animating opacity
    setTimeout(() => {
        modalEls.panel.classList.remove('scale-95', 'opacity-0');
        modalEls.panel.classList.add('scale-100', 'opacity-100');
    }, 10);
}

function hideModal() {
    modalEls.panel.classList.remove('scale-100', 'opacity-100');
    modalEls.panel.classList.add('scale-95', 'opacity-0');
    setTimeout(() => {
        modalEls.modal.classList.add('hidden');
    }, 300); // match tailwind transition duration
}

modalEls.backdrop.addEventListener('click', hideModal);

modalEls.skipBtn.addEventListener('click', () => {
    hideModal();
    executeGeneration(""); // Generate with empty context
});

modalEls.submitBtn.addEventListener('click', () => {
    // Gather all answers
    let contextParts = [];
    const textareas = modalEls.container.querySelectorAll('textarea');
    textareas.forEach((ta, idx) => {
        const answer = ta.value.trim();
        if (answer) {
            contextParts.push(`Q: ${currentQuestions[idx]}\nA: ${answer}`);
        }
    });

    const finalContext = contextParts.join('\n\n');
    hideModal();
    executeGeneration(finalContext);
});

// MAIN EXECUTION TRIGGER (Step 1)
els.generateBtn.addEventListener('click', async () => {
    const kw = els.keywordInput.value.trim();
    if (!kw) return;

    els.generateBtn.disabled = true;

    // Reset UI State for new run
    els.terminal.innerHTML = "";
    els.articlePane.innerHTML = "";
    els.blueprintPane.innerHTML = "";
    els.articlePane.classList.add('hidden');
    updateAgentUI(null);

    // Show Modal Loading State
    modalEls.loading.classList.remove('hidden');
    modalEls.form.classList.add('hidden');
    showModal();

    terminalLog("SYSTEM", `Fetching briefing questions for: ${kw}...`, "#22d3ee");

    try {
        const response = await fetch(`/clarify?keyword=${encodeURIComponent(kw)}`);
        if (!response.ok) throw new Error("Failed to fetch questions");

        const data = await response.json();
        currentQuestions = data.questions || [];

        if (currentQuestions.length === 0) {
            // Fallback if AI fails to return questions
            hideModal();
            executeGeneration("");
            return;
        }

        // Render Questions in Modal
        modalEls.container.innerHTML = "";
        currentQuestions.forEach((q, idx) => {
            const block = document.createElement('div');
            block.className = 'bg-black/20 border border-white/5 rounded-xl p-4';
            block.innerHTML = `
                <label class="block text-sm font-medium text-slate-200 mb-2 leading-snug">${idx + 1}. ${q}</label>
                <textarea rows="2" class="w-full bg-white/5 border border-white/10 rounded-lg p-3 text-sm text-white placeholder-slate-600 outline-none focus:border-cyan-500/50 focus:bg-white/10 transition-all resize-none" placeholder="Type your answer here... (Optional)"></textarea>
            `;
            modalEls.container.appendChild(block);
        });

        modalEls.loading.classList.add('hidden');
        modalEls.form.classList.remove('hidden');
        terminalLog("SYSTEM", `Briefing agent ready. Awaiting user input.`, "#22d3ee");

    } catch (err) {
        terminalLog("ERROR", `Briefing Failed: ${err.message}. Skipping to generation...`, "#ef4444");
        hideModal();
        executeGeneration("");
    }
});

// MAIN GENERATION LOOP (Step 2)
async function executeGeneration(userContext) {
    const kw = els.keywordInput.value.trim();
    const rawNiche = els.nicheInput ? els.nicheInput.value.trim() : "";
    const niche = rawNiche ? rawNiche : "default";

    terminalLog("SYSTEM", `Compiling context and starting generation...`, "#22d3ee");

    try {
        const response = await fetch(`/generate/${encodeURIComponent(kw)}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ niche: niche, context: userContext })
        });

        if (!response.ok) throw new Error(`Server Error: ${response.status}`);

        const reader = response.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let done = false;

        while (!done) {
            const { value, done: readerDone } = await reader.read();
            done = readerDone;
            if (value) {
                const chunk = decoder.decode(value, { stream: true });
                const lines = chunk.split('\n\n');

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        const jsonStr = line.replace('data: ', '').trim();
                        if (!jsonStr) continue;

                        try {
                            const payload = JSON.parse(jsonStr);

                            switch (payload.event) {
                                case 'debug':
                                    terminalLog("SYS-DEBUG", payload.message, "#fbbf24");
                                    break;
                                case 'phase1_start':
                                    updateAgentUI('research');
                                    terminalLog("ENGINE", payload.message, "#d946ef");
                                    break;
                                case 'phase2_start':
                                    updateAgentUI('psychology');
                                    terminalLog("PSYCHOLOGY", payload.message, "#d946ef");
                                    break;
                                case 'phase2_complete':
                                    renderBlueprint(payload.blueprint);
                                    terminalLog("PSYCHOLOGY", "Article strategy mapped.", "#d946ef");
                                    break;
                                case 'phase3_start':
                                    updateAgentUI('writer');
                                    terminalLog("WRITER", payload.message, "#22d3ee");
                                    break;
                                case 'complete':
                                    renderArticle(payload.post);
                                    updateSEOAudit(payload.post.content);
                                    terminalLog("SUCCESS", "Article successfully generated and checked!", "#22d3ee");
                                    break;
                                case 'error':
                                    terminalLog("ERROR", `Generation Failed: ${payload.message}`, "#ef4444");
                                    break;
                            }
                        } catch (e) {
                            console.error("Failed to parse SSE chunk:", jsonStr, e);
                        }
                    }
                }
            }
        }

    } catch (err) {
        terminalLog("ERROR", `Connection Failed: ${err.message}`, "#ef4444");
    } finally {
        els.generateBtn.disabled = false;
        updateAgentUI(null);
    }
}

// CLIPBOARD HANDLERS
document.getElementById('copy-md-btn').addEventListener('click', () => {
    if (!lastGeneratedMarkdown) return;
    navigator.clipboard.writeText(lastGeneratedMarkdown).then(() => {
        const btn = document.getElementById('copy-md-btn');
        btn.innerText = "COPIED!";
        setTimeout(() => btn.innerText = "Copy Markdown", 2000);
    });
});

document.getElementById('copy-html-btn').addEventListener('click', () => {
    const html = els.articlePane.innerHTML;
    if (!html) return;
    navigator.clipboard.writeText(html).then(() => {
        const btn = document.getElementById('copy-html-btn');
        btn.innerText = "COPIED!";
        setTimeout(() => btn.innerText = "Copy Rich Text", 2000);
    });
});

// --- AI BRAIN LOGIC ---
const brainEls = {
    modal: document.getElementById('brain-modal'),
    backdrop: document.getElementById('brain-backdrop'),
    panel: document.getElementById('brain-panel'),
    openBtn: document.getElementById('open-brain-btn'),
    closeBtn: document.getElementById('close-brain-btn'),
    container: document.getElementById('rules-container'),
    input: document.getElementById('new-rule-input'),
    addBtn: document.getElementById('add-rule-btn')
};

function toggleBrain(show) {
    if (show) {
        brainEls.modal.classList.remove('hidden');
        setTimeout(() => {
            brainEls.backdrop.classList.remove('opacity-0');
            brainEls.panel.classList.remove('translate-x-full');
        }, 10);
        loadRules();
    } else {
        brainEls.backdrop.classList.add('opacity-0');
        brainEls.panel.classList.add('translate-x-full');
        setTimeout(() => brainEls.modal.classList.add('hidden'), 500);
    }
}

brainEls.openBtn.addEventListener('click', () => toggleBrain(true));
brainEls.closeBtn.addEventListener('click', () => toggleBrain(false));
brainEls.backdrop.addEventListener('click', () => toggleBrain(false));

async function loadRules() {
    brainEls.container.innerHTML = '<div class="text-slate-500 text-xs text-center mono-text animate-pulse py-10">Accessing memory blocks...</div>';
    try {
        const profile = els.profileSelect ? els.profileSelect.value : "default";
        const res = await fetch('/rules?profile_name=' + profile);
        const rules = await res.json();

        if (rules.length === 0) {
            brainEls.container.innerHTML = `
                <div class="flex flex-col items-center justify-center py-20 opacity-30">
                    <svg class="w-12 h-12 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg>
                    <p class="text-xs mono-text">Memory Bank Empty</p>
                </div>
            `;
            return;
        }

        brainEls.container.innerHTML = rules.map(r => `
            <div class="group bg-white/[0.03] border border-white/5 rounded-2xl p-4 hover:bg-white/[0.05] hover:border-white/10 transition-all relative">
                <div class="flex gap-4 items-start">
                    <div class="w-1.5 h-1.5 rounded-full bg-cyan-500 mt-2 shrink-0 cyber-glow-cyan shadow-[0_0_8px_rgba(34,211,238,0.5)]"></div>
                    <p class="text-sm text-slate-300 leading-relaxed pr-8 font-medium">${r.rule_description}</p>
                </div>
                <button onclick="deleteRule(${r.id})" class="absolute top-4 right-4 text-slate-600 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-all">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
                </button>
            </div>
        `).join('');
    } catch (e) {
        brainEls.container.innerHTML = '<div class="text-red-400/60 text-xs text-center p-10">Error: Failed to connect to Neural Bank.</div>';
    }
}

brainEls.addBtn.addEventListener('click', async () => {
    const text = brainEls.input.value.trim();
    if (!text) return;

    brainEls.addBtn.disabled = true;
    try {
        const profile = els.profileSelect ? els.profileSelect.value : "default";
        const res = await fetch('/rules', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({rule_description: text, profile_name: profile})
        });
        if (res.ok) {
            brainEls.input.value = '';
            loadRules();
        }
    } finally {
        brainEls.addBtn.disabled = false;
    }
});

async function deleteRule(id) {
    try {
        const res = await fetch(`/rules/${id}`, { method: 'DELETE' });
        if (res.ok) loadRules();
    } catch (e) {
        console.error("Failed to delete rule", e);
    }
}

els.profileSelect.addEventListener('change', () => {
    if (!brainEls.modal.classList.contains('hidden')) {
        loadRules();
    }
});

// -------------------------------------------------------------------------
// WORKSPACE CREATION MODAL LOGIC
// -------------------------------------------------------------------------
const wsEls = {
    overlay: document.getElementById('workspace-modal-overlay'),
    panel: document.getElementById('workspace-modal-panel'),
    input: document.getElementById('modal-workspace-input'),
    createBtn: document.getElementById('workspace-create-btn'),
    cancelBtn: document.getElementById('workspace-cancel-btn'),
    openBtn: document.getElementById('add-workspace-btn')
};

function toggleWorkspaceModal(isVisible) {
    if (isVisible) {
        wsEls.overlay.classList.remove('hidden');
        wsEls.input.value = '';
        setTimeout(() => {
            wsEls.panel.classList.remove('scale-95', 'opacity-0');
            wsEls.panel.classList.add('scale-100', 'opacity-100');
            wsEls.input.focus();
        }, 10);
    } else {
        wsEls.panel.classList.remove('scale-100', 'opacity-100');
        wsEls.panel.classList.add('scale-95', 'opacity-0');
        setTimeout(() => wsEls.overlay.classList.add('hidden'), 300);
    }
}

function createWorkspace() {
    const raw = wsEls.input.value.trim();
    if (!raw) return;

    const slug = raw.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '');
    if (!slug) return;

    // Prevent duplicates
    const existing = Array.from(els.profileSelect.options).find(o => o.value === slug);
    if (existing) {
        els.profileSelect.value = slug;
        els.profileSelect.dispatchEvent(new Event('change'));
        toggleWorkspaceModal(false);
        return;
    }

    const option = document.createElement('option');
    option.value = slug;
    option.textContent = `WORKSPACE: ${raw.toUpperCase()}`;
    option.className = 'bg-[#050505]';

    els.profileSelect.appendChild(option);
    els.profileSelect.value = slug;
    els.profileSelect.dispatchEvent(new Event('change'));

    toggleWorkspaceModal(false);
    terminalLog("SYSTEM", `Workspace "${raw}" created and activated.`, "#d946ef");
}

wsEls.openBtn.addEventListener('click', () => toggleWorkspaceModal(true));
wsEls.cancelBtn.addEventListener('click', () => toggleWorkspaceModal(false));
wsEls.overlay.addEventListener('click', (e) => {
    if (e.target === wsEls.overlay) toggleWorkspaceModal(false);
});
wsEls.createBtn.addEventListener('click', createWorkspace);
wsEls.input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') createWorkspace();
});
```
