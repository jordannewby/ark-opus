# Ares Engine

Ares Engine is a sophisticated, fully autonomous, asynchronous **7-Phase AI Content Pipeline** that orchestrates multiple LLMs (GLM-5, DeepSeek-V3, Claude Sonnet 4.5) and external APIs (Exa.ai, DataForSEO MCP) to dynamically build deeply researched, psychologically persuasive, and fact-verified 1,600+ word Markdown articles with citation-backed claims.

It features real-time UI streaming via Server-Sent Events (SSE), multi-gate validation (SEO, Citation, Readability), and self-improving intelligence loops that learn from user feedback to converge on your exact writing style over time.

---

## Table of Contents

1. [What is Ares Engine?](#1-what-is-ares-engine)
2. [The 7-Phase Pipeline](#2-the-7-phase-pipeline)
3. [Intelligence Loops (Self-Improvement)](#3-intelligence-loops-self-improvement)
4. [Tech Stack](#4-tech-stack)
5. [Quickstart Guide](#5-quickstart-guide)
6. [Environment Variables](#6-environment-variables)
7. [Configuration (app/settings.py)](#7-configuration-appsettingspy)
8. [Database Schema](#8-database-schema)
9. [API Endpoints](#9-api-endpoints)
10. [Frontend UI](#10-frontend-ui)
11. [Cost Breakdown](#11-cost-breakdown)
12. [Security](#12-security)
13. [Troubleshooting](#13-troubleshooting)
14. [Development Notes](#14-development-notes)

---

## 1. What is Ares Engine?

Ares Engine is an **AI-powered content generation platform** designed to produce SEO-optimized, fact-verified articles at scale. Unlike simple LLM wrappers, Ares orchestrates a sophisticated pipeline that:

- **Researches** keywords using agentic tool orchestration (GLM-5 Deep Thinking)
- **Verifies** sources via 7-factor credibility scoring (domain authority, freshness, integrity)
- **Extracts** verifiable facts with confidence scoring and citation mapping
- **Strategizes** psychological frameworks (PAS - Problem-Agitation-Solution)
- **Writes** publication-ready prose (Claude Sonnet 4.5) with 3-gate validation
- **Cross-references** claims against verified facts to prevent hallucinations
- **Learns** from human edits to improve over time via intelligence loops

### Key Features

- **Agentic Research**: GLM-5 autonomously decides which tools to use (DataForSEO, Exa.ai) across 5 iterative reasoning loops
- **Source Credibility System**: 4-tier domain classification (Government/Academic → Tech Giants → Industry Blogs → General) with 7-factor scoring algorithm
- **Fact Verification**: Zero-tolerance for fabricated citations; cross-references every claim against verified source facts
- **Multi-Gate Validation**: Articles must pass SEO metrics (1,500+ words, 5+ H2s), citation requirements, and readability standards (7th-10th grade ARI)
- **Real-Time Streaming**: SSE-based UI shows live agent execution, source verification scores, and iteration feedback
- **Self-Improving**: Research and Writer intelligence loops distill playbooks from past runs (≥10 articles) to guide future generations
- **Multi-Tenant**: Workspace-scoped isolation with per-profile style rules and niche playbooks

### Use Cases

- **SEO Content Agencies**: Generate 35-65 researched articles/month on a $10 budget
- **Niche Blogs**: Cybersecurity, AI/ML, GRC, Blue/Red/Purple Team technical content
- **Thought Leadership**: Citation-backed industry analysis with psychological persuasion
- **Content Teams**: Human-in-the-loop workflow where editors approve/refine AI drafts

---

## 2. The 7-Phase Pipeline

### Phase -1: Cartographer (Hub-and-Spoke Planning)

**Trigger**: `/campaigns/plan` endpoint
**Model**: DeepSeek-R1 (`deepseek-reasoner`)
**Purpose**: Maps keyword clusters into strategic content campaigns

**Process**:
1. Fetches 100+ keyword ideas from DataForSEO based on a seed keyword
2. DeepSeek-R1 analyzes keyword intent, search volume, and topical relationships
3. Structures results into a **Pillar keyword** (main topic) + **10 Spoke keywords** (supporting subtopics)
4. Each spoke includes: keyword, intent classification, content angle suggestion

**Output**: `ContentCampaign` database record (persistent, queryable via `/campaigns` endpoint)

**Example**:
- **Pillar**: "zero trust architecture"
- **Spokes**: "zero trust network access", "microsegmentation strategies", "ZTNA vs VPN", etc.

---

### Phase 0: Briefing Agent (Clarification Loop)

**Trigger**: `/clarify` endpoint (optional, user-facing)
**Model**: DeepSeek-V3 (`deepseek-chat`)
**Purpose**: Asks 3 targeted clarifying questions before heavy research

**Process**:
1. Accepts a raw keyword + free-form niche description
2. DeepSeek-V3 generates 3 specific questions to refine context
3. User answers are stored and injected into Phase 1's research prompt

**Output**: List of 3 questions with user-provided answers

**Example Questions**:
- "Are you targeting IT managers or technical implementers?"
- "Should we focus on on-premise or cloud-native solutions?"
- "Do you want vendor comparisons or implementation best practices?"

---

### Phase 1: Research Agent (Agentic Intelligence Gathering)

**Trigger**: `/generate` endpoint start
**Model**: GLM-5 (`glm-5`) for agentic tool orchestration via ZhipuAI API
**Tools**: DataForSEO MCP (keyword ideas, live SERP, backlinks, on-page analysis) + Exa.ai (neural search, full-text extraction)

**Process**:
1. **Agentic Loop** (max 5 iterations): GLM-5 autonomously decides which tools to use based on information gaps
2. **3-Step Sequencing**:
   - **Mandatory**: Keyword ideas + SERP data (always runs first)
   - **Strategic**: Exa scout search → extract full text (GLM-5 decides when to use)
   - **Final**: Synthesize research dict with competitive intelligence
3. **Niche Filtering**: Maps 30+ niche aliases (e.g., "cybersecurity" → ["infosec", "appsec", "netsec"]) to 9 categories, filters Exa searches by domain credibility
4. **Keyword Relevance Fallback**: If <3 relevant sources found after niche-filtered search, triggers unfiltered Exa + broad backfill
5. **Metadata Preservation**: Stores `publishedDate` + `score` via `url_metadata_map` for Phase 1.5 scoring
6. **On-Page Competitor Analysis**: Analyzes top 10 SERP competitors via DataForSEO On-Page API for readability metrics, content quality scores (0-1 scale), on-page SEO scores (0-100), Core Web Vitals, and word count benchmarks
7. **MCP 429 Retry**: Exponential backoff (1s→2s→4s, max 3 retries) on DataForSEO rate-limits
8. **Niche Playbook Injection**: If ≥10 prior runs exist for this niche, injects distilled playbook (~200 tokens) to guide tool selection

**Output**: Research dict with:
- Competitive headers/subheaders from top-ranking pages
- Semantic entities (technologies, frameworks, people, companies)
- People-Also-Ask questions
- Backlink authority scores
- KD (keyword difficulty) metrics
- `elite_competitors` list (URLs of top sources for Phase 1.5)
- `content_patterns` (competitor benchmarks: avg word count, on-page scores, readability metrics, top 5 competitor details)

**Cost**: ~$0.08/article (GLM-5 reasoning tokens)

---

### Phase 1.5: Source Verification & Fact Extraction

**Trigger**: Automatic if `elite_competitors` found in Phase 1
**Model**: GLM-5 (`glm-5`) for integrity/quality checks + fact extraction via ZhipuAI API
**Tools**: DataForSEO MCP (domain authority), Exa.ai, cached domain credibility lists

**Process**:
1. **7-Factor Credibility Scoring** (0-85 base + 15 rescue bonus = 100 max):
   - **Content Integrity** (0-25pts): DeepSeek adversarial check for promotional intent, claim sourcing, specificity
   - **Content Quality** (0-15pts): Depth, evidence, structure assessment
   - **Domain Tier + Authority** (0-20pts): 4-tier classification + DataForSEO domain rank
   - **Content Freshness** (0-15pts): Exa `publishedDate` + OpenGraph metadata + regex date patterns
   - **Author Attribution** (0-5pts): E-E-A-T signals (author names, credentials, contact info)
   - **Topical Relevance** (0-5pts): Exa neural search score
   - **Spam Penalty** (-10pts): If promotional_intent ≥ 0.9
2. **Threshold**: 45.0/100 minimum (53% pass rate)
3. **Rescue Bonus** (borderline sources 35-45): Up to +15pts from:
   - SERP ranking position (+5pts if top 3)
   - Citation count in content (+3pts)
   - Content depth indicators (+4pts)
   - Domain credibility cache hits (+3pts)
4. **Fact Extraction**: DeepSeek extracts verifiable claims:
   - **Types**: Statistics, benchmarks, case studies, expert quotes, survey results
   - **Confidence**: 0.0-1.0 scale (≥0.6 required to pass)
   - **Original Source**: Named study/report/expert (e.g., "Gartner 2024 Report")
   - **Citation Anchor**: Display text for markdown link (e.g., "according to Gartner")
5. **Iterative Backfill**: If <3 sources verified after initial pass:
   - **Attempt 1**: Threshold decay 45→40, find similar sources
   - **Attempt 2**: Threshold 40→35, niche-filtered Exa search
   - **Attempt 3**: Threshold 35, broad unfiltered search
6. **Citation Map Building**: Facts stored in `FactCitation` table, formatted as pre-rendered markdown bullets for writer consumption

**Output**:
- `VerifiedSource` database records (credibility scores, metadata)
- `FactCitation` records linking facts to sources
- Pre-formatted citation map (markdown bullets with source URLs)

**Gate**: Generation **fails** if <3 credible sources remain after all backfill attempts

**Cost**: ~$0.01/article (DataForSEO domain rank + DeepSeek fact extraction)

---

### Phase 2: Psychology Agent (Persuasion Blueprint)

**Trigger**: After Phase 1.5 completes
**Model**: DeepSeek-V3 (`deepseek-chat`)
**Prompt**: `app/services/prompts/persuasion.md` — PAS framework

**Process**:
1. Receives research dict + verified facts from Phase 1/1.5
2. **Injects competitor benchmarks** from On-Page analysis (avg word count, on-page scores, readability targets) for niche-specific adaptation
3. Maps article structure to psychological triggers using **PAS (Problem-Agitation-Solution)**:
   - **Problem**: Identify pain points from research (e.g., "traditional perimeter security fails against lateral movement")
   - **Agitation**: Amplify consequences (e.g., "82% of breaches involve insider threats")
   - **Solution**: Position keyword as remedy (e.g., "zero trust microsegmentation eliminates implicit trust")
4. Generates structured JSON blueprint with dynamic content length targets based on top-ranking competitors:
   - **Hook Strategy**: Opening angle (stat-driven, case-study-led, contrarian)
   - **Target Identity**: Reader persona (CISO, SOC analyst, compliance officer)
   - **Agitation Points**: 3-5 pain amplifiers with emotional triggers
   - **Identity Hooks**: Language patterns that reinforce reader's self-image
   - **Semantic Entity Map**: Technologies/frameworks to weave into prose
   - **Outline Structure**: H2/H3 hierarchy with psychological purpose per section

**Output**: Blueprint JSON (saved to database, displayed in UI Blueprint Pane)

**Cost**: ~$0.01/article (DeepSeek-V3)

---

### Phase 3: Writer Service (Content Generation + Multi-Gate Validation)

**Trigger**: After Phase 2 completes
**Model**: Claude Sonnet 4.5 (`claude-sonnet-4-5-20250929`) via native Anthropic SDK
**Process**: Iterative loop (max 5 attempts) with **3 sequential gates**

#### Gate 1: SEO Validation

**Requirements**:
- Min word count: **1,500**
- Min H2 count: **5**
- Min list/table density: **3 blocks**
- Information Gain Density: **≥2.0** (unique insights per 100 words)

**Feedback on Failure**: All conditions reported with specific counts (e.g., "Only 1,342 words, need 1,500")

#### Gate 2: Citation & Claim Verification

**Two-Stage Process**:

**Stage A: Citation Requirement Validation**
- Detects claims via 8 regex patterns:
  - Percentages (e.g., "72% of organizations")
  - Dollar amounts (e.g., "$4.5M average cost")
  - Comparative stats (e.g., "3x more likely")
  - Benchmarks (e.g., "industry standard of 99.9% uptime")
- **Citation Requirements**:
  - 0-2 claims detected → 3 citations minimum
  - 3+ claims → 1 citation per claim minimum
- **Accepted Formats**:
  - Markdown links: `[text](url)`
  - Parenthetical: `(Source 2024)`
  - Footnotes: `[1]`

**Stage B: Post-Writer Claim Cross-Referencing**
1. Extracts claim+citation pairs from article prose
2. Matches each citation URL against `FactCitation` database via **3-tier matching**:
   - **Exact**: Full URL match
   - **Normalized**: Domain + path prefix match
   - **Domain**: Domain-only match (weaker)
3. **Claim Classification**:
   - **VERIFIED**: Claim text matches source fact (text similarity ≥0.2)
   - **FABRICATED**: Citation URL not in fact map (zero-tolerance, triggers retry)
   - **UNGROUNDED**: URL exists but claim doesn't match source facts (zero-tolerance normally, softened to 15% max when <3 on-topic facts available)
   - **AMBIGUOUS**: Sent to LLM for resolution (max 10 per article, requires ≥0.7 confidence)
4. **Attribution-URL Mismatch Detection**: Flags "Gartner says X" linked to random blog (zero-tolerance, triggers retry)
5. **Topical Coverage Softening**: If <3 on-topic facts found in citation map, allows `max(2, int(total_claims * 0.15))` ungrounded claims

**Feedback on Failure**: Shows available facts per source with correction instructions

#### Gate 3: Readability Validation

**Primary Metric**: **ARI (Automated Readability Index) ≤10.0** (7th-10th grade target)

**Cross-Check**: Flesch-Kincaid ≤11.5 (+1.5 buffer)

**Advisory**: Coleman-Liau (reports but doesn't block — over-penalizes technical vocab)

**Sentence Constraints**:
- Average sentence length ≤12 words
- **≥80%** of sentences in 8-12 word range
- **≤15%** can exceed 15 words

**Keyword Masking**: Filters semantic keywords + blueprint entities + 58 niche business jargon terms (e.g., streamline, leverage, optimize, enhance, framework, ecosystem, paradigm, synergize)

**Citation Masking**: Inline markdown citations `[text](url)` treated as single words

**Feedback on Failure**:
- Exact distribution (e.g., "Only 62% in 8-12 range, need 80%")
- Per-sentence analysis showing length violations
- Concrete word-swap table (e.g., "implement → set up", "utilize → use")

#### Prompt Injection

Claude receives:
- **User Style Rules**: Learned via FeedbackAgent from past human edits
- **WriterPlaybook**: Distilled readability patterns if ≥10 articles exist (niche ARI baseline, target sentence length)
- **Citation Map**: Pre-rendered markdown bullets from Phase 1.5 with **CRITICAL CITATION REQUIREMENTS** warning
- **Topical Mismatch Warning**: If <3 on-topic citations found, alerts Claude to expect limited factual grounding
- **Pre-Flight Simplicity Primer** + **7th-Grade Template Sentences** for pattern-matching
- **Layer-Cake Scanning Format**: H2s every 150-200 words, first-sentence takeaways, bold anchors
- **Word-Swap Reference Table**: 58 banned words with simple alternatives embedded in prompt
- **Dynamic `READABILITY_DIRECTIVE`**: Injected per-iteration based on gate failures (never modifies `writer.md` file)

#### Deterministic Banned-Word Sanitizer

**Post-LLM Regex**: Catches inflected forms Claude might miss:
- 22 banned root words (leverage, optimize, landscape, streamline, etc.)
- All variants: leveraging, leveraged, optimized, optimizing, landscapes, landscaping, etc.
- Runs **after** Claude generates, strips variants deterministically

#### Retry Logic

On Gate 1-3 failure:
1. Reporter generates detailed feedback (specific counts, violation examples, fix instructions)
2. Feedback sent to Claude in follow-up message
3. Claude regenerates article (attempt 2/5)
4. Process repeats until all gates pass or max attempts reached

**Streaming**: Real-time SSE events:
- `content` — Live typing effect (article prose chunks)
- `debug` — Iteration logs, gate pass/fail with reasons
- `control` — `RETRY_CLEAR` signal to reset editor before retry

**Output**: ~1,600 word markdown article (streamed in real-time)

**Cost**: ~$0.05/article (Claude Sonnet 4.5 input+output tokens)

---

### Phase 4: Post-Writer Claim Verification Gate

**Trigger**: After Phase 3 completes (integrated into Gate 2)
**Function**: Cross-references article claims against verified facts (described in Gate 2 Stage B above)

**Capabilities**:
- Extracts article claims via regex (claim text + citation URL pairs)
- Detects uncited claims (claims without markdown links)
- Detects attribution-URL mismatches (org named in prose but linked to wrong domain)
- Performs 3-tier URL matching + number anchoring + text similarity checks
- Max 2 claims sent to DeepSeek LLM for ambiguous resolution

**Retry on Failure**: If fabricated, uncited, ungrounded, or mismatch claims detected, re-runs writer with feedback (max 2 retries)

**Graceful Degradation**: If Phase 1.5 (Exa Research API) failed and no fact citations exist, claim verification is skipped entirely. The article is saved with an informational note that verified facts were unavailable.

**Final Gate**: Proceeds to save if:
- Zero fabricated claims
- Zero attribution mismatches
- `≤MAX_UNCITED_CLAIMS` (tunable, default 2)
- `≤MAX_UNGROUNDED_RATIO` of total claims ungrounded (default 15%)

---

### Phase 6: Self-Correction Loop (Feedback Agent)

**Trigger**: `/posts/{post_id}/approve` endpoint after human edits
**Model**: DeepSeek-V3 (`deepseek-chat`)
**Purpose**: Learns user's writing style from edits

**Process**:
1. Compares `original_ai_content` vs `human_edited_content`
2. DeepSeek-V3 semantically diffs the two versions
3. Extracts permanent `UserStyleRule` entities:
   - **Type**: vocabulary_preference, structure_preference, tone_preference
   - **Pattern**: Original phrase → Preferred replacement
   - **Example**: "implement" → "set up", "utilize" → "use"
4. Stores rules in database scoped by `profile_name`
5. Rules injected into Phase 3 writer prompt on future generations

**Background Task**: Runs in a separate `SessionLocal()` connection (request-scoped session closes after `/approve` response)

**Output**: `UserStyleRule` database records (queried by profile_name)

**Intelligence Scoring**: Triggers `score_research_run()` and `score_writer_run()` to compute quality metrics for intelligence loop distillation

---

## 3. Intelligence Loops (Self-Improvement)

### Research Intelligence Loop

**Purpose**: Distills successful research patterns into reusable playbooks

**Telemetry Capture** (`_capture_run_telemetry()`):
- Tool sequence used (keyword_ideas, serp, exa_scout, exa_extract)
- KD (keyword difficulty) stats
- Exa queries executed
- Semantic entity clusters discovered
- **Cost**: $0.00 (pure Python, no API calls)

**Playbook Recall** (`_get_niche_playbook()`):
- If ≥10 prior runs exist for `(profile_name, niche)`, fetches `NichePlaybook`
- Injects distilled playbook (~200 tokens) into R1's agentic prompt
- Guides tool selection without contaminating current research

**Reinforcement** (`score_research_run()`):
- Triggered on `/approve` after human edits
- Computes edit-distance ratio: `1.0 - (levenshtein(original, edited) / max_len)`
- Persisted as `quality_score` (0.0-1.0)

**Distillation** (`maybe_distill()`):
- Triggers at ≥10 undistilled runs
- **Heuristic Aggregation** (<5 quality runs): Averages tool patterns, entity clusters
- **DeepSeek-V3 Distillation** (≥5 runs with quality ≥0.20): Summarizes strategic patterns
- Result upserted to `NichePlaybook` table

**Storage**: `NichePlaybook` table with composite key `(profile_name, niche)`

---

### Writer Intelligence Loop

**Purpose**: Learns optimal readability patterns for each niche

**Telemetry Capture** (`WriterRun`):
- ARI (Automated Readability Index)
- FK (Flesch-Kincaid Grade Level)
- CLI (Coleman-Liau Index)
- Average sentence length
- Word count
- Automatically captured on every generation

**Playbook Recall** (`WriterPlaybook`):
- If ≥10 articles exist for `(profile_name, niche)`, fetches playbook
- Injects:
  - Niche ARI baseline (e.g., "Cybersecurity articles average ARI 9.2")
  - Target sentence length (e.g., "Aim for 11 words/sentence")
  - Structure patterns (e.g., "Use 6 H2s per 1,500 words")

**Reinforcement** (`score_writer_run()`):
- Computes readability efficiency: `(10.0 - ari) / 10.0` (higher = closer to 7th-10th grade target)
- Persisted as `efficiency_score` (0.0-1.0)

**Distillation**:
- Triggers at ≥10 undistilled runs with ≥5 efficiency ≥0.20
- Computes heuristic averages (median ARI, mean sentence length)
- Upserted to `WriterPlaybook` table

**Storage**: `WriterPlaybook` table with composite key `(profile_name, niche)`

---

## 4. Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **API Framework** | FastAPI 0.135.1 | REST endpoints + SSE streaming |
| **Database** | Neon PostgreSQL + SQLAlchemy 2.0 | Multi-tenant ORM with connection pooling |
| **Reasoning LLM** | GLM-5 (`glm-5`) / DeepSeek-R1 (`deepseek-reasoner`) | GLM-5: Phase 1 research, Phase 1.5 verification; DeepSeek-R1: Phase -1 cartographer |
| **Chat LLM** | DeepSeek-V3 (`deepseek-chat`) | Phase 0 briefing, Phase 2 psychology, Phase 6 feedback, intelligence distillation |
| **Writer LLM** | Claude Sonnet 4.5 (`claude-sonnet-4-5-20250929`) | Phase 3 article generation |
| **Research Tools** | Exa.ai + DataForSEO MCP | Web search (neural + SERP) + SEO intelligence (keywords, backlinks, on-page analysis) |
| **Streaming** | SSE (Server-Sent Events) | Real-time frontend updates |
| **Frontend** | Vanilla JS + Tailwind CSS | Cyber-glassmorphism console UI |
| **Container** | Uvicorn ASGI server | Async production runtime |
| **HTTP Client** | httpx (async) + Anthropic SDK | LLM API calls |
| **Validation** | Pydantic 2.12.5 | Request/response schemas |
| **MCP Framework** | Model Context Protocol (MCP) | DataForSEO tool integration |

---

## 5. Quickstart Guide

### Prerequisites

Ensure you have the following installed:
- [Python 3.10+](https://www.python.org/downloads/)
- [Git](https://git-scm.com/downloads)
- [Node.js / npm](https://nodejs.org/en/) (required for DataForSEO MCP server)

### Installation Steps

#### 1. Clone the Repository

```bash
git clone https://github.com/jordannewby/ares-engine.git
cd ares-engine
```

#### 2. Set Up Virtual Environment

```bash
python -m venv venv
```

**Activate the environment:**

**Windows:**
```powershell
.\venv\Scripts\activate
```

**Mac/Linux:**
```bash
source venv/bin/activate
```

#### 3. Install Python Dependencies

```bash
pip install -r requirements.txt
```

#### 4. Install DataForSEO MCP Server Dependencies

```bash
cd mcp-dataforseo-server
npm install
cd ..
```

#### 5. Create .env File

**CRITICAL**: The `.env` file holds sensitive API keys and is **gitignored**. You must create it manually.

Copy the template:
```bash
cp .env.example .env
```

Edit `.env` with your actual API keys (see [Section 6: Environment Variables](#6-environment-variables) for details).

#### 6. Start the Application

```bash
uvicorn app.main:app --reload
```

**Access Points:**
- Frontend UI: `http://127.0.0.1:8000/`
- API docs (Swagger): `http://127.0.0.1:8000/docs`
- Alternative docs (ReDoc): `http://127.0.0.1:8000/redoc`

#### 7. Verify Installation

1. Open `http://127.0.0.1:8000/` in your browser
2. You should see the Ares Console UI (cyber-glassmorphism design)
3. Check browser console (F12) for any errors
4. Navigate to `/health` endpoint to verify API connectivity

---

## 6. Environment Variables

Create a `.env` file in the project root with these required variables:

### Database

```env
DATABASE_URL="postgresql://user:password@host:5432/dbname?sslmode=require"
```

**Required**: Neon PostgreSQL connection string. Get yours at [neon.tech](https://neon.tech).

### LLM API Keys

```env
ANTHROPIC_API_KEY="sk-ant-api03-..."
```
**Required**: Claude Sonnet 4.5 for writing phase. Get yours at [console.anthropic.com](https://console.anthropic.com).

```env
DEEPSEEK_API_KEY="sk-..."
```
**Required**: DeepSeek-V3 for cartographer, briefing, psychology, feedback. Get yours at [platform.deepseek.com](https://platform.deepseek.com).

```env
ZAI_API_KEY="sk-..."
```
**Required**: GLM-5 for research and source verification. Get yours at [open.bigmodel.cn](https://open.bigmodel.cn).

### Search & Intelligence APIs

```env
EXA_API_KEY="..."
```
**Required**: Exa.ai neural search for source discovery. Get yours at [dashboard.exa.ai](https://dashboard.exa.ai).

```env
DATAFORSEO_LOGIN="your-email@example.com"
DATAFORSEO_PASSWORD="your-password"
```
**Required**: DataForSEO credentials for SERP/keyword/backlink tools. Register at [app.dataforseo.com](https://app.dataforseo.com).

### Admin

```env
ADMIN_SECRET="your-admin-secret"
```
**Required for API key management**: Used to authenticate `POST /admin/api-keys` requests via the `X-Admin-Secret` header. Generate a strong random value (e.g., `python -c "import secrets; print(secrets.token_urlsafe(32))"`).

### Optional

```env
ARES_DEBUG=true
```
**Optional**: Enable debug mode for verbose logging.

```env
DATAFORSEO_CONTENT_ANALYSIS_ENABLED=true
```
**Optional**: Enable DataForSEO on-page analysis feature flag.

---

## 7. Configuration (app/settings.py)

The application uses centralized operational constants in `app/settings.py`. Key configurations:

### Model Constants

```python
CLAUDE_MODEL = "claude-sonnet-4-5-20250929"
DEEPSEEK_MODEL = "deepseek-chat"  # DeepSeek-V3
DEEPSEEK_REASONER_MODEL = "deepseek-reasoner"  # DeepSeek-R1
GLM5_MODEL = "glm-5"  # GLM-5 Deep Thinking
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
SOURCE_CREDIBILITY_THRESHOLD = 45.0   # Min score to pass (0-100 scale)
SOURCE_THRESHOLD_DECAY = 5.0          # Lower threshold on retries
MAX_VERIFICATION_ITERATIONS = 3       # Iterative backfill attempts
```

### Claim Verification

```python
MAX_EXA_FACT_CHECKS = 15
MAX_LLM_VERIFICATIONS = 10
CLAIM_TEXT_SIMILARITY_THRESHOLD = 0.45
LLM_SOURCE_CONTEXT_CHARS = 5000
MAX_UNCITED_CLAIMS = 2                # Max uncited claims before gate fails
MAX_UNGROUNDED_RATIO = 0.15          # Max fraction of claims allowed ungrounded (15%)
MAX_CLAIM_RETRIES = 2                 # Writer retries on claim gate failure
```

### Penalties

```python
BLOG_DOMAIN_PENALTY = 10.0            # Points deducted for blog.* subdomains
BLOG_PATH_PENALTY = 5.0               # Points deducted for /blog/ in URL
UNSOURCED_CLAIMS_PENALTY = 15.0       # Low-credibility domain claims penalty
```

---

## 8. Database Schema

Ares Engine uses **Neon PostgreSQL** (serverless). Tables are created automatically via 15 migrations in `app/database.py`.

### Core Models

#### Post
```python
id: int (PK)
keyword: str
profile_name: str
niche: str
original_ai_content: str          # Claude's initial draft
human_edited_content: str | None  # User's refined version
readability_scores: dict | None   # ARI, FK, CLI, sentence length
created_at: datetime
```

Stores generated articles with readability analytics.

#### UserStyleRule
```python
id: int (PK)
profile_name: str
rule_type: str  # vocabulary_preference, structure_preference, tone_preference
pattern: str    # Original phrase
replacement: str  # Preferred replacement
created_at: datetime
```

Learned writing preferences extracted by FeedbackAgent (Phase 6).

#### ResearchCache
```python
keyword: str (composite PK)
profile_name: str (composite PK)
niche: str (composite PK)
data: dict  # Research dict from Phase 1
created_at: datetime
```

Caches research results for 24h to reduce API costs.

#### ResearchRun
```python
id: int (PK)
profile_name: str
niche: str
tool_sequence: list[str]  # e.g., ["keyword_ideas", "serp", "exa_scout"]
kd_stats: dict | None
exa_queries: list[str]
entity_clusters: list[str]
quality_score: float | None  # 0.0-1.0 from human edits
is_distilled: bool
created_at: datetime
```

Telemetry for Research Intelligence Loop.

#### NichePlaybook
```python
profile_name: str (composite PK)
niche: str (composite PK)
playbook_data: dict  # Distilled research patterns
source_run_count: int
distilled_at: datetime
```

Distilled research strategies (≥10 runs).

#### WriterRun
```python
id: int (PK)
profile_name: str
niche: str
ari: float
flesch_kincaid: float
coleman_liau: float
avg_sentence_length: float
word_count: int
efficiency_score: float | None  # (10.0 - ari) / 10.0
is_distilled: bool
created_at: datetime
```

Telemetry for Writer Intelligence Loop.

#### WriterPlaybook
```python
profile_name: str (composite PK)
niche: str (composite PK)
playbook_data: dict  # Distilled readability patterns
source_run_count: int
distilled_at: datetime
```

Distilled readability patterns (≥10 articles).

#### VerifiedSource
```python
id: int (PK)
research_run_id: int (FK)
source_url: str
domain: str
tier: int  # 0-4 (domain credibility tier)
composite_score: float  # 0-100 credibility score
verification_status: str  # verified, rejected, pending
published_date: datetime | None
```

Sources scored in Phase 1.5. Unique constraint: `(research_run_id, source_url)`.

#### FactCitation
```python
id: int (PK)
source_id: int (FK to VerifiedSource)
fact_text: str
fact_type: str  # statistic, benchmark, case_study, expert_quote
citation_anchor: str  # e.g., "according to Gartner"
original_source: str  # Named study/report
confidence: float  # 0.0-1.0
is_verified: bool
verification_status: str  # corroborated, trusted, exa_verified, not_checked
```

Extracted facts linked to verified sources.

#### DomainCredibilityCache
```python
domain: str (composite PK)
niche: str (composite PK)
tier: int
composite_score: float
cached_at: datetime
```

90-day cache for domain credibility scores (reduces DeepSeek calls by 40%).

#### ContentCampaign
```python
id: int (PK)
profile_name: str
pillar_keyword: str
spoke_keywords: list[dict]  # [{keyword, intent, angle}, ...]
created_at: datetime
```

Hub-and-spoke keyword mappings from Cartographer (Phase -1).

#### Workspace
```python
id: int (PK)
name: str
slug: str
profile_name: str
# Unique constraint: (slug, profile_name)
```

Multi-tenant workspace definitions scoped to authenticated profile.

---

## 9. API Endpoints

All endpoints except `/health` and `/` require `X-API-Key` header authentication.

| Endpoint | Method | Auth | Rate Limit | Purpose |
|----------|--------|------|------------|---------|
| **`/generate/{keyword:path}`** | POST | API Key | 5/min, 50/day | **Main orchestration** — full 7-phase pipeline. SSE stream |
| **`/research/{keyword:path}`** | GET | API Key | 10/min | Phase 1 only — direct research endpoint |
| **`/clarify`** | GET | API Key | - | Phase 0 — 3 clarifying questions |
| **`/blueprint`** | POST | API Key | - | Phase 2 only — psychology blueprint |
| **`/posts`** | GET | API Key | - | List articles (profile-scoped) |
| **`/posts/{post_id}`** | GET | API Key | - | Fetch specific article (profile-scoped) |
| **`/posts`** | POST | API Key | - | Create article manually |
| **`/posts/{post_id}/approve`** | POST | API Key | - | Approve edits, trigger FeedbackAgent + scoring |
| **`/rules`** | GET | API Key | - | Fetch style rules (profile-scoped) |
| **`/rules`** | POST | API Key | - | Add style rule (max 25 per profile) |
| **`/rules/{rule_id}`** | DELETE | API Key | - | Delete style rule (ownership verified) |
| **`/workspaces`** | GET | API Key | - | List workspaces (profile-scoped) |
| **`/workspaces`** | POST | API Key | - | Create workspace (profile-scoped) |
| **`/campaigns`** | GET | API Key | - | Fetch campaigns (profile-scoped) |
| **`/campaigns/plan`** | POST | API Key | 10/min | Cartographer hub-and-spoke planning |
| **`/settings`** | GET | API Key | - | Fetch profile settings |
| **`/settings`** | PUT | API Key | - | Update profile settings |
| **`/admin/api-keys`** | POST | Admin Secret | - | Create new API key (X-Admin-Secret header) |
| **`/health`** | GET | None | - | System status check |
| **`/`** | GET | None | - | Serves frontend UI |

---

## 10. Frontend UI

### Cyber-Glassmorphism Design

The frontend (`static/ares_console.html` + `static/js/console.js`) features a **cyberpunk-inspired glassmorphic interface** with real-time agent visualization.

### Key Components

#### Editor Pane
- Real-time markdown editor with syntax highlighting
- Live SEO audit scoring (mirrors backend `verify_seo_score()` gates)
- Word count, H2 count, citation count indicators
- "Approve" button triggers `/approve` endpoint

#### Blueprint Pane
- Displays psychology outline from Phase 2
- Hook strategy, target identity, agitation points
- Outline structure with H2/H3 hierarchy
- Collapsible sections for clean viewing

#### Terminal
- Structured logs from all agents
- Phase progression indicators (Research → Verify → Psychology → Writer)
- Source verification scores with color-coding:
  - Green (≥70): High credibility
  - Yellow (45-69): Moderate credibility
  - Red (<45): Rejected
- Iteration feedback (gate failures with specific fix instructions)

#### Agent Nodes
- Visual indicators of active phase
- Glowing effect on current agent
- Progress dots showing iteration count

#### Modal System
- **Workspace Selector**: Switch between profiles
- **Workspace Creator**: Add new workspace
- **AI Brain**: Manage style rules (view, add, delete)
- **Cartographer**: Campaign planner with spoke generation confirmation
- **Clarification Questions**: Phase 0 modal (3 questions)

#### Mobile Toast
- Agent status indicator for mobile users
- Shows current phase + iteration count

### State Management

**Global Abort Controller**: Cancels in-flight SSE streams before new generation

**State Clearing**: Frontend clears these before each generation:
- `lastGeneratedMarkdown`
- `currentPostId`
- `currentQuestions`
- Editor content
- Blueprint pane

**No Native Dialogs**: Uses custom `showConfirmModal(message, onConfirm)` instead of `window.confirm()` for better UX

---

## 11. Cost Breakdown

### External Services

| Service | Purpose | Cost per Article | Required | Model/Version |
|---------|---------|------------------|----------|---------------|
| **Anthropic** | Writer phase prose generation | ~$0.05 | Yes | Claude Sonnet 4.5-20250929 |
| **GLM-5** | Research, Source verification | ~$0.06 | Yes | glm-5 via ZhipuAI API |
| **DeepSeek** | Cartographer (R1), Briefing (V3), Psychology (V3), Feedback (V3) | ~$0.02 | Yes | deepseek-chat (V3), deepseek-reasoner (R1) |
| **Exa.ai** | Neural search source discovery | ~$0.01 | Yes | scout_search, extract_full_text |
| **DataForSEO** | SERP/keywords/backlinks/on-page (via MCP) | ~$0.02 | Yes | SERP ($0.02), Keyword Ideas ($0.0001), Backlinks ($0.00), On-Page ($0.00125 for 10 competitors) |
| **Neon PostgreSQL** | Database (serverless) | Free tier: 3GB storage, $7/month for more | Yes | PostgreSQL 15 |

### Budget Planning

**Total Cost per Article**: $0.15-0.30 (varies by research depth, iteration count)

**$10/Month Budget**:
- **Low estimate**: 35 articles (at $0.30 each)
- **High estimate**: 65 articles (at $0.15 each)
- **Average**: ~50 articles

### Cost Optimization Strategies

1. **Research Caching** (`CACHE_TTL_HOURS = 24`): Reuse research results within 24h window
2. **Domain Credibility Cache** (90-day TTL): Reduces DeepSeek calls by 40%
3. **Playbook Distillation** (≥10 articles): Reduces intelligence injection tokens
4. **Exa Result Limits** (`EXA_NUM_RESULTS = 10`): Caps per-search costs
5. **Agentic Loop Limits** (`MAX_AGENTIC_ITERATIONS = 5`): Prevents runaway R1 reasoning
6. **Writer Retry Limits** (`MAX_WRITER_ATTEMPTS = 5`): Caps iteration costs

---

## 12. Security

Ares Engine implements defense-in-depth across authentication, prompt injection, rate limiting, and frontend hardening. Audited against OWASP Agentic Top 10 (2026), OWASP Web Top 10, and ASVS v4.0.

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
| `sanitize_external_content()` | Strips HTML comments + control chars, truncates (no boundary tags) | External/LLM-derived data (Exa content, style rules, claim feedback, psychology directives, web content) |

**Coverage** — sanitization applied at every LLM prompt boundary:
- `research_service.py` — keyword, user_context, niche playbook, Exa tool results
- `briefing_agent.py` — keyword, niche
- `cartographer_service.py` — seed_topic, niche_context
- `writer_agent_graph.py` — style rules, citation text, psychology directives
- `writer_service.py` — style rule descriptions, claim feedback
- `feedback_service.py` — original and edited article text
- `source_verification_service.py` — web content in quality/integrity assessments
- `psychology_agent.py` — research JSON data

**Input length bounds** (Pydantic `Field(max_length=...)` at API boundary + truncation before LLM injection):
- `MAX_USER_CONTEXT_CHARS=2000`, `MAX_STYLE_RULES_CHARS=1500`, `MAX_RESEARCH_JSON_CHARS=6000`, `MAX_PLAYBOOK_CHARS=1500`

### Rate Limiting & Abuse Prevention

- **Per-endpoint rate limits** — `slowapi`: `/generate` (5/min), `/research` (10/min), `/campaigns/plan` (10/min); keyed by API key hash
- **Daily generation cap** — `MAX_DAILY_GENERATIONS=50` per profile per day
- **Style rule cap** — `MAX_STYLE_RULES_PER_PROFILE=25` prevents unbounded memory accumulation
- **Agentic loop limits** — `MAX_AGENTIC_ITERATIONS=5`, `MAX_WRITER_ATTEMPTS=5` cap per-request cost

### Security Headers

`SecurityHeadersMiddleware` adds to all responses:
- `Strict-Transport-Security: max-age=63072000; includeSubDomains` (HSTS)
- `Content-Security-Policy` (default-src 'self', restricted script/style/font/connect sources)
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy: camera=(), microphone=(), geolocation=()`

### Frontend Security

- **XSS prevention** — All `innerHTML` assignments wrapped in `DOMPurify.sanitize()`
- **Markdown rendering** — `marked.parse()` output sanitized via DOMPurify before DOM insertion
- **SRI hashes** — Third-party scripts (marked.js, DOMPurify) loaded with Subresource Integrity
- **Error isolation** — SSE error events send generic messages only; stack traces never reach the client

### Secrets Management

**Environment variables only** — All API keys loaded via `os.getenv()` in `app/settings.py`:
- `ANTHROPIC_API_KEY`, `DEEPSEEK_API_KEY`, `EXA_API_KEY`, `ZAI_API_KEY`
- `DATAFORSEO_LOGIN`, `DATAFORSEO_PASSWORD`
- `DATABASE_URL`, `ADMIN_SECRET`
- Validated at startup — server refuses to start if critical keys are missing

**Never commit secrets**:
- `.env` is gitignored; use `.env.example` as template
- If keys are accidentally exposed, rotate immediately at provider dashboards

**Verify before commit**:
```bash
git check-ignore .env  # Should output: .env
git status             # Should NOT show .env in untracked files
```

---

## 13. Troubleshooting

### Common Setup Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| `DEEPSEEK_API_KEY is missing` | `.env` not loaded or key missing | Verify `.env` exists in project root with `DEEPSEEK_API_KEY="..."` |
| `DATABASE_URL environment variable is required` | PostgreSQL connection string missing | Add `DATABASE_URL="postgresql://..."` to `.env` |
| `ModuleNotFoundError: No module named 'anthropic'` | Dependencies not installed | Run `pip install -r requirements.txt` |
| MCP server fails to start | Node.js not installed or DataForSEO credentials wrong | Install Node.js, verify `DATAFORSEO_LOGIN` and `DATAFORSEO_PASSWORD` in `.env` |
| "0/47 sources verified" error | Metadata extraction failure (legacy issue) | Ensure `url_metadata_map` is preserved (March 2026 fix already in code) |
| Emoji in logs crashes (Windows) | cp1252 encoding doesn't support emoji | Use `[LABEL]` ASCII prefixes instead (already enforced in codebase) |
| Articles stuck in validation loops | Readability gate too strict | Tune `WRITER_MAX_TOKENS`, verify citation map is provided if Phase 1.5 completed |
| SSE stream disconnects mid-generation | Neon PostgreSQL SSL timeout | `nonlocal db` pattern already implemented (March 2026 fix) |
| Writer produces fabricated citations | Citation map not injected | Verify Phase 1.5 completed (check `verified_sources` table) |
| High API costs | Research loop running too many iterations | Lower `MAX_AGENTIC_ITERATIONS`, enable `CACHE_TTL_HOURS` |

### Debugging Tips

**Enable Debug Mode**:
```env
ARES_DEBUG=true
```

**Check Frontend Console** (F12):
- SSE events show real-time agent execution
- `phase1_start`, `source_verification`, `content`, `debug`, `error` events
- Error events display generic messages (details in backend logs only)

**Check Backend Logs**:
```bash
uvicorn app.main:app --log-level debug
```

Look for structured log prefixes:
- `[ARES]` — General system messages
- `[SCORE]` — Source credibility scoring
- `[RESCUED]` — Borderline sources with rescue bonus
- `[DEDUP]` — Duplicate source filtering
- `[GATE]` — Writer validation gates
- `[CLAIM-VERIFY]` — Claim cross-referencing

**Database Inspection**:
```bash
# Connect to Neon PostgreSQL
psql $DATABASE_URL

# Check recent research runs
SELECT profile_name, niche, tool_sequence, quality_score FROM research_runs ORDER BY created_at DESC LIMIT 10;

# Check verified sources for a run
SELECT source_url, tier, composite_score, verification_status FROM verified_sources WHERE research_run_id = 123;

# Check extracted facts
SELECT fact_text, fact_type, confidence, verification_status FROM fact_citations WHERE source_id IN (SELECT id FROM verified_sources WHERE research_run_id = 123);
```

---

## 14. Development Notes

All development rules, security constraints, and architecture conventions are documented in `CLAUDE.md` (project root). Key highlights:

- **Async mandatory** — All HTTP clients + LLM calls must use async/await
- **Multi-tenant isolation** — All DB queries filter by `profile_name`
- **Prompt injection defense** — All LLM prompt boundaries must use `sanitize_prompt_input()` or `sanitize_external_content()`
- **Centralized config** — All constants in `app/settings.py`; never hardcode values in services
- **Prompt files read-only** — Never modify `app/services/prompts/*.md` without explicit approval

For detailed phase diagrams, scoring algorithms, and intelligence loop mechanics, see `docs/architecture.md`.

