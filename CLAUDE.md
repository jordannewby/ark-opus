# Ares Engine

## NEVER
- Never rewrite entire files for small logic changes — use targeted edits
- Never commit `.env`, `venv/`, `blog.db`, `__pycache__/`
- Never swap the database to SQLite or any non-Neon provider
- Never duplicate source code into `.md` memory files
- Never introduce paid dependencies without admin approval
- Never remove `pool_pre_ping` or keepalive args from `database.py`

**Stack**: FastAPI + Neon PostgreSQL + GLM-5 Thinking, DeepSeek V3 + Claude Sonnet 4.5 + Exa.ai + DataForSEO MCP
**Budget**: $10-$20 max — prefer lightweight, serverless

## Key Paths
- `app/main.py` — FastAPI endpoints + SSE `event_generator()` pipeline spine; `_normalize_url()` helper for consistent URL keying
- `app/services/` — Agents: briefing, research, exa_research, source_verification, claim_verification, psychology, writer, readability, feedback, research_intel, writer_intel, cartographer
- `app/glm_client.py` — GLM-5 API client (semaphore concurrency + 5xx retry)
- `app/exa_client.py` — Exa API client (rate limiting + 5xx retry)
- `app/services/exa_research_service.py` — Phase 1.5 Exa Research API fact discovery + citation laundering detection
- `app/models.py` — ORM: Post, UserStyleRule, UserStyleRuleArchive, ResearchCache, Workspace, ResearchRun, NichePlaybook, WriterRun, WriterPlaybook, ContentCampaign, VerifiedSource, FactCitation, ProfileSettings, DomainCredibilityCache, ApiKey
- `app/schemas.py` — Pydantic request/response schemas
- `app/domain_tiers.py` — 4-tier domain credibility lists
- `app/auth.py` — API key authentication (`verify_api_key` FastAPI dependency, SHA256 hashing)
- `app/security.py` — Prompt injection sanitization (`sanitize_prompt_input`, `sanitize_external_content`)
- `app/services/prompts/` — LLM prompt templates (writer.md, persuasion.md)
- `app/database.py` — Neon PostgreSQL (SQLAlchemy, pool_pre_ping, keepalives, FK constraints, migration versioning)
- `static/` — Frontend (ares_console.html, js/console.js)

