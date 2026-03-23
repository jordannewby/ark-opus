# Ares Engine

**Stack**: FastAPI + Neon PostgreSQL + DeepSeek-R1/V3 + Claude Sonnet 4 + Exa.ai + DataForSEO MCP
**Budget**: $10 max — prefer lightweight, serverless

## Key Paths
- `app/main.py` — FastAPI endpoints: `/generate` (SSE), `/approve`, `/clarify`, `/rules`, `/workspaces`, `/campaigns`
- `app/services/` — Agents: briefing, research, source_verification, claim_verification, psychology, writer, readability, feedback, research_intel, writer_intel, cartographer
- `app/models.py` — ORM: Post, UserStyleRule, ResearchCache, Workspace, ResearchRun, NichePlaybook, WriterRun, WriterPlaybook, ContentCampaign, VerifiedSource, FactCitation
- `app/schemas.py` — Pydantic request/response schemas
- `app/domain_tiers.py` — 4-tier domain credibility lists
- `app/services/prompts/` — LLM prompt templates (writer.md, persuasion.md)
- `app/database.py` — Neon PostgreSQL (SQLAlchemy, pool_pre_ping, keepalives)
- `static/` — Frontend (ares_console.html, js/console.js)

## Rules
- **Async mandatory** — all HTTP clients and generation calls must use async/await
- **Pydantic-first** — validate at every agent boundary via `app/schemas.py`
- **Multi-tenant** — all DB queries must filter by `profile_name`; cache uses composite key `(keyword, profile_name, niche)`
- **LLM routing** — DeepSeek via httpx (`deepseek-chat` for briefing/feedback/intel, `deepseek-reasoner` for research/verification/cartographer); Anthropic Claude Sonnet 4 (`claude-sonnet-4-20250514`) for writer via `langchain-anthropic`
- **SSL retry** — post-generation `db.commit()` in `event_generator()` uses `nonlocal db` + `OperationalError` catch to get fresh `SessionLocal()` if Neon drops connection
- **No fake assets / no fabricated data** — writer prompt bans invented templates, tools, stats; must use only verified citation map facts
- **Prompt files read-only** — never modify `app/services/prompts/*.md` without explicit approval
- **Niche normalization** — always use `normalize_niche()` helper: `strip().lower().replace(" ", "-")`
- **Frontend state** — clear `lastGeneratedMarkdown`, `currentPostId`, `currentQuestions` before each generation; `currentAbortController` cancels in-flight SSE before new generation
- **No native dialogs** — use `showConfirmModal(message, onConfirm)` in console.js instead of `window.confirm()`; confirm modal HTML in ares_console.html
- **Exa metadata preservation** — all Exa search functions must preserve `publishedDate` + `score` via `url_metadata_map` pattern, merged into extract results for Phase 1.5 scoring
- **Source credibility threshold** — 45.0/100 minimum (53% pass rate). 7-factor base scoring (85pts max) + rescue bonus (15pts max) for borderline sources
- **Keyword relevance fallback** — `_keyword_relevance_score()` in research_service.py tokenizes slug keywords and checks source relevance; if <3 relevant sources after niche-filtered search, unfiltered Exa fallback + broad backfill fire automatically
- **Claim verification gate** — post-writer claim cross-referencing via `claim_verification_agent.py`; fabricated citations (URL not in fact map) = zero-tolerance; ungrounded citations (URL exists but claim doesn't match) = zero-tolerance normally, softened to 15% when low topical coverage detected
- **Banned word sanitizer** — deterministic post-LLM regex in `writer_service._sanitize_banned_words()` catches inflected forms (leveraging, optimized, landscapes) after Claude generates; never rely solely on prompt instructions
- **MCP retry** — all DataForSEO MCP `session.call_tool()` calls must use `mcp_call_with_retry()` wrapper from `research_service.py` (exponential backoff: 1s→2s→4s, max 3 retries on 429/rate-limit)
- **Centralized config** — operational constants (timeouts, thresholds, tuning params) live in `app/settings.py`; add new values there and import in services
- **Structured logging** — all service files use `logger = logging.getLogger(__name__)`; never use bare `print()` for debug output
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
