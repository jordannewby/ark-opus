# Ark Opus

An AI content pipeline that researches, verifies, and writes long-form articles with automated citation checking. Every factual claim is cross-referenced against verified sources before the article is saved.

---

## The Problem

AI content tools generate fluent prose but leave fact-checking to the user. They invent URLs that 404. They attribute studies to organizations that never published them. They hallucinate statistics that sound plausible but have no source.

Editorial teams end up spending more time fact-checking AI output than they saved by using it. The trust problem isn't a model quality problem — it's an architecture problem. No amount of prompt engineering prevents a model from inventing a URL it has never seen.

Ark Opus makes verification a structural requirement, not an optional step. Articles can't be saved until claims pass a multi-gate verification pipeline.

---

## What It Does

**Post-Write Claim Verification** — After the article is generated, every factual claim is extracted and matched against the verified fact database. Fabricated citations (URLs not in the verified source map) trigger an automatic rewrite. Zero tolerance.

**Source Credibility Scoring** — Before any source enters the writer's citation pool, it's scored across multiple factors including content integrity, domain authority, freshness, and topical relevance. Sources below threshold are rejected.

**Citation Laundering Detection** — When an article claims "Organization X reports Y" but the citation URL points to a blog that aggregated the data, the system detects the mismatch and flags it.

**Self-Improving Intelligence Loops** — After enough articles in a niche, the system distills successful research and readability patterns into playbooks. Human edit feedback trains per-profile style rules that persist across sessions.

---

## How It Works

```
Keyword + Niche
       |
       v
[Campaign Planning] ── Keyword clustering into hub-and-spoke content strategy
       |
       v
[Briefing] ─────────── Clarifying questions to refine intent and audience
       |
       v
[Research] ─────────── Agentic tool orchestration across search and SEO APIs
       |
       v
[Source Verification] ─ Credibility scoring, fact extraction, citation laundering detection
       |
       v
[Fact Grounding] ───── Verifies extracted facts against actual source page content,
       |                cross-source corroboration, primary source tracing
       |
       v
[Psychology] ────────── Persuasion blueprint (audience targeting, emotional hooks)
       |
       v
[Writer] ───────────── Article generation with triple-gate validation:
       |                SEO structure, citation accuracy, readability scoring
       |
       v
[Claim Gate] ────────── Post-write claim cross-referencing (zero-tolerance on fabrication)
       |
       v
[Feedback] ─────────── Learns from human edits, improves future generations
```

Each phase streams progress events in real time via SSE so you can watch the pipeline work.

---

## Quick Start

### Prerequisites

- Python 3.10+
- Git
- Node.js / npm

### Installation

```bash
# Clone and set up
git clone <your-repo-url>
cd ark-opus

# Python environment
python -m venv venv
# Windows:
.\venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# MCP server dependencies
cd mcp-dataforseo-server && npm install && cd ..

# Configure environment
cp .env.example .env
# Edit .env with your API keys (see .env.example for required keys)

# Install pre-commit hook
cp hooks/pre-commit .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit

# Start the application
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/` to access the console UI.

### Environment Setup

Copy `.env.example` to `.env` and fill in your API keys. The application requires credentials for its database, LLM providers, and search APIs. See the example file for the full list — never commit `.env` to version control.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| API | FastAPI (async, SSE streaming) |
| Database | PostgreSQL (SQLAlchemy ORM) |
| LLMs | Multiple models for research, writing, and analysis |
| Search | Neural search + SEO intelligence APIs |
| Frontend | Vanilla JS + Tailwind CSS |
| Validation | Pydantic schema enforcement |

---

## Cost

Roughly **$1.00 - $2.50 per article** in API costs, depending on research depth and retry count. Built-in caching (research results, domain credibility) reduces costs significantly after the first few runs in a niche.

---

## Frontend

The console UI features a real-time agent visualization with:

- **Editor** — Live markdown editor with SEO audit scoring, word/heading/citation counts, and an approval button for the feedback loop
- **Blueprint** — Displays the psychology outline (hook strategy, audience targeting, content structure)
- **Terminal** — Structured logs from all pipeline phases with color-coded source verification scores
- **Modals** — Workspace management, style rule editor (AI Brain), campaign planner (Cartographer), and clarification questions

---

## Troubleshooting

Enable debug mode for verbose logging:

```bash
ARK_DEBUG=true uvicorn app.main:app --log-level debug
```

Common issues are usually one of: missing environment variables (check `.env`), missing dependencies (`pip install -r requirements.txt`), or MCP server not starting (verify Node.js is installed). The frontend console (F12) shows real-time SSE events for diagnosing pipeline issues.

---

## License

This project is proprietary software. All rights reserved.

You may view the source code for reference purposes only. No permission is granted to use, copy, modify, merge, publish, distribute, sublicense, or sell copies of this software without explicit written permission from the author.

For licensing inquiries, contact the repository owner.
