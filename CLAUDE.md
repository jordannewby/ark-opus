# Ares Engine

## Project Overview
Ares Engine is a sophisticated, multi-agent AI content generation pipeline designed to produce deep, persuasive, and heavily vetted 2,000+ word articles. It is built entirely on a strict **$10 budget** using predominantly zero-cost tools and optimized API models.

The system is designed to stop scrolling visually, capture the reader emotionally using the PAS (Problem-Agitation-Solution) psychological framework, and rank high utilizing automated SEO extraction.

## Core Flow & Architecture 
The master orchestration route (`/generate/{keyword}`) located in `app/main.py` chains three primary agents:

1.  **Phase 1: Research (`ResearchAgent`)**
    - **Location**: `app/services/research_service.py`
    - **Function**: Uses the Brave Web Search API to scrape live data for a specific keyword. Extracts top competitor H2s, "People Also Ask" metrics, and semantic entities.
    - **Cost-Saving Measure**: Results are mapped to a local SQLite cache table (`ResearchCache`) to drastically reduce API requests and stay within budget.
2.  **Phase 2: Psychology Blueprint (`PsychologyAgent`)**
    - **Location**: `app/services/psychology_agent.py`
    - **Function**: Utilizes Google Gemini (`gemini-2.5-flash`) via the `GEMINI_PSYCH_API_KEY` to draft a deep behavioral blueprint. Applies the PAS framework and generates specific "Identity Hooks" to target the reader.
3.  **Phase 3: Content Writer (`WriterService`)**
    - **Location**: `app/services/writer_service.py`
    - **Function**: Acts as the master editor. Takes the psychological blueprint and SEO entities, feeding them into another Gemini (`gemini-2.5-flash`) stream (via `GEMINI_API_KEY`) to generate a massive, fully formatted Markdown article that strictly adheres to anti-AI constraints (e.g., removing fluff and corporate speak).

## Tech Stack
-   **Backend**: FastAPI (Python)
-   **Database**: SQLite (via SQLAlchemy ORM)
-   **Server Engine**: Uvicorn (`uvicorn[standard]`)
-   **AI Integration**: `google-genai` (Gemini Flash Models)
-   **Web Client**: `httpx` (for Async Requests)

## File & Folder Structure
```
app/
├── main.py                     # Master orchestration and endpoints
├── models.py                   # SQLAlchemy schema (Post, ResearchCache)
├── schemas.py                  # Pydantic validation schemas
├── database.py                 # SQLite configuration
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
