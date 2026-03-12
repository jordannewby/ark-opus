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
- **Agentic Logic**: DeepSeek-R1 runs in an **iterative loop** (max 5 iterations). It autonomously orchestrates both MCP tools (Keyword Ideas, Live SERP, etc.) and native Exa tools to scout and extract full article bodies (truncated to 20,000 chars for context safety). The agentic prompt uses a **3-step sequencing pattern** to prevent R1 from skipping tools: Step 1 provides a literal JSON example of mandatory tool calls (keyword_ideas + SERP) pre-filled with the target keyword; Step 2 lists strategic tools (Exa scout/extract, backlinks, on_page, related keywords); Step 3 defines the final output format — placed last so R1 doesn't fill it in prematurely. A `CRITICAL` preamble enforces tool-calling before any final analysis. Debug logging (`[DEBUG] R1 raw response`) prints the first 500 chars of each R1 response to diagnose tool-skipping.
- **Niche Playbook Injection**: Before the agentic loop, `_get_niche_playbook()` retrieves distilled or heuristic intelligence for the current `(profile_name, niche)` and injects it into R1's prompt (~200 extra tokens) wrapped in `<niche_playbook>` XML tags. A **CRITICAL INSTRUCTION** explicitly directs R1 to use the playbook ONLY for strategic patterns (tool sequence, KD thresholds, audience insights) and NOT to research past topics mentioned within. Omitted entirely on cold start.
- **Fallback / Safety**: Circuit breaker forces output at 5 iterations. Hallucinated tools return a simulated error to allow R1 to self-correct.
- **Opportunity Score Algorithm**: Filters semantic entities by Volume, CPC, KD — discards any keyword with KD > 65
- **Expanded Output**: R1 returns an expanded dict with keys: `information_gap` (string), `unique_angles` (list), `competitor_weaknesses` (list), `data_points` (list), `practitioner_insights` (list). Legacy string format still supported via fallback. String responses auto-parsed via `json.loads` in case R1 returns stringified JSON. On-page metrics and backlink authority extracted from real MCP tool results (no hardcoded placeholders). All fields unpacked into the top-level result dict for downstream consumption by PsychologyAgent and WriterService.
- **Telemetry Capture**: After each run, `_capture_run_telemetry()` stores tool sequence, KD stats, Exa queries, entity clusters, and info gap into `ResearchRun`. Triggers distillation check.
- **Noise filter**: `_strip_webhook_noise` removes large DataForSEO webhook payloads from MCP schemas before passing to R1
- **Cache Strategy**: ResearchCache enforces strict multi-tenant isolation via composite unique constraint `(keyword, profile_name, niche)`. Cache lookups require exact match on all three fields. Existing entries are checked for expiration (default 24h TTL) and deleted if stale. Migration adds `profile_name` and `niche` columns to legacy cache entries with `'default'` values.

### Phase 2 — PsychologyAgent (`app/services/psychology_agent.py`)
- **Model**: `deepseek-chat` (DeepSeek-V3)
- **Prompt**: `app/services/prompts/persuasion.md` — PAS (Problem-Agitation-Solution) framework
- **Output**: Structured JSON psychological blueprint with Identity Hooks, emotional triggers

### Phase 3 — WriterService (`app/services/writer_service.py`)
- **Model**: `claude-3-5-sonnet-20241022` via native `anthropic` SDK
- **Logic**: Operates in an **iterative dual-gate loop** (max 5 attempts). Each draft is validated by two sequential gates:
  1. **Gate 1 (SEO)**: `verify_seo_score` checks word count (min 1500), H2 count (min 5), list/table density (min 3 blocks), and Information Gain Density (min 2.0)
  2. **Gate 2 (Readability)**: `verify_readability` enforces 7th-10th grade reading level (target ≤10.0, accepts 7.5-10 range) using composite scoring: ARI (primary gate), Flesch-Kincaid (cross-check, target +1.5 buffer), Coleman-Liau (advisory only — over-penalizes technical vocabulary). Also enforces avg sentence length ≤12 words, **80% distribution gate** (requires ≥80% of sentences in 8-12 word range, not just average), and complex sentence gate (≤15% of sentences can exceed 15 words, reduced from 20%). Broad keyword masking during scoring: semantic keywords + blueprint entities + 58+ common niche terms including business jargon (security, business, software, streamline, leverage, optimize, enhance, framework, methodology, ecosystem, paradigm, establish, execute, implement, facilitate, comprehensive, infrastructure, capability, operational, strategic, scalable) that inflate ARI but have no shorter synonym. Readability scores (ARI, FK, CLI, avg sentence length) persisted to Post.readability_score JSON column for analytics.
