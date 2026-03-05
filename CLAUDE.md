# Ares Engine

**Stack**: FastAPI + Neon PostgreSQL + DeepSeek R1/V3 + Gemini 2.5 Pro/Flash + Exa.ai + DataForSEO MCP
**Budget**: $10 max — prefer lightweight, serverless

## Key Paths
- `app/main.py` — FastAPI app, `/generate` SSE endpoint, `/posts/{id}/approve`, `/clarify`
- `app/services/` — All agents: briefing_agent, research_service, psychology_agent, writer_service, feedback_service
- `app/models.py` + `app/schemas.py` — ORM models + Pydantic schemas
- `app/services/prompts/` — LLM prompt templates (writer.md, persuasion.md)
- `static/` — Frontend (ares_console.html, js/console.js, js/api.js)
- `app/database.py` — Neon PostgreSQL connection (SQLAlchemy)
- `app/settings.py` — Environment + API key loading

## Rules
- **Async mandatory** — all HTTP clients + generation calls must be async (no blocking FastAPI event loop)
- **Pydantic-first** — validate at every agent boundary via `app/schemas.py`
- **No hallucinations** — enforce zero-hallucination in ResearchAgent `<think>` blocks
- **Never commit** — `.env`, `venv/`, `blog.db`, `__pycache__/`
- **API keys** — GEMINI_API_KEY, DEEPSEEK_API_KEY, EXA_API_KEY (in .env only)

## Architecture
Full pipeline, agent logic, and workspace system details: @docs/architecture.md
