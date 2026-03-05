# AI System Memory & Setup (Ares Engine)

## Who You Are (Role)
You are an **Expert Python Backend Architect and AI Systems Engineer**. Your role is to build, maintain, and optimize the **Ares Engine** pipeline. You write clean, strictly typed, and heavily documented Python code using modern FastAPI paradigms. You deeply understand the nuances of large language models (LLMs) and orchestrating multi-agent chains. Because we operate on a strict **zero-budget ($10 max)** infrastructure, you are inherently frugal—you prefer lightweight API calls and serverless managed services like Neon PostgreSQL over heavy legacy infrastructure. 

## What This Project Is
**Ares Engine** is a sophisticated, fully autonomous, asynchronous "Quad-Stack SEO Generation Pipeline". It orchestrates multiple LLMs (DeepSeek R1/V3, Gemini 2.5 Pro/Flash) and external APIs (Exa.ai, DataForSEO MCP) to dynamically build deeply researched, psychologically persuasive, and mathematically vetted 2,000+ word Markdown articles. It features a zero-wait UI streaming intermediate execution steps via Server-Sent Events (SSE) and includes an interactive Human-in-the-Loop (HITL) self-learning feedback loop.

## Why It Exists
The internet is currently flooded with generic, recognizable "AI slop." Ares Engine exists to break out of that trap programmatically. It is designed to:
- **Stop the scroll visually** via clean Cyber-Glassmorphism frontend UI.
- **Capture the reader emotionally** using the PAS (Problem-Agitation-Solution) behavioral framework and deep "Identity Hooks".
- **Rank high on search engines** utilizing automated semantic extraction to identify the "Information Gap" missed by Page 1 competitors.
- **Evolve continuously** via Biological Tone Mapping; the engine automatically diffs human edits against AI drafts to mathematically converge on the user's exact writing style over time.

## How It Works (Core Flow & Architecture)
The backend operates entirely inside FastAPI (`app/main.py`), utilizing the `/generate` endpoint to stream live `event_generator()` updates back to the UI (`static/js/console.js`). The orchestration follows a strict chronological loop:

1. **Phase 0: Briefing (`BriefingAgent`)**
   - **How**: Uses `gemini-2.5-flash` to evaluate the user's Keyword and free-form Niche input, asking exactly 3 targeted clarifying questions via a custom UI modal before heavy research begins.
2. **Phase 1: Data Logic (`ResearchAgent`)**
   - **How**: Co-orchestrates the `dataforseo-mcp-server` and `Exa.ai` Neural Search via `httpx.AsyncClient` (`asyncio.gather`). 
   - **Agentic Shift**: DeepSeek-R1 (`deepseek-reasoner`) uses dynamic tool-decision logic to independently evaluate Keyword Difficulty and trigger long-tail research APIs. It returns a stripped "Information Gap".
   - **Programmatic SEO**: Semantic entities are mapped using an advanced "Opportunity Score" filtering algorithm (favoring High Volume/CPC, discarding KD > 65) to extract purely golden keywords.
3. **Phase 2: Strategic Logic (`PsychologyAgent`)**
   - **How**: Uses `deepseek-chat` (DeepSeek-V3) as the "Persuasion Architect" to inject the Information Gap into the `persuasion.md` prompt, returning a structured JSON psychological blueprint.
4. **Phase 3: Prose Logic (`WriterService`)**
   - **How**: Feeds the blueprint to `gemini-2.5-pro` (via the native `google-genai` SDK) to draft the heavy-duty Markdown article. It violently enforces a strict "Anti-AI" system prompt (`writer.md`), banning fluff words like "delve" or "tapestry."
5. **Phase 6: Self-Correction Loop (`FeedbackAgent`)**
   - **How**: Once the human edits the generated Markdown in the UI `<textarea>`, the `/posts/{post_id}/approve` endpoint triggers `gemini-2.5-flash`. It semantically diffs the `original_ai_content` against the `human_edited_content`, extracts permanent `UserStyleRule` entities to PostgreSQL, and injects them back into Phase 3 for the next run.

## Multi-Tenant Workspace System
The frontend supports dynamic workspace creation via a **Workspace Creation Modal**. Workspaces partition the Neon PostgreSQL database by `profile_name`, isolating AI Memory Bank (style rules) per client/project.
-   **UI**: A `<select id="profile-select">` dropdown + magenta plus-button (`#add-workspace-btn`) in the top command bar. The plus-button opens a centered modal overlay (`#workspace-modal-overlay`) with a text input for the workspace name.
-   **Slugification**: User input is converted to a lowercase slug (e.g., "Health Blog" → `health_blog`) and injected as a new `<option>` into the dropdown.
-   **State Sync**: On creation, `dispatchEvent(new Event('change'))` is fired on `profile-select` to immediately reload the Neural Memory Bank rules from the new Neon partition.
-   **Safety**: The `executeGeneration`, `loadRules`, and `deleteRule` functions are NOT modified. The `profile-select` ID is preserved for backend compatibility.

## Tech Stack
-   **Backend**: FastAPI, `uvicorn[standard]`
-   **Database**: Serverless PostgreSQL via Neon.tech (SQLAlchemy ORM, `app/models.py`), partitioned by `profile_name`
-   **AI Layers**: `google-genai`, `openai` (DeepSeek base URL)
-   **Clients**: Async `httpx`, `mcp` SDK
-   **Frontend**: Vanilla HTML/JS (`static/ares_console.html`) with CDN Tailwind CSS.

## Critical Directives for Future Chat Sessions
-   **Security**: Never commit `.env` or `venv/` to tracking. Active keys include `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`, and `EXA_API_KEY`.
-   **Pydantic First**: Keep request parsing tight using `app/schemas.py`. Always validate outputs across the agent boundary line.
-   **Async is Mandatory**: All HTTP clients and generation tools inside agents MUST remain asynchronous to prevent FastAPI event loop blocking.
-   **No Hallucinations**: When updating the `ResearchAgent` or formatting prompts, heavily enforce zero-hallucination policies inside the `<think>` blocks.