- **Readability Service** (`app/services/readability_service.py`): Zero-cost pure Python implementation. ARI is the primary gatekeeper (character-based, deterministic). FK cross-check uses +1.5 buffer to absorb syllable-counting noise. CLI is advisory only — reported in debug but does not block publishing (it over-penalizes technical vocabulary that IS the SEO strategy). `READABILITY_DIRECTIVE` injected dynamically into prompt (never modifies `writer.md`). Includes **pre-flight simplicity primer** before main directive and **7th-grade template sentences** for pattern-matching. Uses **layer-cake scanning format** — optimized for how busy readers actually read (scan headings, first sentences, bold text). Requires benefit-driven H2 headings every 150-200 words, key takeaway as first sentence of each section, bold anchor phrase per section. Includes a concrete **word-swap reference table** (implement→set up, utilize→use, demonstrate→show, streamline→simplify, leverage→using, etc.) that is **repeated in feedback on every iteration** giving Claude explicit short-word alternatives. **Distribution feedback** shows exact breakdown ("Only 62% in 8-12 range, need 80%") with actionable rebalancing steps. Per-sentence analysis identifies complex sentences. Typical convergence: 1-2 passes for SEO, 1-2 passes for readability (down from 5 failures).
- **Writer Intelligence Injection**: After UserStyleRules, fetches `WriterPlaybook` for `(profile_name, niche)` and injects learned readability patterns (~100 tokens). Includes niche-specific ARI baseline, target sentence length, effective sentence patterns (future LLM distillation), and preferred word swaps (future LLM distillation). Example: "This niche typically achieves ARI: 7.15 grade level. Target sentence length: 11.2 words. (Playbook version 1, based on 10 successful articles)". Omitted on cold start (first 10 articles in a niche).
- **Prompt**: `app/services/prompts/writer.md` — Anti-AI-slop rules (bans: "delve", "tapestry", "crucial", corporate fluff) + dynamic SEO length directive (1,500-1,800 words) + **pre-flight simplicity primer** (7th-grade readability checklist) + `READABILITY_DIRECTIVE` (layer-cake scanning: benefit-driven H2s every 150-200 words, first-sentence takeaways, bold text anchoring, H1 + ≥5 H2s + ≥3 list/table blocks; 7th-8th grade target ≤7.5, 8-12 words/sentence MANDATORY for 80% of sentences with 15-word hard ceiling, active voice, 7th-grade template sentences for pattern-matching, banned AI-slop words list + word-swap reference table embedded in directive). **No Fake Assets** constraint bans references to non-existent templates, tools, downloads, checklists, or frameworks — requires actionable steps instead. **No Fabricated Data** constraint bans inventing statistics, percentages, or study results not found in the research brief.
- **SEO Feedback**: On validation failure, reports all 6 conditions with specific counts: word count, H1 count, H2 count, list/table blocks, information gain density, and banned words found. Eliminates blind retry loops.
- **Input**: Psychology blueprint + UserStyleRules from DB (scoped to active workspace)
- **Output**: ~1,600 word Markdown article streamed in real-time. Yields `debug` events for iteration tracking (SEO pass/fail with specific failure reasons, Readability pass/fail with grade metrics) and `content` events for prose. Yields `RETRY_CLEAR` on validation failure to reset editor.

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

### Writer Intelligence Loop (`app/services/writer_intel_service.py`)

A parallel closed-loop system that makes the WriterService self-improving for readability across runs. Mirrors the Research Intelligence architecture. Four phases:

1. **Capture** ($0/run) — After each article generation, `WriterRun` telemetry is captured in `event_generator()` (app/main.py). Stores readability metrics (ARI, FK, CLI, avg_sentence_length) extracted from `Post.readability_score`. Data already in memory, zero API cost.
2. **Recall** (~100 tokens) — `produce_article()` in `writer_service.py` fetches `WriterPlaybook` for `(profile_name, niche)` and injects learned patterns into Claude's prompt. Includes niche ARI baseline, target sentence length, and structure templates. Omitted on cold start (first 10 articles).
3. **Reinforce** ($0 on `/approve`) — `WriterIntelService.score_writer_run()` computes readability efficiency on approval. Formula: `efficiency = (10.0 - ari_score) / 10.0`. Lower ARI = higher efficiency. Example: ARI 9.2 → efficiency 0.08. Persisted as `WriterRun.readability_efficiency`.
4. **Distill** (~$0.001 per 10 runs) — `maybe_distill()` triggers when ≥10 undistilled runs accumulate AND ≥5 have efficiency ≥0.20 (ARI ≤8.0, quality threshold unchanged). Uses `_compute_heuristic_playbook()` (zero LLM cost, statistical averages) for MVP. Result upserted into `WriterPlaybook` with fields: `avg_ari_baseline`, `avg_readability_efficiency`, `target_avg_sentence_length`, `structure_template` (H2 frequency, list blocks). Versioned with `runs_distilled` counter.

