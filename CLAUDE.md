# Ares Engine

**Stack**: FastAPI + Neon PostgreSQL + DeepSeek-R1/V3 + Claude 3.5 Sonnet + Exa.ai + DataForSEO MCP
**Budget**: $10 max — prefer lightweight, serverless

## Key Paths
- `app/main.py` — FastAPI endpoints: `/generate` (SSE), `/approve`, `/clarify`, `/rules`, `/workspaces`, `/campaigns`
- `app/services/` — Agents: briefing, research, source_verification, psychology, writer, readability, feedback, research_intel, writer_intel, cartographer
- `app/models.py` — ORM: Post, UserStyleRule, ResearchCache, Workspace, ResearchRun, NichePlaybook, WriterRun, WriterPlaybook, ContentCampaign, VerifiedSource, FactCitation
- `app/schemas.py` — Pydantic request/response schemas
- `app/domain_tiers.py` — 4-tier domain credibility lists
- `app/services/prompts/` — LLM prompt templates (writer.md, persuasion.md)
- `app/database.py` — Neon PostgreSQL (SQLAlchemy, pool_pre_ping, keepalives)
- `static/` — Frontend (ares_console.html, js/console.js, js/api.js)

## Rules
- **Async mandatory** — all HTTP clients and generation calls must use async/await
- **Pydantic-first** — validate at every agent boundary via `app/schemas.py`
- **Multi-tenant** — all DB queries must filter by `profile_name`; cache uses composite key `(keyword, profile_name, niche)`
- **DeepSeek API** — all LLM calls use DeepSeek via httpx (`deepseek-chat` for briefing/feedback/intel, `deepseek-reasoner` for research/verification/cartographer)
- **SSL retry** — post-generation `db.commit()` in `event_generator()` uses `nonlocal db` + `OperationalError` catch to get fresh `SessionLocal()` if Neon drops connection
- **No fake assets / no fabricated data** — writer prompt bans invented templates, tools, stats; must use only verified citation map facts
- **Prompt files read-only** — never modify `app/services/prompts/*.md` without explicit approval
- **Niche normalization** — always use `normalize_niche()` helper: `strip().lower().replace(" ", "-")`
- **Frontend state** — clear `lastGeneratedMarkdown`, `currentPostId`, `currentQuestions` before each generation
- **Exa metadata preservation** — all Exa search functions must preserve `publishedDate` + `score` via `url_metadata_map` pattern, merged into extract results for Phase 1.5 scoring
- **Source credibility threshold** — 45.0/100 minimum (53% pass rate). 7-factor base scoring (85pts max) + rescue bonus (15pts max) for borderline sources
- **API keys** — ANTHROPIC_API_KEY, DEEPSEEK_API_KEY, EXA_API_KEY, DATAFORSEO_LOGIN, DATAFORSEO_PASSWORD (`.env` only)

## NEVER
- Never rewrite entire files for small logic changes — use targeted edits
- Never commit `.env`, `venv/`, `blog.db`, `__pycache__/`
- Never swap the database to SQLite or any non-Neon provider
- Never duplicate source code into `.md` memory files
- Never introduce paid dependencies without admin approval
- Never remove `pool_pre_ping` or keepalive args from `database.py`

## Architecture
Full pipeline (7 phases), agent logic, scoring algorithms, intelligence loops, and workspace system: `@docs/architecture.md`
