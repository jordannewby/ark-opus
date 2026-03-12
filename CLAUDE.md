# Ares Engine

**Stack**: FastAPI + Neon PostgreSQL + DeepSeek-R1/V3 + Anthropic Claude 3.5 Sonnet + Gemini 2.5 Pro/Flash + Exa.ai (Native Tools) + DataForSEO MCP
**Budget**: $10 max — prefer lightweight, serverless

## Key Paths
- `app/main.py` — FastAPI app, `/generate` SSE endpoint, `/posts/{id}/approve`, `/clarify`, `/rules`, `/workspaces`, `/campaigns/plan`, `/campaigns`
- `app/services/` — All agents: briefing_agent, research_service, psychology_agent, writer_service, readability_service, feedback_service, research_intel_service, cartographer_service
- `app/models.py` — ORM models: `Post`, `UserStyleRule`, `ResearchCache`, `Workspace`, `ResearchRun`, `NichePlaybook`, `ContentCampaign`
- `app/schemas.py` — Pydantic schemas (includes `WorkspaceCreate`, `WorkspaceResponse`, `StyleRuleCreate`, `ResearchRunCapture`, `NichePlaybookResponse`, `CampaignResponse`)
- `app/services/prompts/` — LLM prompt templates (writer.md, persuasion.md)
- `static/` — Frontend (ares_console.html, js/console.js, js/api.js)
- `app/database.py` — Neon PostgreSQL connection (SQLAlchemy, pool_pre_ping, keepalives)
- `app/settings.py` — Environment + API key loading

## Rules
- **Async mandatory** — all HTTP clients + generation calls must be async
- **Pydantic-first** — validate at every agent boundary via `app/schemas.py`
- **Zero Hallucination** — enforce strict tool schemas in ResearchAgent; hallucinated tools trigger an error block to force R1 self-correction
- **Iterative Tooling** — ResearchAgent runs an iterative loop (max 5) allowing R1 to mix DataForSEO MCP tools with native Exa tools (`exa_scout_search`, `exa_extract_full_text`). Agentic prompt uses a **3-step sequencing pattern**: Step 1 (mandatory tools with literal JSON example pre-filled with keyword), Step 2 (strategic tools like Exa/backlinks/on_page), Step 3 (final output only after Steps 1-2). A `CRITICAL` preamble enforces tool-calling before any final analysis.
- **Expanded Research Output** — R1's final output is an expanded dict with keys: `information_gap`, `unique_angles`, `competitor_weaknesses`, `data_points`, `practitioner_insights`. Legacy string format still supported via fallback. Result dict unpacks these into top-level keys. On-page metrics and backlink authority are extracted from real MCP tool results (no hardcoded placeholders). String responses are auto-parsed via `json.loads` in case R1 returns stringified JSON.
- **Multi-tenant** — all DB queries must filter by `profile_name` (workspace scope)
- **Cache Isolation** — ResearchCache uses composite unique key `(keyword, profile_name, niche)` to prevent cross-workspace/niche pollution. All cache lookups require exact match on all three fields.
- **Playbook Boundaries** — Niche playbooks are injected within `<niche_playbook>` XML tags with explicit instruction to DeepSeek-R1 to use them ONLY for strategic patterns, NOT past topic research.
- **Frontend State Management** — Global variables (`lastGeneratedMarkdown`, `currentPostId`, `currentQuestions`) are cleared before each generation to prevent UI artifacts from previous runs.
- **Research Intelligence** — ResearchAgent self-improves via a 4-phase loop: Capture ($0) → Recall (~200 tokens) → Reinforce ($0 on /approve) → Distill (~$0.001/10 runs via Gemini Flash). Niche playbooks are scoped by `(profile_name, niche)`.
- **Readability Enforcement** — WriterService enforces 7th-8th grade readability (target ≤7.5) via dual-gate validation: SEO structure first, then composite readability scoring (ARI primary, Flesch-Kincaid cross-check with +1.5 buffer, Coleman-Liau advisory only). Max 5 iterative rewrites. Zero API cost. READABILITY_DIRECTIVE injected dynamically (never modifies writer.md). Includes **pre-flight simplicity primer** before main directive and **7th-grade template sentences** for pattern-matching. Directive uses **layer-cake scanning format** optimized for how busy readers scan (headings → first sentences → bold text). Requires benefit-driven H2s every 150-200 words, key takeaway as first sentence of each section, and bold anchor phrase per section. Target word count: 1,500-1,800 words. Bans AI-slop words directly in the directive. Includes a concrete **word-swap reference table** (implement→set up, utilize→use, demonstrate→show, etc.) so Claude has explicit short-word alternatives. Enforces 8-12 words/sentence (MANDATORY for 80% of sentences, never exceed 15 words). **Complex sentence gate**: ≤20% of sentences can exceed 15 words. **Broad keyword masking**: scoring masks semantic keywords + blueprint entities + 33 common niche terms (security, business, software, etc.) that inflate ARI but have no shorter synonym. **Readability tracking**: scores (ARI, FK, CLI, avg sentence length) persisted to Post.readability_score JSON column for analytics. SEO failure feedback reports all 6 validation conditions with specific counts (word count, H1, H2, list/table blocks, info gain density, banned words).
- **No Fake Assets & No Fabricated Data** — WriterService prompt includes hard constraints (constraints 5 and 6) banning references to non-existent templates, tools, downloads, checklists, or frameworks, and strictly forbidding the fabrication of statistics, percentages, or dollar amounts. The model must give actionable steps and use only data from the research brief.
- **SSL Retry on Commit** — Post-generation `db.commit()` in `event_generator()` is wrapped in `OperationalError` retry that gets a fresh `SessionLocal()` if Neon drops the SSL connection during long writer loops. Uses `nonlocal db` to reassign the outer scope's session. Only applied to post-generation commits, not every commit in the file.
- **API keys** — ANTHROPIC_API_KEY, GEMINI_API_KEY, DEEPSEEK_API_KEY, EXA_API_KEY, DATAFORSEO_LOGIN, DATAFORSEO_PASSWORD (in .env only)

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