**Key behaviors:**
- Niche normalization: `strip().lower().replace(" ", "-")` (identical to Research Intelligence)
- Quality threshold: Only runs with `readability_efficiency ≥ 0.20` (ARI ≤8.0) included in distillation
- Playbooks inject adaptive prompts: "This niche typically achieves ARI: 7.15 grade level. Target sentence length: 11.2 words."
- `is_distilled` flag marks consumed runs to prevent re-distillation
- Future: LLM-based distillation via Gemini Flash to extract sentence patterns and word swaps from article content

**Complementary to UserStyleRule**:
- `UserStyleRule` (FeedbackAgent) learns *what humans prefer* (tone, voice, specificity)
- `WriterPlaybook` (WriterIntelService) learns *what achieves readability targets* (sentence patterns, word choices, structure)
- Both systems feed into WriterService prompts, optimizing for different goals

---

## SSE Streaming Architecture

- `/generate` endpoint → `event_generator()` async generator → `StreamingResponse` (Uses Pydantic `model_dump(mode='json')` for safe datetime serialization)
- Frontend `static/js/console.js` consumes SSE events and renders them in the Cyber-Glassmorphism console.
- **Real-time Content**: Phase 3 (Writer) streams `content` events which are appended directly to the UI editor for a "live typing" effect. Supports `RETRY_CLEAR` data to reset the editor during iterative SEO loops.
- **Debug Propagation**: Forwarding `debug` events from all backend agents (Phase 1 tool decisions, Phase 3 iteration logs) to the Cyber-Glass terminal for full visibility.
- Each phase streams progress events (tool decisions, intermediate results) in real time.
- DataForSEO MCP tool names are streamed directly to the UI as R1 selects them

---

## SSL Retry on Post-Generation Commit

The DB session (`db`) is checked out via FastAPI's `Depends(get_db)` before `event_generator()` starts. With up to 5 iterations of Claude API calls (15-30s each), total generation can run 2-3 minutes. Neon PostgreSQL drops idle SSL connections before that completes. `pool_pre_ping` only helps at checkout time, not for connections already held open.

**Fix** (in `app/main.py`, `event_generator()`):
- `nonlocal db` declared at top of generator so reassignment works across Python's closure scoping
- Both post-generation `db.commit()` calls wrapped in `try/except OperationalError` → rollback → close → `SessionLocal()` → re-add/merge → commit
- Only applied to the two commits after article generation (Post save + ResearchRun linking), not every commit in the file

---

## State Management & Bleed Prevention

Ares Engine implements multi-layered state isolation to prevent topic bleed across keyword generations:

### Backend Cache Isolation
- **ResearchCache Table**: Composite unique key `(keyword, profile_name, niche)` enforces strict workspace and niche scoping
- **Cache Lookup**: `_get_cached(keyword, profile_name, niche)` in `research_service.py` requires exact match on all three fields
- **Cache Save**: `_save_cache(keyword, profile_name, niche, result)` upserts with full composite key
- **Migration**: `migrate_research_cache()` in `app/database.py` adds `profile_name` and `niche` columns to existing cache entries with `'default'` values

### Playbook Topic Boundaries
- **XML Wrapper**: Niche playbooks injected within `<niche_playbook>` tags in R1 prompt
- **Critical Instruction**: Explicit direction to DeepSeek-R1: "Use playbook STRICTLY for tone, audience insights, and strategic style. DO NOT research past topics. Focus EXCLUSIVELY on current Target Keyword: '{keyword}'"
- **Location**: `_build_agentic_prompt()` method in `research_service.py`

### Frontend State Clearing
- **Global Variables**: `lastGeneratedMarkdown`, `currentPostId`, `currentQuestions` cleared at two points:
  1. Generate button click handler (line ~246 in `console.js`)
  2. `executeGeneration()` function start (line ~304 in `console.js`)
- **Editor Clear**: Article editor explicitly cleared on `phase3_start` SSE event (line ~364)
- **Dual Clear Strategy**: Ensures state is cleared whether user completes clarification modal or skips it