## Rules
- **Async mandatory** — all HTTP clients and generation calls must use async/await
- **Pydantic-first** — validate at every agent boundary via `app/schemas.py`
- **Multi-tenant** — all DB queries must filter by `profile_name`; cache uses composite key `(keyword, profile_name, niche)`
- **LLM routing** — GLM-5 via `call_glm5_with_retry()` from `glm_client.py` (`glm-5` for research/verification); DeepSeek via httpx (`deepseek-chat` for briefing/feedback/intel, `deepseek-reasoner` for cartographer); Anthropic Claude Sonnet 4.5 (`claude-sonnet-4-5-20250929`) for writer via `langchain-anthropic` + native `anthropic` SDK (extended thinking)
- **SSL retry** — post-generation `db.commit()` in `event_generator()` uses `nonlocal db` + `OperationalError` catch to get fresh `SessionLocal()` if Neon drops connection
- **No fake assets / no fabricated data** — writer prompt bans invented templates, tools, stats; must use only verified citation map facts
- **Prompt files read-only** — never modify `app/services/prompts/*.md` without explicit approval
- **Niche normalization** — always use `normalize_niche()` helper: `strip().lower().replace(" ", "-")`
- **Frontend state** — clear `lastGeneratedMarkdown`, `currentPostId`, `currentQuestions` before each generation; `currentAbortController` cancels in-flight SSE before new generation
- **No native dialogs** — use `showConfirmModal(message, onConfirm)` in console.js instead of `window.confirm()`; confirm modal HTML in ares_console.html
- **Exa metadata preservation** — all Exa search functions must preserve `publishedDate` + `score` via `url_metadata_map` pattern, merged into extract results for Phase 1.5 scoring
- **Source credibility threshold** — 45.0/100 minimum (53% pass rate). 7-factor base scoring (85pts max) + rescue bonus (15pts max) for borderline sources
- **Keyword relevance fallback** — `_keyword_relevance_score()` in research_service.py tokenizes slug keywords and checks source relevance; if <3 relevant sources after niche-filtered search, unfiltered Exa fallback + broad backfill fire automatically
- **Claim verification gate** — post-writer claim cross-referencing via `claim_verification_agent.py`; fabricated citations (URL not in fact map) = zero-tolerance; ungrounded citations always enforced via `max(2, int(total_claims * MAX_UNGROUNDED_RATIO))` threshold; skipped entirely when no FactCitations exist (Phase 1.5 failure → graceful bypass)
- **Attribution mismatch detection** — use `detect_attribution_mismatches()` from `source_verification_service.py`; single helper reusing module-level `_ORG_PATTERN` regex and `KNOWN_RESEARCH_ORGS` — never duplicate this logic
- **Banned word sanitizer** — deterministic post-LLM regex in `writer_service._sanitize_banned_words()` catches inflected forms (leveraging, optimized, landscapes) after Claude generates; never rely solely on prompt instructions
- **URL normalization** — `_normalize_url()` in `main.py` strips www, query params, fragments, trailing slashes; always use for `source_content_map` keys
- **source_content_map completeness** — must include both Phase 1 competitor articles AND Phase 1.5 Exa Research API facts, keyed by normalized URL; Phase 4 claim cross-referencing depends on this
- **Phase 1.5 graceful degradation** — Exa Research API failure is non-fatal; pipeline yields `phase1_5_warning` event and continues with Phase 1 data only
- **Psychology agent timeout** — `asyncio.wait_for(..., timeout=90)` wrapper on DeepSeek-V3 blueprint generation
- **5xx retry** — GLM-5 and Exa clients retry on 429, 500, 502, 503 with exponential backoff (1s→2s→4s)
- **Input length bounds** — user-controlled inputs truncated before LLM prompt injection: `MAX_USER_CONTEXT_CHARS=2000`, `MAX_STYLE_RULES_CHARS=1500`, `MAX_RESEARCH_JSON_CHARS=6000`, `MAX_PLAYBOOK_CHARS=1500` (all in `settings.py`)
- **Exa Research API confidence** — tier-aware scoring (Tier 1-2: 0.90, Tier 3-4: 0.75, unknown: 0.60) + citation laundering detection (suspect: 0.40); replaces hardcoded 0.85
- **MCP retry** — all DataForSEO MCP `session.call_tool()` calls must use `mcp_call_with_retry()` wrapper from `research_service.py` (exponential backoff: 1s→2s→4s, max 3 retries on 429/rate-limit)
- **Centralized config** — operational constants (timeouts, thresholds, tuning params, input bounds) live in `app/settings.py`; add new values there and import in services
- **Structured logging** — all service files use `logger = logging.getLogger(__name__)`; never use bare `print()` for debug output
- **FK constraints** — `posts.research_run_id` → `research_runs.id` (SET NULL), `writer_runs.post_id` → `posts.id` (CASCADE); enforced at DB level
- **Migration versioning** — `migration_history` table tracks applied migrations; `migrate_version_tracking()` in `database.py`
- **Editor readability alignment** — `writer_agent_graph.py` editor node uses `verify_readability()` from readability service (not a separate ARI threshold)
- **API key auth** — all endpoints (except `/health`, `/`) require `X-API-Key` header validated by `verify_api_key()` from `app/auth.py`; SHA256 hashed, matched against `api_keys` table
- **Prompt injection defense** — all user-controlled inputs sanitized via `sanitize_prompt_input()` from `app/security.py` before LLM prompt injection; XML boundary tags, HTML comment stripping, control char removal
- **Rate limiting** — `slowapi` on `/campaigns/plan` (10/min), `/research` (10/min), `/generate` (5/min); keyed by API key hash or client IP
- **Daily generation cap** — `MAX_DAILY_GENERATIONS=50` per profile enforced at `/generate` endpoint
- **Admin secret** — `ADMIN_SECRET` env var for `/admin/api-keys` endpoint; validated with `secrets.compare_digest()` (timing-safe)
- **Error sanitization** — SSE error events send generic messages only; stack traces logged server-side, never sent to client
- **Security headers** — `SecurityHeadersMiddleware` adds CSP, X-Content-Type-Options, X-Frame-Options to all responses
- **API keys** — ANTHROPIC_API_KEY, DEEPSEEK_API_KEY, EXA_API_KEY, ZAI_API_KEY, DATAFORSEO_LOGIN, DATAFORSEO_PASSWORD, ADMIN_SECRET (`.env` only)

## Architecture
Only if told to read. Full pipeline (7 phases), agent logic, scoring algorithms, intelligence loops, and workspace system: `docs/architecture.md`
