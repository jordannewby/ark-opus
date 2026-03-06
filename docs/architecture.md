# Ares Engine — Architecture Reference

Load this file when working on pipeline logic, agent behavior, or the workspace system: `@docs/architecture.md`

---

## Pipeline Overview (6 Phases)

### Phase -1 — CartographerAgent (`app/services/cartographer_service.py`)
- **Model**: `deepseek-reasoner` (DeepSeek-R1)
- **Trigger**: `/campaigns/plan` endpoint via the Cartographer UI
- **Logic**: Fetches top 100 keyword ideas from DataForSEO, sends compressed schema to DeepSeek-R1 to map Hub-and-Spoke structure, and saves result strictly as JSON to database.
- **Output**: Persists a `ContentCampaign` containing 1 Pillar and up to 10 Spoke keywords, output via `/campaigns` to the UI.

### Phase 0 — BriefingAgent (`app/services/briefing_agent.py`)
- **Model**: `gemini-2.5-flash`
- **Trigger**: `/clarify` endpoint before the main `/generate` call
- **Logic**: Evaluates the user's Keyword + free-form Niche input, asks exactly 3 targeted clarifying questions via a custom frontend modal
- **Output**: User answers injected into Phase 1 as additional context

### Phase 1 — ResearchAgent (`app/services/research_service.py`)
- **Models**: `deepseek-reasoner` (DeepSeek-R1) for agentic tool decisions
- **Tools**: DataForSEO MCP server + Native Exa.ai tools (`exa_scout_search`, `exa_extract_full_text`)
- **Agentic Logic**: DeepSeek-R1 runs in an **iterative loop** (max 5 iterations). It autonomously orchestrates both MCP tools (Keyword Ideas, Live SERP, etc.) and native Exa tools to scout and extract full article bodies (truncated to 20,000 chars for context safety).
- **Niche Playbook Injection**: Before the agentic loop, `_get_niche_playbook()` retrieves distilled or heuristic intelligence for the current `(profile_name, niche)` and injects it into R1's prompt (~200 extra tokens). Omitted entirely on cold start.
- **Fallback / Safety**: Circuit breaker forces output at 5 iterations. Hallucinated tools return a simulated error to allow R1 to self-correct.
- **Opportunity Score Algorithm**: Filters semantic entities by Volume, CPC, KD — discards any keyword with KD > 65
- **Output**: Stripped "Information Gap" — what Page 1 competitors missed
- **Telemetry Capture**: After each run, `_capture_run_telemetry()` stores tool sequence, KD stats, Exa queries, entity clusters, and info gap into `ResearchRun`. Triggers distillation check.
- **Noise filter**: `_strip_webhook_noise` removes large DataForSEO webhook payloads from MCP schemas before passing to R1

### Phase 2 — PsychologyAgent (`app/services/psychology_agent.py`)
- **Model**: `deepseek-chat` (DeepSeek-V3)
- **Prompt**: `app/services/prompts/persuasion.md` — PAS (Problem-Agitation-Solution) framework
- **Output**: Structured JSON psychological blueprint with Identity Hooks, emotional triggers

### Phase 3 — WriterService (`app/services/writer_service.py`)
- **Model**: `claude-3-5-sonnet-20241022` via native `anthropic` SDK
- **Logic**: Operates in an **iterative SEO loop** (max 3 attempts). Each draft is validated by `verify_seo_score`. If validation fails, feedback is injected into the next attempt's prompt.
- **SEO Validation**: Static method checks for word count (min 1500), H2 count (min 5), list/table density (min 3 blocks), and Information Gain Density (min 2.0). 
- **Prompt**: `app/services/prompts/writer.md` — Anti-AI-slop rules (bans: "delve", "tapestry", "crucial", corporate fluff) + dynamic SEO length directive (2,000-2,500 words).
- **Input**: Psychology blueprint + UserStyleRules from DB (scoped to active workspace)
- **Output**: 2,500+ word Markdown article streamed in real-time. Yields `debug` events for iteration tracking and `content` events for prose. 

### Phase 6 — FeedbackAgent (`app/services/feedback_service.py`)
- **Model**: `gemini-2.5-flash`
- **Trigger**: `/posts/{post_id}/approve` endpoint when user submits human-edited Markdown
- **Logic**: Semantically diffs `original_ai_content` vs `human_edited_content`, extracts `UserStyleRule` entities
- **Output**: Permanent style rules saved to Neon PostgreSQL, injected into Phase 3 next run

### Research Intelligence Loop (`app/services/research_intel_service.py`)

A closed-loop system that makes the ResearchAgent self-improving across runs. Four phases:

