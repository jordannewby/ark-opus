# Ares Engine

## NEVER
- Never rewrite entire files for small logic changes — use targeted edits
- Never commit `.env`, `venv/`, `blog.db`, `__pycache__/`
- Never swap the database to SQLite or any non-Neon provider
- Never duplicate source code into `.md` memory files
- Never introduce paid dependencies without admin approval
- Never remove `pool_pre_ping` or keepalive args from `database.py`
- Never pass user-controlled or external data into LLM prompts without `sanitize_prompt_input()` or `sanitize_external_content()` from `app/security.py`
- Never use `innerHTML` in frontend without wrapping in `DOMPurify.sanitize()`
- Never use bare `print()` — use `logger = logging.getLogger(__name__)` (Windows cp1252 encoding crashes on emoji)

**Stack**: FastAPI + Neon PostgreSQL + GLM-5 Thinking + DeepSeek V3 + Claude Sonnet 4.5 + Exa.ai + DataForSEO MCP
**Budget**: $10-$20 max — prefer lightweight, serverless

## Key Paths
- `app/main.py` — FastAPI endpoints, SSE `event_generator()` pipeline spine, `_normalize_url()` helper, `SecurityHeadersMiddleware`, rate limiting
- `app/auth.py` — API key authentication (`verify_api_key` dependency, SHA256 hashing)
- `app/security.py` — Prompt injection sanitization (`sanitize_prompt_input`, `sanitize_external_content`)
- `app/models.py` — ORM: Post, UserStyleRule, UserStyleRuleArchive, ResearchCache, Workspace, ResearchRun, NichePlaybook, WriterRun, WriterPlaybook, ContentCampaign, VerifiedSource, FactCitation, ProfileSettings, DomainCredibilityCache, ApiKey
- `app/schemas.py` — Pydantic request/response schemas (all string fields have `Field(max_length=...)` constraints)
- `app/settings.py` — All operational constants, env vars, configurable settings registry
- `app/database.py` — Neon PostgreSQL (SQLAlchemy, pool_pre_ping, keepalives, FK constraints, migration versioning)
- `app/glm_client.py` — GLM-5 API client (semaphore concurrency + 5xx retry)
- `app/exa_client.py` — Exa API client (rate limiting + 5xx retry)
- `app/domain_tiers.py` — 4-tier domain credibility lists
- `app/services/` — Agents: briefing, research, exa_research, source_verification, claim_verification, psychology, writer (writer_service + writer_agent_graph), readability, feedback, research_intel, writer_intel, cartographer
- `app/services/prompts/` — LLM prompt templates (writer.md, persuasion.md) — **read-only without explicit approval**
- `static/` — Frontend (ares_console.html, js/console.js)

## Security Rules
- **API key auth** — all endpoints (except `/health`, `/`) require `X-API-Key` header validated by `verify_api_key()` from `app/auth.py`; SHA256 hashed against `api_keys` table
- **Admin secret** — `ADMIN_SECRET` env var for `/admin/api-keys`; validated with `secrets.compare_digest()` (timing-safe)
- **Prompt injection defense** — every LLM prompt boundary must sanitize inputs:
  - User-controlled data (keyword, niche, context, briefing answers): `sanitize_prompt_input()` with XML boundary tags
  - External/LLM-derived data (Exa content, style rules, claim feedback, psychology directives, web content): `sanitize_external_content()`
  - Never pass raw user or external strings into f-string prompt templates
