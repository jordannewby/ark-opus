# Ares Engine

**Stack**: FastAPI + Neon PostgreSQL + DeepSeek-R1/V3 + Gemini 2.5 Pro/Flash + Exa.ai (Native Tools) + DataForSEO MCP
**Budget**: $10 max — prefer lightweight, serverless

## Key Paths
- `app/main.py` — FastAPI app, `/generate` SSE endpoint, `/posts/{id}/approve`, `/clarify`, `/rules`, `/workspaces`
- `app/services/` — All agents: briefing_agent, research_service, psychology_agent, writer_service, feedback_service, research_intel_service
- `app/models.py` — ORM models: `Post`, `UserStyleRule`, `ResearchCache`, `Workspace`, `ResearchRun`, `NichePlaybook`
- `app/schemas.py` — Pydantic schemas (includes `WorkspaceCreate`, `WorkspaceResponse`, `StyleRuleCreate`, `ResearchRunCapture`, `NichePlaybookResponse`)
- `app/services/prompts/` — LLM prompt templates (writer.md, persuasion.md)
- `static/` — Frontend (ares_console.html, js/console.js, js/api.js)
- `app/database.py` — Neon PostgreSQL connection (SQLAlchemy, pool_pre_ping, keepalives)
- `app/settings.py` — Environment + API key loading

## Rules
- **Async mandatory** — all HTTP clients + generation calls must be async
- **Pydantic-first** — validate at every agent boundary via `app/schemas.py`
- **Zero Hallucination** — enforce strict tool schemas in ResearchAgent; hallucinated tools trigger an error block to force R1 self-correction
- **Iterative Tooling** — ResearchAgent runs an iterative loop (max 5) allowing R1 to mix DataForSEO MCP tools with native Exa tools (`exa_scout_search`, `exa_extract_full_text`)
- **Multi-tenant** — all DB queries must filter by `profile_name` (workspace scope)
- **Research Intelligence** — ResearchAgent self-improves via a 4-phase loop: Capture ($0) → Recall (~200 tokens) → Reinforce ($0 on /approve) → Distill (~$0.001/10 runs via Gemini Flash). Niche playbooks are scoped by `(profile_name, niche)`.
- **API keys** — GEMINI_API_KEY, DEEPSEEK_API_KEY, EXA_API_KEY, DATAFORSEO_LOGIN, DATAFORSEO_PASSWORD (in .env only)

## NEVER
- Never rewrite entire files for small logic changes — use targeted edits
- Never commit `.env`, `venv/`, `blog.db`, `__pycache__/`
- Never swap the database to SQLite or any non-Neon provider
- Never modify `app/services/prompts/*.md` without explicit approval
- Never duplicate source code into `.md` memory files
- Never introduce paid dependencies without admin approval
- Never remove `pool_pre_ping` or keepalive args from `database.py`

## Architecture
Full pipeline, agent logic, and workspace system details are in docs/architecture.md (Read on-demand only).