1. **Capture** ($0/run) — `_capture_run_telemetry()` in `research_service.py` extracts structured telemetry (tool sequence, KD stats, Exa queries, entity clusters) from data already in memory. Stored as `ResearchRun` rows.
2. **Recall** (~200 tokens) — `_get_niche_playbook()` retrieves the distilled `NichePlaybook` for `(profile_name, niche)` and injects it into R1's agentic prompt. Falls back to heuristic aggregation of last 5 raw runs. Returns `None` on true cold start.
3. **Reinforce** ($0 on `/approve`) — `ResearchIntelService.score_research_run()` computes `SequenceMatcher` edit-distance ratio (0.0–1.0) between `original_ai_content` and human-edited content. Persisted as `ResearchRun.quality_score`.
4. **Distill** (~$0.001 per 10 runs) — `maybe_distill()` triggers when ≥10 undistilled runs accumulate for a niche. Uses `_compute_heuristic_playbook()` (zero LLM cost, Counter-based stats) if <5 quality-scored runs, otherwise `_distill_with_flash()` via `gemini-2.5-flash`. Result upserted into `NichePlaybook`.

**Key behaviors:**
- Niche normalization: `strip().lower().replace(" ", "-")` (e.g., "Health Blog" → "health-blog")
- Stale playbook caveat appended when `updated_at` > 30 days old
- 5% random prune of distilled `ResearchRun` rows >90 days old to manage DB growth
- `is_distilled` flag marks consumed runs so they aren't re-distilled

---

## SSE Streaming Architecture

- `/generate` endpoint → `event_generator()` async generator → `StreamingResponse` (Uses Pydantic `model_dump(mode='json')` for safe datetime serialization)
- Frontend `static/js/console.js` consumes SSE events and renders them in the Cyber-Glassmorphism console.
- **Real-time Content**: Phase 3 (Writer) streams `content` events which are appended directly to the UI editor for a "live typing" effect. Supports `RETRY_CLEAR` data to reset the editor during iterative SEO loops.
- **Debug Propagation**: Forwarding `debug` events from all backend agents (Phase 1 tool decisions, Phase 3 iteration logs) to the Cyber-Glass terminal for full visibility.
- Each phase streams progress events (tool decisions, intermediate results) in real time.
- DataForSEO MCP tool names are streamed directly to the UI as R1 selects them

---

## Multi-Tenant Workspace System

Workspaces partition Neon PostgreSQL by `profile_name`, isolating `UserStyleRule` memory per client/project.

- **UI**: `<select id="profile-select">` dropdown + magenta `#add-workspace-btn` in top command bar
- **Modal**: `#workspace-modal-overlay` — text input → slugify (e.g., "Health Blog" → `health_blog`) → inject `<option>` → `dispatchEvent(new Event('change'))` → reloads Neural Memory Bank
- **Safety invariant**: `executeGeneration`, `loadRules`, `deleteRule` functions are NEVER modified by workspace logic
- **AI Brain panel**: `#brain-modal` slide-out reads/writes rules scoped to active `profile-select` value
- **Cartographer panel**: `#cartographer-modal` slide-out provides an interface to plan Content Campaigns mappings.

---

## Database Schema (Neon PostgreSQL)

Tables managed via SQLAlchemy ORM in `app/models.py`:
- `Post` — generated articles (`title`, `content`, `original_ai_content`, `human_edited_content`, `profile_name`, `research_run_id`, `updated_at`)
- `UserStyleRule` — style memory rules scoped by `profile_name`
- `ResearchCache` — cached keyword research to reduce API calls
- `Workspace` — persistent workspace definitions (`name`, `slug`, unique)
- `ContentCampaign` — stores hub-and-spoke mappings (`seed_topic`, `pillar_keyword`, `spoke_keywords_json`, `profile_name`)
- `ResearchRun` — per-run telemetry (tool sequence, KD stats, Exa queries, entity clusters, `quality_score`, `is_distilled`). Linked to `Post` via bidirectional `post_id`/`research_run_id`.
- `NichePlaybook` — distilled niche-level intelligence. Composite unique constraint `(profile_name, niche)` for multi-tenant isolation. Versioned with `runs_distilled` counter.

Connection configured in `app/database.py` — Neon PostgreSQL with `pool_pre_ping`, `pool_recycle=300`, TCP keepalives.

---

## Anti-AI-Slop Enforcement

- Banned words list in `app/services/prompts/writer.md` (delve, tapestry, crucial, foster, etc.)
- PAS framework enforced via `app/services/prompts/persuasion.md`
- Identity Hooks target reader psychology via specific audience archetypes
- UserStyleRules from FeedbackAgent mathematically converge on the user's exact writing style over runs

---

## NEVER
- Never rewrite entire files for small logic changes
- Never remove `pool_pre_ping` or keepalive args from `database.py`
- Never modify `app/services/prompts/*.md` without explicit approval
- Never bypass `profile_name` filtering — all style rules are workspace-scoped
- Never duplicate source code into `.md` memory files
