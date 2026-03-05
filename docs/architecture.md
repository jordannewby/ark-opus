# Ares Engine — Architecture Reference

Load this file when working on pipeline logic, agent behavior, or the workspace system: `@docs/architecture.md`

---

## Pipeline Overview (5 Phases)

### Phase 0 — BriefingAgent (`app/services/briefing_agent.py`)
- **Model**: `gemini-2.5-flash`
- **Trigger**: `/clarify` endpoint before the main `/generate` call
- **Logic**: Evaluates the user's Keyword + free-form Niche input, asks exactly 3 targeted clarifying questions via a custom frontend modal
- **Output**: User answers injected into Phase 1 as additional context

### Phase 1 — ResearchAgent (`app/services/research_service.py`)
- **Models**: `deepseek-reasoner` (DeepSeek-R1) for agentic tool decisions
- **Data Sources**: DataForSEO MCP server + Exa.ai Neural Search via `asyncio.gather`
- **Agentic Logic**: DeepSeek-R1 independently evaluates Keyword Difficulty and selects from a 4-tool baseline (Keyword Ideas, Live SERP, Related Searches, On-Page Content Analysis)
- **Opportunity Score Algorithm**: Filters semantic entities by Volume, CPC, KD — discards any keyword with KD > 65
- **Output**: Stripped "Information Gap" — what Page 1 competitors missed
- **Noise filter**: `_strip_webhook_noise` removes large DataForSEO webhook payloads from MCP schemas before passing to R1

### Phase 2 — PsychologyAgent (`app/services/psychology_agent.py`)
- **Model**: `deepseek-chat` (DeepSeek-V3)
- **Prompt**: `app/services/prompts/persuasion.md` — PAS (Problem-Agitation-Solution) framework
- **Output**: Structured JSON psychological blueprint with Identity Hooks, emotional triggers

### Phase 3 — WriterService (`app/services/writer_service.py`)
- **Model**: `gemini-2.5-pro` via native `google-genai` SDK
- **Prompt**: `app/services/prompts/writer.md` — Anti-AI-slop rules (bans: "delve", "tapestry", "crucial", corporate fluff)
- **Input**: Psychology blueprint + UserStyleRules from DB (scoped to active workspace)
- **Output**: 2,000+ word Markdown article streamed via SSE

### Phase 6 — FeedbackAgent (`app/services/feedback_service.py`)
- **Model**: `gemini-2.5-flash`
- **Trigger**: `/posts/{post_id}/approve` endpoint when user submits human-edited Markdown
- **Logic**: Semantically diffs `original_ai_content` vs `human_edited_content`, extracts `UserStyleRule` entities
- **Output**: Permanent style rules saved to Neon PostgreSQL, injected into Phase 3 next run

---

## SSE Streaming Architecture

- `/generate` endpoint → `event_generator()` async generator → `StreamingResponse`
- Frontend `static/js/console.js` consumes SSE events and renders them in the Cyber-Glassmorphism console
- Each phase streams progress events (tool decisions, intermediate results) in real time
- DataForSEO MCP tool names are streamed directly to the UI as R1 selects them

---

## Multi-Tenant Workspace System

Workspaces partition Neon PostgreSQL by `profile_name`, isolating `UserStyleRule` memory per client/project.

- **UI**: `<select id="profile-select">` dropdown + magenta `#add-workspace-btn` in top command bar
- **Modal**: `#workspace-modal-overlay` — text input → slugify (e.g., "Health Blog" → `health_blog`) → inject `<option>` → `dispatchEvent(new Event('change'))` → reloads Neural Memory Bank
- **Safety invariant**: `executeGeneration`, `loadRules`, `deleteRule` functions are NEVER modified by workspace logic
- **AI Brain panel**: `#brain-modal` slide-out reads/writes rules scoped to active `profile-select` value

---

## Database Schema (Neon PostgreSQL)

Tables managed via SQLAlchemy ORM in `app/models.py`:
- `Post` — generated articles (`original_ai_content`, `human_edited_content`, `profile_name`)
- `UserStyleRule` — style memory rules scoped by `profile_name`
- `ResearchCache` — cached keyword research to reduce API calls

Connection configured in `app/database.py` — credentials loaded from `.env`.

---

## Anti-AI-Slop Enforcement

- Banned words list in `app/services/prompts/writer.md` (delve, tapestry, crucial, foster, etc.)
- PAS framework enforced via `app/services/prompts/persuasion.md`
- Identity Hooks target reader psychology via specific audience archetypes
- UserStyleRules from FeedbackAgent mathematically converge on the user's exact writing style over runs