- **Input length bounds** — enforced via Pydantic `Field(max_length=...)` at API boundary AND truncation before LLM injection: `MAX_USER_CONTEXT_CHARS=2000`, `MAX_STYLE_RULES_CHARS=1500`, `MAX_RESEARCH_JSON_CHARS=6000`, `MAX_PLAYBOOK_CHARS=1500`
- **Rate limiting** — `slowapi` on `/campaigns/plan` (10/min), `/research` (10/min), `/generate` (5/min); keyed by API key hash or client IP
- **Daily generation cap** — `MAX_DAILY_GENERATIONS=50` per profile at `/generate`
- **Style rule cap** — `MAX_STYLE_RULES_PER_PROFILE=25` enforced at `/rules` POST and feedback_service auto-extraction
- **Security headers** — `SecurityHeadersMiddleware`: HSTS, CSP, X-Content-Type-Options (nosniff), X-Frame-Options (DENY), Referrer-Policy, Permissions-Policy
- **Error sanitization** — SSE error events send generic messages only; stack traces logged server-side, never sent to client
- **Frontend XSS** — all `innerHTML` assignments wrapped in `DOMPurify.sanitize()`; API key stored in `localStorage`
- **No native dialogs** — use `showConfirmModal(message, onConfirm)` in console.js instead of `window.confirm()`
- **API keys** — ANTHROPIC_API_KEY, DEEPSEEK_API_KEY, EXA_API_KEY, ZAI_API_KEY, DATAFORSEO_LOGIN, DATAFORSEO_PASSWORD, ADMIN_SECRET (`.env` only, never logged)

## Architecture Rules
- **Async mandatory** — all HTTP clients and generation calls must use async/await
- **Pydantic-first** — validate at every agent boundary via `app/schemas.py`
- **Multi-tenant** — all DB queries must filter by `profile_name` (including workspaces); cache uses composite key `(keyword, profile_name, niche)`
- **LLM routing** — GLM-5 via `call_glm5_with_retry()` (`glm-5` for research/verification); DeepSeek via httpx (`deepseek-chat` for briefing/feedback/intel, `deepseek-reasoner` for cartographer); Claude Sonnet 4.5 (`claude-sonnet-4-5-20250929`) for writer via `anthropic` SDK (extended thinking)
- **SSL retry** — post-generation `db.commit()` in `event_generator()` uses `nonlocal db` + `OperationalError` catch to get fresh `SessionLocal()` if Neon drops connection
- **Centralized config** — all operational constants live in `app/settings.py`; import from there, never hardcode
- **Niche normalization** — always use `normalize_niche()` helper: `strip().lower().replace(" ", "-")`
- **URL normalization** — `_normalize_url()` in `main.py` strips www, query params, fragments, trailing slashes; always use for `source_content_map` keys
- **Migration versioning** — `migration_history` table tracks applied migrations; new migrations go in `database.py` and register in `record_all_migrations()`
- **FK constraints** — `posts.research_run_id` → `research_runs.id` (SET NULL), `writer_runs.post_id` → `posts.id` (CASCADE); enforced at DB level

## Pipeline Rules
- **No fake assets / no fabricated data** — writer prompt bans invented templates, tools, stats; must use only verified citation map facts
- **source_content_map completeness** — must include both Phase 1 competitor articles AND Phase 1.5 Exa Research API facts, keyed by normalized URL
- **Claim verification gate** — post-writer claim cross-referencing via `claim_verification_agent.py`; fabricated citations = zero-tolerance; skipped when no FactCitations exist (Phase 1.5 failure → graceful bypass)
- **Attribution mismatch detection** — use `detect_attribution_mismatches()` from `source_verification_service.py`; never duplicate `_ORG_PATTERN` / `KNOWN_RESEARCH_ORGS`
- **Banned word sanitizer** — deterministic post-LLM regex in `writer_service._sanitize_banned_words()`; never rely solely on prompt instructions
- **Phase 1.5 graceful degradation** — Exa Research API failure is non-fatal; pipeline continues with Phase 1 data only
- **Exa metadata preservation** — all Exa search functions must preserve `publishedDate` + `score` via `url_metadata_map` pattern
- **5xx retry** — GLM-5 and Exa clients retry on 429/500/502/503 with exponential backoff (1s→2s→4s); MCP calls use `mcp_call_with_retry()` wrapper
- **Frontend state** — clear `lastGeneratedMarkdown`, `currentPostId`, `currentQuestions` before each generation; `currentAbortController` cancels in-flight SSE

## Architecture
Only if told to read. Full pipeline (7 phases), agent logic, scoring algorithms, intelligence loops, and workspace system: `docs/architecture.md`
