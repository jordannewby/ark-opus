# Ark Opus

A 7-phase AI content pipeline that researches, verifies, and writes long-form articles with automated citation checking. It orchestrates multiple LLMs (GLM-5, DeepSeek-V3, Claude Sonnet 4.5) and external APIs (Exa.ai, DataForSEO) to produce 1,600+ word Markdown articles where every factual claim is cross-referenced against verified sources before the article is saved.

---

## Table of Contents

1. [The Problem](#the-problem)
2. [What Ark Opus Does Differently](#what-ark-opus-does-differently)
3. [What This Is / What This Is NOT](#what-this-is--what-this-is-not)
4. [How It Compares](#how-it-compares)
5. [Pipeline Overview](#pipeline-overview)
6. [Quick Start](#quick-start)
7. [Environment Variables](#environment-variables)
8. [Tech Stack](#tech-stack)
9. [API Endpoints](#api-endpoints)
10. [Cost Breakdown](#cost-breakdown)
11. [Security](#security)
12. [Architecture Deep Dive](#architecture-deep-dive)
13. [License](#license)

---

## The Problem

Every major AI content tool generates text and leaves fact-checking to the user. Jasper, Copy.ai, and Writesonic produce fluent prose with no mechanism to verify whether the claims in that prose are real. Frase researches before writing but does not cross-reference claims after generation. Surfer SEO optimizes for keyword density and SERP signals but does not touch factual accuracy. MarketMuse maps topical authority but does not verify individual claims.

Citation fabrication is the default failure mode of LLMs used for content. They invent URLs that return 404. They attribute studies to organizations that never published them. They hallucinate statistics that sound plausible but have no source. This is not an edge case. It is the baseline behavior of every general-purpose content generation tool on the market today.

The result: editorial teams spend more time fact-checking AI output than they saved by using AI in the first place. Content agencies publish articles with fabricated citations that damage client credibility. The trust problem is not a model quality problem — it is an architecture problem. No amount of prompt engineering prevents a model from inventing a URL it has never seen.

Ark Opus solves this by making verification a structural requirement, not an optional step. Articles cannot be saved until claims pass a multi-gate verification pipeline. The system does not trust LLM output — it verifies it.

---

## What Ark Opus Does Differently

These are specific, technical capabilities implemented in this codebase. Each one is verifiable by reading the referenced source file.

**1. Post-Write Claim Cross-Referencing**
After Claude generates an article, every factual claim is extracted via regex and matched against the verified fact database using 3-tier URL matching (exact, normalized, domain-level) and text similarity scoring. Fabricated citations — URLs not in the verified source map — trigger an automatic rewrite. Zero tolerance, no exceptions.
`app/services/claim_verification_agent.py`

**2. 7-Factor Source Credibility Scoring**
Before any source enters the writer's citation pool, it is scored on a 0-100 scale across 7 factors: content integrity, content quality, domain tier + authority, content freshness, author attribution, topical relevance, and spam detection. Sources below the threshold (default 45.0) are rejected. A rescue bonus system (up to +15 points) recovers borderline sources that show strong SERP ranking or citation depth.
`app/services/source_verification_service.py`

**3. Citation Laundering Detection**
When an article claims "Gartner reports X" but the citation URL points to a blog that aggregated the data, the system detects the mismatch. It maintains a map of 70+ research organizations to their canonical domains and flags attribution-URL mismatches as zero-tolerance violations.
`app/services/source_verification_service.py` — `KNOWN_RESEARCH_ORGS`

**4. Self-Improving Intelligence Loops**
After 10+ articles in a niche, the system distills successful research patterns (tool sequences, entity clusters, keyword strategies) and readability patterns (ARI baselines, sentence lengths) into playbooks. These playbooks are injected into future generations to guide — not dictate — research and writing quality. Human edit feedback trains per-profile style rules that persist across sessions.
`app/services/research_intel_service.py`, `app/services/writer_intel_service.py`, `app/services/feedback_service.py`

---

## What This Is / What This Is NOT

| This IS | This is NOT |
|---------|-------------|
| A fact-verification-first content pipeline | A fast content spinner |
| 20-40 minutes per article (research + verification + writing) | A "generate in 30 seconds" tool |
| Multi-LLM orchestration (5 models across 7 phases) | A single-prompt wrapper around GPT/Claude |
| Self-hosted, API-key-based | A SaaS product with a login page |
| ~$0.15-0.30 per article in API costs | Free or unlimited |
| Best for: technical content, SEO, thought leadership | Best for: social media posts, ad copy, email blasts |
| Style learning requires 10+ articles to activate | Instant brand voice templates |
| Requires 5 separate API accounts (Anthropic, DeepSeek, ZhipuAI, Exa, DataForSEO) | A one-click setup |

---

## How It Compares

This table reflects publicly documented capabilities of each platform as of April 2026. Checkmarks indicate the feature exists as a core product capability, not a workaround.

| Feature | Ark Opus | Frase | Jasper | Surfer SEO | MarketMuse |
|---------|----------|-------|--------|------------|------------|
| Post-write citation verification | Yes | No | No | N/A | No |
| Source credibility scoring | 7-factor (0-100) | No | No | No | No |
| Citation laundering detection | Yes | No | No | No | No |
| Research before writing | Yes (agentic, multi-tool) | Yes (single-pass) | Limited | No | No |
| Multi-LLM orchestration | 5 models | 1 | 2+ | N/A | N/A |
| Self-improving intelligence loops | Yes (research + writer) | No | Brand voice only | No | No |
| Speed per article | 20-40 min | ~10 min | ~2 min | N/A | N/A |
| Real-time SEO optimization | Basic (word count, H2s, ARI) | Yes | Via Surfer add-on | Yes (advanced) | No |
| Topical authority mapping | No | No | No | No | Yes |
| Brand voice template library | No (learned from edits) | No | Yes (50+) | No | No |
| Cost per article | ~$0.15-0.30 | Subscription | Subscription | Subscription | Subscription |

**Where competitors are better:** Frase is faster. Jasper has superior brand voice templates and enterprise integrations. Surfer SEO provides deeper real-time SERP correlation analysis. MarketMuse excels at site-wide topical authority planning. All of them are easier to set up.

**Where Ark Opus is better:** No platform in this category performs automated post-write citation verification, source credibility scoring, or citation laundering detection. These are structurally absent from the competition, not just weaker implementations.

---

## Pipeline Overview

```
Keyword + Niche
       |
       v
[Phase -1] Cartographer ─── Hub-and-spoke keyword campaign planning (DeepSeek-R1)
       |                    Fetches 100-700 keywords from DataForSEO, clusters into
       |                    pillar + up to 10 spokes with intent classification
       v
[Phase  0] Briefing ─────── 3 clarifying questions before research (DeepSeek-V3)
       |                    Optional. Refines keyword intent and audience targeting
       v
[Phase  1] Research ─────── Agentic tool orchestration (GLM-5)
       |                    DataForSEO SERP/keywords + Exa.ai neural search
       |                    Max 5 reasoning loops, niche-filtered source discovery
       v
[Phase 1.5] Verification ── Source credibility scoring + fact extraction
       |                    7-factor scoring (0-100), AI content detection,
       |                    citation laundering detection, URL liveness validation
       |                    GATE: Fails if <3 credible sources verified
       v
[Phase  2] Psychology ───── Persuasion blueprint generation (DeepSeek-V3)
       |                    PAS framework, identity hooks, semantic entity mapping,
       |                    dynamic content length targets from competitor benchmarks
       v
[Phase  3] Writer ────────── Article generation + 3-gate validation (Claude Sonnet 4.5)
       |                    Gate 1: SEO (1,500+ words, 5+ H2s, 3+ list/table blocks)
       |                    Gate 2: Citations (claim cross-referencing, URL matching)
       |                    Gate 3: Readability (ARI ≤10.0, 80%+ sentences 8-12 words)
       |                    Max 5 attempts with detailed feedback per retry
       v
[Phase  4] Claim Gate ───── Post-write claim verification
       |                    Zero-tolerance: fabricated citations, attribution mismatches
       |                    Soft limits: ≤2 uncited claims, ≤15% ungrounded ratio
       v
[Phase  6] Feedback ─────── Self-correction from human edits (DeepSeek-V3)
                            Extracts style rules, scores research/writer quality,
                            triggers playbook distillation at ≥10 articles
```

---

## Quick Start

### Prerequisites

- [Python 3.10+](https://www.python.org/downloads/)
- [Git](https://git-scm.com/downloads)
- [Node.js / npm](https://nodejs.org/en/) (required for DataForSEO MCP server)

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/jordannewby/ark-opus.git
cd ark-opus

# 2. Set up Python virtual environment
python -m venv venv

# Windows:
.\venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Install DataForSEO MCP server dependencies
cd mcp-dataforseo-server
npm install
cd ..

# 5. Create your .env file (NEVER commit this file)
cp .env.example .env
# Edit .env with your actual API keys (see Environment Variables below)

# 6. Install pre-commit hook (blocks accidental secret commits)
cp hooks/pre-commit .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit

# 7. Start the application
uvicorn app.main:app --reload
```

**Access Points:**
- Frontend UI: `http://127.0.0.1:8000/`
- API docs (Swagger): `http://127.0.0.1:8000/docs`
- Health check: `http://127.0.0.1:8000/health`

### Verify Installation

1. Open `http://127.0.0.1:8000/` — you should see the Ark Opus Console UI
2. Check browser console (F12) for errors
3. Hit `/health` to verify API connectivity

---

## Environment Variables

Create a `.env` file in the project root. **This file is gitignored and must never be committed.**

### Required

```env
# Database — Neon PostgreSQL (https://neon.tech)
DATABASE_URL="postgresql://user:password@host:5432/dbname?sslmode=require"

# Anthropic — Claude Sonnet 4.5 for writing (https://console.anthropic.com)
ANTHROPIC_API_KEY="your-anthropic-api-key-here"

# ZhipuAI — GLM-5 for research + verification (https://open.bigmodel.cn)
ZAI_API_KEY="your-zai-api-key-here"

# DeepSeek — V3 for briefing/psychology/feedback, R1 for cartographer (https://platform.deepseek.com)
DEEPSEEK_API_KEY="your-deepseek-api-key-here"

# Exa.ai — Neural search for source discovery (https://dashboard.exa.ai)
EXA_API_KEY="your-exa-api-key-here"

# DataForSEO — SERP, keywords, backlinks, on-page analysis (https://app.dataforseo.com)
DATAFORSEO_LOGIN="your-dataforseo-login"
DATAFORSEO_PASSWORD="your-dataforseo-password"

# Admin — API key management endpoint authentication
# Generate: python -c "import secrets; print(secrets.token_urlsafe(32))"
ADMIN_SECRET="your-admin-secret-here"
```

### Optional

```env
# Enable debug mode for verbose SSE events and logging
ARK_DEBUG=true
```

### Security Notes

- All keys loaded via `os.getenv()` in `app/settings.py` — never hardcoded
- Server refuses to start if critical keys are missing
- Verify your `.env` is ignored: `git check-ignore .env` (should output `.env`)
- If keys are accidentally exposed, rotate immediately at provider dashboards

---

## Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **API Framework** | FastAPI | REST endpoints + SSE streaming |
| **Database** | Neon PostgreSQL + SQLAlchemy 2.0 | Multi-tenant ORM with connection pooling |
| **Reasoning LLM** | GLM-5 / DeepSeek-R1 | Research orchestration, source verification, campaign planning |
| **Chat LLM** | DeepSeek-V3 | Briefing, psychology, feedback, intelligence distillation |
| **Writer LLM** | Claude Sonnet 4.5 | Article generation with extended thinking |
| **Research APIs** | Exa.ai + DataForSEO MCP | Neural search + SEO intelligence (SERP, keywords, backlinks, on-page) |
| **Streaming** | SSE (Server-Sent Events) | Real-time frontend updates |
| **Frontend** | Vanilla JS + Tailwind CSS | Console UI with real-time agent visualization |
| **HTTP Client** | httpx (async) + Anthropic SDK | LLM API calls |
| **Validation** | Pydantic | Request/response schema enforcement |
| **MCP Framework** | Model Context Protocol | DataForSEO tool integration |

---

## API Endpoints

All endpoints except `/health` and `/` require `X-API-Key` header authentication.

| Endpoint | Method | Auth | Rate Limit | Purpose |
|----------|--------|------|------------|---------|
| `/generate/{keyword:path}` | POST | API Key | 5/min, 50/day | Full 7-phase pipeline (SSE stream) |
| `/research/{keyword:path}` | GET | API Key | 10/min | Phase 1 research only |
| `/clarify` | GET | API Key | - | Phase 0 — 3 clarifying questions |
| `/blueprint` | POST | API Key | - | Phase 2 psychology blueprint only |
| `/posts` | GET | API Key | - | List articles (profile-scoped) |
| `/posts/{post_id}` | GET | API Key | - | Fetch specific article |
| `/posts/{post_id}/approve` | POST | API Key | - | Approve edits, trigger feedback + scoring |
| `/rules` | GET/POST | API Key | - | Manage style rules (max 25/profile) |
| `/rules/{rule_id}` | DELETE | API Key | - | Delete style rule (ownership verified) |
| `/workspaces` | GET/POST | API Key | - | Manage workspaces (profile-scoped) |
| `/campaigns` | GET | API Key | - | Fetch campaigns |
| `/campaigns/plan` | POST | API Key | 10/min | Cartographer hub-and-spoke planning |
| `/settings` | GET/PUT | API Key | - | Profile settings (tunable thresholds) |
| `/admin/api-keys` | POST | Admin Secret | - | Create API keys (`X-Admin-Secret` header) |
| `/health` | GET | None | - | System status |
| `/` | GET | None | - | Frontend UI |

---

## Cost Breakdown

| Service | Purpose | Cost per Article | Model |
|---------|---------|------------------|-------|
| **Anthropic** | Writer phase | ~$0.05 | Claude Sonnet 4.5 |
| **ZhipuAI** | Research + verification | ~$0.06 | GLM-5 |
| **DeepSeek** | Briefing, psychology, feedback, cartographer | ~$0.02 | V3 + R1 |
| **Exa.ai** | Neural search | ~$0.01 | scout_search, extract |
| **DataForSEO** | SERP, keywords, on-page (via MCP) | ~$0.02 | SERP, keyword ideas, on-page |
| **Neon PostgreSQL** | Database | Free tier (3GB) or ~$7/mo | PostgreSQL 15 |

**Total per article:** $0.15-0.30 (varies by research depth and retry count)

**Budget planning:**
- $10/month = ~35-65 articles
- $20/month = ~70-130 articles

**Cost optimizations built in:**
- Research caching (24h TTL) — reuses results for same keyword/niche/profile
- Domain credibility cache (90-day TTL) — reduces verification API calls by ~40%
- Playbook distillation — reduces prompt token injection after 10+ articles
- Configurable limits: `EXA_NUM_RESULTS`, `MAX_AGENTIC_ITERATIONS`, `MAX_WRITER_ATTEMPTS`

---

## Security

Ark Opus implements defense-in-depth across authentication, prompt injection, rate limiting, and frontend hardening.

### Authentication & Authorization

- **API key auth** — All endpoints (except `/health`, `/`) require `X-API-Key` header. Keys are SHA256-hashed and validated against the `api_keys` table via `app/auth.py`
- **Admin endpoint** — `POST /admin/api-keys` requires `X-Admin-Secret` header, validated with `secrets.compare_digest()` (timing-safe)
- **Key generation** — `secrets.token_urlsafe(32)`, stored as SHA256 hash (never plaintext)
- **Profile scoping** — Each API key is bound to a `profile_name`; all database queries filter by profile for multi-tenant isolation

### Prompt Injection Defense

All data entering LLM prompts is sanitized via `app/security.py`:

| Function | Protection | Usage |
|----------|-----------|-------|
| `sanitize_prompt_input()` | Strips HTML comments + control chars, truncates, wraps in XML boundary tags | User-controlled inputs (keyword, niche, context, briefing answers) |
| `sanitize_external_content()` | Strips HTML comments + control chars, truncates (no boundary tags) | External/LLM-derived data (Exa content, style rules, claim feedback, web content) |

**Coverage** — sanitization applied at every LLM prompt boundary across all 8 agent services.

**Input length bounds** — Pydantic `Field(max_length=...)` at API boundary AND truncation before LLM injection: `MAX_USER_CONTEXT_CHARS=2000`, `MAX_STYLE_RULES_CHARS=1500`, `MAX_RESEARCH_JSON_CHARS=6000`, `MAX_PLAYBOOK_CHARS=1500`

### Rate Limiting & Abuse Prevention

- **Per-endpoint rate limits** — `slowapi`: `/generate` (5/min), `/research` (10/min), `/campaigns/plan` (10/min); keyed by API key hash
- **Daily generation cap** — `MAX_DAILY_GENERATIONS=50` per profile per day
- **Style rule cap** — `MAX_STYLE_RULES_PER_PROFILE=25` prevents unbounded memory accumulation
- **Agentic loop limits** — `MAX_AGENTIC_ITERATIONS=5`, `MAX_WRITER_ATTEMPTS=5` cap per-request cost

### Security Headers

`SecurityHeadersMiddleware` adds to all responses:
- `Strict-Transport-Security: max-age=63072000; includeSubDomains` (HSTS)
- `Content-Security-Policy` (restricted script/style/font/connect sources)
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy: camera=(), microphone=(), geolocation=()`

### Frontend Security

- **XSS prevention** — All `innerHTML` assignments wrapped in `DOMPurify.sanitize()`
- **Markdown rendering** — `marked.parse()` output sanitized via DOMPurify before DOM insertion
- **SRI hashes** — Third-party scripts loaded with Subresource Integrity
- **Error isolation** — SSE error events send generic messages only; stack traces never reach the client

### Secrets Management

- All API keys loaded via `os.getenv()` in `app/settings.py` — never hardcoded in source
- `.env` is gitignored; `.env.example` provides the template with placeholder values
- Pre-commit hook (`hooks/pre-commit`) blocks `.env` files and scans for API key patterns
- Server validates critical keys at startup — refuses to start if missing

```bash
# Verify before committing
git check-ignore .env          # Should output: .env
git status                     # Should NOT show .env
```

---

## Architecture Deep Dive

<details>
<summary><strong>Phase -1: Cartographer (Hub-and-Spoke Planning)</strong></summary>

**Trigger**: `/campaigns/plan` endpoint
**Model**: DeepSeek-R1 (`deepseek-reasoner`)
**Purpose**: Maps keyword clusters into strategic content campaigns

**Process**:
1. Fetches 100-700 keyword ideas from DataForSEO based on a seed keyword
2. DeepSeek-R1 analyzes keyword intent, search volume, and topical relationships
3. Structures results into a **Pillar keyword** (main topic) + up to **10 Spoke keywords** (supporting subtopics)
4. Each spoke includes: keyword, KD, volume, intent classification (Informational/Commercial), content angle

**Filtering rules**: Discards job-seeking, navigational, competitor-branded, and irrelevant keywords. Prefers 4 good spokes over 10 forced ones. Target KD < 45 for spokes.

**Output**: `ContentCampaign` database record (queryable via `/campaigns` endpoint)

**Cost**: ~$0.02/campaign

</details>

<details>
<summary><strong>Phase 0: Briefing Agent (Clarification Loop)</strong></summary>

**Trigger**: `/clarify` endpoint (optional, user-facing)
**Model**: DeepSeek-V3 (`deepseek-chat`)
**Purpose**: Asks 3 targeted clarifying questions before heavy research

**Process**:
1. Accepts a raw keyword + free-form niche description
2. DeepSeek-V3 generates 3 specific questions to refine context
3. User answers are stored and injected into Phase 1's research prompt (capped at 2,000 chars)

**Example Questions**:
- "Are you targeting IT managers or technical implementers?"
- "Should we focus on on-premise or cloud-native solutions?"
- "Do you want vendor comparisons or implementation best practices?"

**Cost**: ~$0.002/call

</details>

<details>
<summary><strong>Phase 1: Research Agent (Agentic Intelligence Gathering)</strong></summary>

**Trigger**: `/generate` endpoint start
**Model**: GLM-5 (`glm-5`) for agentic tool orchestration via ZhipuAI API
**Tools**: DataForSEO MCP (keyword ideas, live SERP, backlinks, on-page analysis) + Exa.ai (neural search, full-text extraction)

**Process**:
1. **Agentic Loop** (max 5 iterations): GLM-5 autonomously decides which tools to use based on information gaps
2. **3-Step Sequencing**:
   - **Mandatory**: Keyword ideas + SERP data (always runs first)
   - **Strategic**: Exa scout search + extract full text (GLM-5 decides when to use)
   - **Final**: Synthesize research dict with competitive intelligence
3. **Niche Filtering**: Maps 30+ niche aliases (e.g., "cybersecurity" -> ["infosec", "appsec", "netsec"]) to 9 categories, filters Exa searches by domain credibility
4. **Keyword Relevance Fallback**: If <3 relevant sources found after niche-filtered search, triggers unfiltered Exa + broad backfill
5. **Metadata Preservation**: Stores `publishedDate` + `score` via `url_metadata_map` for Phase 1.5 scoring
6. **On-Page Competitor Analysis**: Analyzes top 10 SERP competitors via DataForSEO On-Page API for readability metrics, on-page SEO scores (0-100), and word count benchmarks
7. **MCP 429 Retry**: Exponential backoff (1s -> 2s -> 4s, max 3 retries) on DataForSEO rate-limits
8. **Niche Playbook Injection**: If >=10 prior runs exist for this niche, injects distilled playbook (~200 tokens) to guide tool selection

**Output**: Research dict with competitive headers, semantic entities, People-Also-Ask questions, KD metrics, `elite_competitors` list, and `content_patterns` (competitor benchmarks)

**Cost**: ~$0.08/article

</details>

<details>
<summary><strong>Phase 1.5: Source Verification & Fact Extraction</strong></summary>

**Trigger**: Automatic if `elite_competitors` found in Phase 1
**Models**: GLM-5 for integrity/quality checks + DeepSeek-V3 for fact extraction
**Tools**: DataForSEO MCP (domain authority), Exa.ai, cached domain credibility lists

**7-Factor Credibility Scoring** (0-85 base + 15 rescue bonus = 100 max):
- **Content Integrity** (0-25pts): GLM-5 adversarial check for promotional intent, claim sourcing, specificity
- **Content Quality** (0-15pts): Depth, evidence, structure assessment
- **Domain Tier + Authority** (0-20pts): 4-tier classification + DataForSEO domain rank
- **Content Freshness** (0-15pts): Exa `publishedDate` + OpenGraph metadata + regex date patterns
- **Author Attribution** (0-5pts): E-E-A-T signals (author names, credentials)
- **Topical Relevance** (0-5pts): Exa neural search score
- **Spam Penalty** (-10pts): If promotional_intent >= 0.9

**Threshold**: 45.0/100 minimum. Rescue bonus for borderline sources (35-45): up to +15pts from SERP ranking, citation count, content depth, domain cache.

**Fact Extraction** (DeepSeek-V3):
- Types: statistics, benchmarks, case studies, expert quotes, survey results
- Confidence: 0.0-1.0 scale (>=0.6 required to pass)
- Citation laundering detection: Maps 70+ research organizations to canonical domains

**Iterative Backfill**: If <3 sources verified, retries with decaying thresholds (45 -> 40 -> 35) and broader search.

**Gate**: Generation **fails** if <3 credible sources remain after all backfill attempts.

**AI Content Detection** (deterministic, $0.00 cost):
- 4 measurable signals: type-token ratio, sentence length variance, hedging phrase density, transition formula density
- Tier-aware penalty applied after scoring

**Cost**: ~$0.01/article

</details>

<details>
<summary><strong>Phase 2: Psychology Agent (Persuasion Blueprint)</strong></summary>

**Trigger**: After Phase 1.5 completes
**Model**: DeepSeek-V3 (`deepseek-chat`)
**Prompt**: `app/services/prompts/persuasion.md` — PAS framework

**Process**:
1. Receives research dict + verified facts + competitor benchmarks
2. Maps article structure to psychological triggers using **PAS (Problem-Agitation-Solution)**
3. Generates structured JSON blueprint with dynamic content length targets based on top-ranking competitors

**Output includes**:
- Hook strategy (stat-driven, case-study-led, contrarian)
- Target identity (reader persona)
- Agitation points (3-5 pain amplifiers)
- Identity hooks (expert vs. amateur, visionary vs. follower, insider vs. crowd)
- Semantic entity map
- Outline structure with H2/H3 hierarchy and psychological purpose per section

**Heading rules enforced**: <=10 words per heading, no word >3 syllables, 7th-grade readability, 22+ banned words (delve, landscape, multifaceted, comprehensive, etc.)

**Cost**: ~$0.01/article

</details>

<details>
<summary><strong>Phase 3: Writer Service (Content Generation + 3-Gate Validation)</strong></summary>

**Trigger**: After Phase 2 completes
**Model**: Claude Sonnet 4.5 (`claude-sonnet-4-5-20250929`) via native Anthropic SDK
**Process**: Iterative loop (max 5 attempts) with 3 sequential gates

#### Gate 1: SEO Validation
- Min word count: **1,500**
- Min H2 count: **5**
- Min list/table density: **3 blocks**
- Information Gain Density: **>=2.0**

#### Gate 2: Citation & Claim Verification (Two-Stage)

**Stage A**: Citation requirement validation
- Detects claims via 8 regex patterns (percentages, dollar amounts, comparative stats, benchmarks)
- 0-2 claims detected -> 3 citations minimum; 3+ claims -> 1 citation per claim

**Stage B**: Post-writer claim cross-referencing
- Extracts claim+citation pairs from article prose
- 3-tier URL matching: exact -> normalized -> domain
- Number-anchored matching: requires shared number + >=2 context words
- Text similarity threshold: >=0.45
- Classification: VERIFIED, FABRICATED (zero-tolerance), UNGROUNDED (zero-tolerance normally, softened to 15% max when <3 on-topic facts), AMBIGUOUS (LLM resolution, max 10)
- Attribution-URL mismatch detection (zero-tolerance)

#### Gate 3: Readability Validation
- **ARI <= 10.0** (7th-10th grade target)
- Flesch-Kincaid <= 11.5
- Average sentence length <= 12 words
- >= 80% of sentences in 8-12 word range
- Keyword masking: filters semantic keywords + 58 jargon terms for scoring (actual article keeps keywords)
- Citation masking: inline markdown citations treated as single words

#### Deterministic Post-Processing
- **Banned-word sanitizer**: 22 banned root words + all inflections stripped via regex after generation
- **Slop pattern removal**: Catches formulaic phrases ("it's worth noting", "in today's X Y")

#### Retry Logic
On gate failure: detailed feedback (specific counts, violation examples, fix instructions) sent to Claude for re-generation.

**Cost**: ~$0.05/article

</details>

<details>
<summary><strong>Phase 6: Self-Correction Loop (Feedback Agent)</strong></summary>

**Trigger**: `/posts/{post_id}/approve` endpoint after human edits
**Model**: DeepSeek-V3 (`deepseek-chat`)
**Purpose**: Learns user's writing style from edits

**Process**:
1. Compares `original_ai_content` vs `human_edited_content`
2. DeepSeek-V3 semantically diffs the two versions
3. Extracts permanent `UserStyleRule` entities (max 3 per approval):
   - Types: vocabulary_preference, structure_preference, tone_preference
   - Example: "implement" -> "set up", "utilize" -> "use"
4. Stores rules scoped by `profile_name` (max 25 per profile, auto-consolidated if >20)
5. Rules injected into Phase 3 writer prompt on future generations

**Intelligence Scoring**: Triggers `score_research_run()` (edit-distance ratio) and `score_writer_run()` (readability efficiency) for playbook distillation.

**Cost**: ~$0.01/approval

</details>

<details>
<summary><strong>Intelligence Loops (Self-Improvement System)</strong></summary>

### Research Intelligence Loop

**Telemetry captured**: tool sequences, KD stats, Exa queries, semantic entity clusters ($0.00 — pure Python)

**Playbook recall**: If >=10 prior runs for `(profile_name, niche)`, fetches `NichePlaybook` and injects ~200 tokens into GLM-5's research prompt.

**Reinforcement**: On `/approve`, computes edit-distance ratio (0.0-1.0) as `quality_score`.

**Distillation**: At >=10 undistilled runs with >=5 quality scores >=0.20, DeepSeek-V3 summarizes strategic patterns. Result upserted to `NichePlaybook` table.

### Writer Intelligence Loop

**Telemetry captured**: ARI, Flesch-Kincaid, Coleman-Liau, average sentence length, word count.

**Playbook recall**: If >=10 articles for niche, injects niche ARI baseline, target sentence length, and structure patterns.

**Reinforcement**: Computes readability efficiency `(10.0 - ari) / 10.0` as `efficiency_score`.

**Distillation**: Heuristic averages (median ARI, mean sentence length) upserted to `WriterPlaybook` table.

</details>

<details>
<summary><strong>Configuration Reference (app/settings.py)</strong></summary>

### Model Constants

```python
CLAUDE_MODEL = "claude-sonnet-4-5-20250929"
DEEPSEEK_MODEL = "deepseek-chat"        # DeepSeek-V3
DEEPSEEK_REASONER_MODEL = "deepseek-reasoner"  # DeepSeek-R1
GLM5_MODEL = "glm-5"                    # GLM-5 Deep Thinking
```

### Timeouts (seconds)

```python
BRIEFING_TIMEOUT = 30
DEEPSEEK_TIMEOUT = 60
DEEPSEEK_REASONER_TIMEOUT = 90
CARTOGRAPHER_TIMEOUT = 300
EXA_TIMEOUT = 30
```

### Research Tuning

```python
CACHE_TTL_HOURS = 24                # Research cache expiration
MAX_AGENTIC_ITERATIONS = 5          # Max GLM-5 reasoning loops
EXA_NUM_RESULTS = 10                # Results per Exa search
EXA_MAX_CHARACTERS = 25000          # Max content per source extract
SERP_DEPTH = 10                     # SERP results per query
LOCATION_CODE = 2840                # Geographic targeting (US)
LANGUAGE_CODE = "en"                # Language preference
```

### Writer Tuning

```python
MAX_WRITER_ATTEMPTS = 5             # Retry iterations for gate validation
WRITER_MAX_TOKENS = 8192            # Token budget per generation
```

### Source Verification

```python
SOURCE_CREDIBILITY_THRESHOLD = 45.0   # Min score to pass (0-100)
SOURCE_THRESHOLD_DECAY = 5.0          # Lower threshold on retries
MAX_VERIFICATION_ITERATIONS = 3       # Iterative backfill attempts
```

### Claim Verification

```python
MAX_EXA_FACT_CHECKS = 15
MAX_LLM_VERIFICATIONS = 10
CLAIM_TEXT_SIMILARITY_THRESHOLD = 0.45
MAX_UNCITED_CLAIMS = 2
MAX_UNGROUNDED_RATIO = 0.15
MAX_CLAIM_RETRIES = 2
```

### Penalties

```python
BLOG_DOMAIN_PENALTY = 10.0
BLOG_PATH_PENALTY = 5.0
UNSOURCED_CLAIMS_PENALTY = 15.0
```

### Runtime-Tunable Settings (via `/settings` endpoint)

```python
CONFIGURABLE_SETTINGS = {
    "claim_gate_hard_block": bool,           # Block save on claim failure (default: True)
    "verify_qualitative_claims": bool,       # Check "research shows" claims (default: True)
    "source_credibility_threshold": float,   # 35.0-75.0 range
    "exa_num_results": int,                  # 5-25 range
    "max_agentic_iterations": int,           # 2-10 range
    "cache_ttl_hours": int,                  # 1, 6, 24, or 72
    "writer_max_tokens": int,                # 4096-16384
    "max_writer_attempts": int,              # 1-10
}
```

</details>

<details>
<summary><strong>Database Schema</strong></summary>

Ark Opus uses **Neon PostgreSQL** (serverless). Tables are created automatically via migrations in `app/database.py`.

#### Post
Stores generated articles with readability analytics. Fields: `id`, `keyword`, `profile_name`, `niche`, `original_ai_content`, `human_edited_content`, `readability_scores`, `created_at`.

#### UserStyleRule
Learned writing preferences extracted by FeedbackAgent. Fields: `id`, `profile_name`, `rule_type`, `pattern`, `replacement`. Max 25 per profile.

#### ResearchCache
Caches research results (composite key: `keyword`, `profile_name`, `niche`). 24h TTL.

#### ResearchRun
Telemetry for Research Intelligence Loop. Fields: `id`, `profile_name`, `niche`, `tool_sequence`, `kd_stats`, `exa_queries`, `entity_clusters`, `quality_score`, `is_distilled`.

#### NichePlaybook
Distilled research strategies (composite key: `profile_name`, `niche`). Activated at >=10 runs.

#### WriterRun
Telemetry for Writer Intelligence Loop. Fields: `id`, `profile_name`, `niche`, `ari`, `flesch_kincaid`, `coleman_liau`, `avg_sentence_length`, `word_count`, `efficiency_score`, `is_distilled`.

#### WriterPlaybook
Distilled readability patterns (composite key: `profile_name`, `niche`). Activated at >=10 articles.

#### VerifiedSource
Sources scored in Phase 1.5. Fields: `id`, `research_run_id`, `source_url`, `domain`, `tier`, `composite_score`, `verification_status`, `published_date`. Unique constraint: `(research_run_id, source_url)`.

#### FactCitation
Extracted facts linked to verified sources. Fields: `id`, `source_id`, `fact_text`, `fact_type`, `citation_anchor`, `original_source`, `confidence`, `is_verified`, `verification_status`, `consensus_count`.

#### DomainCredibilityCache
90-day cache for domain credibility scores. Composite key: `(domain, niche)`. Reduces verification API calls by ~40%.

#### ContentCampaign
Hub-and-spoke keyword mappings from Cartographer. Fields: `id`, `profile_name`, `pillar_keyword`, `spoke_keywords`.

#### Workspace
Multi-tenant workspace definitions. Unique constraint: `(slug, profile_name)`.

</details>

<details>
<summary><strong>Frontend UI</strong></summary>

The frontend (`static/ark_opus_console.html` + `static/js/console.js`) features a cyberpunk-inspired glassmorphic interface with real-time agent visualization.

**Editor Pane**: Real-time markdown editor with live SEO audit scoring (mirrors backend gates), word/H2/citation count indicators, and "Approve" button for feedback loop.

**Blueprint Pane**: Displays psychology outline — hook strategy, target identity, agitation points, outline structure with H2/H3 hierarchy.

**Terminal**: Structured logs from all agents with phase progression indicators, source verification scores (color-coded: green >=70, yellow 45-69, red <45), and iteration feedback.

**Agent Nodes**: Visual indicators of active phase with glowing effect and progress dots.

**Modal System**: Workspace selector/creator, AI Brain (style rule management), Cartographer (campaign planner), Clarification Questions (Phase 0).

**State Management**: Global abort controller cancels in-flight SSE streams. Frontend clears `lastGeneratedMarkdown`, `currentPostId`, `currentQuestions`, and editor content before each generation. Custom `showConfirmModal()` replaces native `window.confirm()`.

</details>

<details>
<summary><strong>Troubleshooting</strong></summary>

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| `DEEPSEEK_API_KEY is missing` | `.env` not loaded or key missing | Verify `.env` exists with `DEEPSEEK_API_KEY="..."` |
| `DATABASE_URL environment variable is required` | Connection string missing | Add `DATABASE_URL="postgresql://..."` to `.env` |
| `ModuleNotFoundError: No module named 'anthropic'` | Dependencies not installed | Run `pip install -r requirements.txt` |
| MCP server fails to start | Node.js missing or DataForSEO creds wrong | Install Node.js, verify `DATAFORSEO_LOGIN`/`PASSWORD` in `.env` |
| Emoji in logs crashes (Windows) | cp1252 encoding | Codebase uses `[LABEL]` ASCII prefixes — if you see crashes, check for bare `print()` |
| Articles stuck in validation loops | Readability gate too strict | Tune `WRITER_MAX_TOKENS`, verify citation map provided |
| SSE stream disconnects mid-generation | Neon PostgreSQL SSL timeout | `nonlocal db` pattern handles reconnection automatically |
| Writer produces fabricated citations | Citation map not injected | Verify Phase 1.5 completed (check `verified_sources` table) |
| High API costs | Too many research iterations | Lower `MAX_AGENTIC_ITERATIONS`, enable caching |

### Debugging

```bash
# Enable debug mode
ARK_DEBUG=true uvicorn app.main:app --log-level debug
```

**Log prefixes**: `[ARK]` general, `[SCORE]` credibility scoring, `[RESCUED]` borderline sources, `[GATE]` writer validation, `[CLAIM-VERIFY]` claim cross-referencing.

**Frontend console (F12)**: SSE events show real-time agent execution — `phase1_start`, `source_verification`, `content`, `debug`, `error`.

</details>

---

## License

This project is proprietary software. All rights reserved.

You may view the source code for reference purposes only. No permission is granted to use, copy, modify, merge, publish, distribute, sublicense, or sell copies of this software without explicit written permission from the author.

For licensing inquiries, contact the repository owner.

---

## Development Notes

All development rules, security constraints, and architecture conventions are documented in `CLAUDE.md` (project root). Key highlights:

- **Async mandatory** — All HTTP clients + LLM calls must use async/await
- **Multi-tenant isolation** — All DB queries filter by `profile_name`
- **Prompt injection defense** — All LLM prompt boundaries must use `sanitize_prompt_input()` or `sanitize_external_content()`
- **Centralized config** — All constants in `app/settings.py`; never hardcode values in services
- **Prompt files read-only** — Never modify `app/services/prompts/*.md` without explicit approval

For detailed phase diagrams, scoring algorithms, and intelligence loop mechanics, see `docs/architecture.md`.