### Verification
Test multi-tenant cache isolation:
```bash
# 1. Workspace "blog-a", keyword "python tutorials" → Research A
# 2. Workspace "blog-b", keyword "python tutorials" → Research B (different)
# 3. Check DB: SELECT keyword, profile_name, niche FROM research_cache WHERE keyword = 'python tutorials'
# Expected: 2 distinct rows
```

Test playbook boundary enforcement:
```bash
# 1. Generate "react hooks" in niche "web-dev" (creates playbook)
# 2. Generate "vue composition" in same niche
# Expected: Research focuses ONLY on Vue, not React (check debug logs)
```

Test frontend state clearing:
```bash
# 1. Generate "Keyword A"
# 2. Browser console: verify lastGeneratedMarkdown contains article A
# 3. Click generate "Keyword B" (no refresh)
# 4. Browser console: verify all globals empty before new fetch
```

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
- `Post` — generated articles (`title`, `content`, `original_ai_content`, `human_edited_content`, `profile_name`, `niche`, `research_run_id`, `readability_score`, `updated_at`). `readability_score` is a JSON column storing ARI, FK, CLI, and avg sentence length for analytics. `niche` added for WriterRun scoping.
- `UserStyleRule` — style memory rules scoped by `profile_name`
- `ResearchCache` — cached keyword research to reduce API calls. Composite unique constraint `(keyword, profile_name, niche)` ensures multi-tenant isolation. Includes TTL expiration (default 24h). Migration applied via `migrate_research_cache()` in `app/database.py`.
- `Workspace` — persistent workspace definitions (`name`, `slug`, unique)
- `ContentCampaign` — stores hub-and-spoke mappings (`seed_topic`, `pillar_keyword`, `spoke_keywords_json`, `profile_name`)
- `ResearchRun` — per-run telemetry (tool sequence, KD stats, Exa queries, entity clusters, `quality_score`, `is_distilled`). Linked to `Post` via bidirectional `post_id`/`research_run_id`.
- `NichePlaybook` — distilled niche-level intelligence for research. Composite unique constraint `(profile_name, niche)` for multi-tenant isolation. Versioned with `runs_distilled` counter.
- `WriterRun` — per-article readability telemetry (`ari_score`, `flesch_kincaid_score`, `coleman_liau_score`, `avg_sentence_length`, `readability_efficiency`, `human_approved`, `approved_at`, `is_distilled`). Composite unique constraint `(profile_name, niche, post_id)`. Linked to `Post` via `post_id`.
- `WriterPlaybook` — distilled niche-level readability patterns. Composite unique constraint `(profile_name, niche)` for multi-tenant isolation. Stores JSON with `avg_ari_baseline`, `avg_readability_efficiency`, `target_avg_sentence_length`, `structure_template`, `effective_sentence_patterns` (future), `preferred_word_swaps` (future). Versioned with `runs_distilled` counter.

Connection configured in `app/database.py` — Neon PostgreSQL with `pool_pre_ping`, `pool_recycle=300`, TCP keepalives.

---

## Anti-AI-Slop Enforcement

- Banned words list in `app/services/prompts/writer.md` (delve, tapestry, crucial, foster, etc.)
- **7th-10th grade readability enforcement** via `readability_service.py` — ARI-primary scoring with FK cross-check (+1.5 buffer) and CLI advisory. Target ≤10.0, accepts 7.5-10 range. Broad keyword masking (semantic keywords + entities + 58+ niche terms including business jargon: streamline, leverage, optimize, enhance, framework, methodology, ecosystem, paradigm, etc.) prevents unavoidable subject-matter nouns from inflating scores. Enforces avg sentence length ≤12 words, **80% distribution gate** (requires ≥80% of sentences in 8-12 word range, not just average), complex sentence gate (≤15% can exceed 15 words, reduced from 20%), active voice, immediate technical term explanations. READABILITY_DIRECTIVE includes **pre-flight simplicity primer** and **7th-grade template sentences** for pattern-matching. Uses **layer-cake scanning format**: benefit-driven H2s every 150-200 words, first-sentence takeaways per section, bold anchor phrases, 1,500-1,800 word target. Embeds banned AI-slop words list + concrete word-swap reference table (implement→set up, utilize→use, streamline→simplify, leverage→using, etc.) directly in the directive and **repeated in feedback on every iteration**. **Distribution feedback** shows exact breakdown ("Only 62% in 8-12 range, need 80%") with actionable rebalancing steps. Enforces 8-12 words/sentence (MANDATORY for 80% of sentences, never exceed 15 words). Readability scores persisted to Post.readability_score JSON for analytics.
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
