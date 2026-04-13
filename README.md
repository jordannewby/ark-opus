<p align="center">
  <img src="static/ark%20opus%20thumbnail.png" alt="Ark Opus" width="100%"/>
</p>

# Ark Opus

**Multi-agent autonomous AI orchestration engine for verified content generation.**

An autonomous multi-agent content engine that doesn't trust itself.

Every factual claim, every citation URL, every statistic in the final article has been independently verified against real source material before the system will save it. Not by one check — by a redundant chain of verification gates where each layer assumes the previous one failed.

---

## Why This Exists

AI writing tools have a credibility problem. They generate confident prose backed by sources that don't exist, statistics nobody published, and URLs that 404. Teams spend more time fact-checking the AI than they saved using it.

The root cause isn't model quality. It's architecture. A single-pass generation pipeline will always hallucinate because there's nothing structurally preventing it from doing so.

Ark Opus makes it structurally impossible. The article cannot be saved until every claim survives a multi-agent verification gauntlet. Fabricate a URL? Caught. Attribute a study to the wrong organization? Caught. Invent a statistic? Caught and rejected.

---

## What Happens When You Hit Generate

Seven autonomous phases fire in sequence. Each one streams progress in real time.

**Campaign Intelligence** — An AI cartographer analyzes hundreds of keywords from live SEO data and maps them into a hub-and-spoke content strategy. One pillar, up to ten supporting articles, all clustered by topical authority.

**Briefing** — Before any research begins, the system asks you three targeted clarifying questions. Your answers shape the entire pipeline — audience, angle, depth.

**Agentic Research** — A reasoning model autonomously orchestrates search APIs and neural retrieval tools in an iterative loop. It decides which tools to call, evaluates results, and re-queries when coverage is insufficient. It doesn't follow a script — it adapts.

**Source Verification** — Every source is scored across seven credibility factors: content integrity, editorial quality, domain authority, freshness, author attribution, topical relevance, and spam detection. Sources below threshold are rejected. Borderline sources get a secondary rescue evaluation. The system will refuse to generate if fewer than three credible sources survive.

**Fact Grounding** — Extracted facts are verified against actual source page content. Cross-source corroboration checks whether independent sources confirm the same claims. Primary source tracing follows citation chains back to the original publisher when laundering is detected. Version currency checks flag outdated statistics.

**Psychology + Writing** — A persuasion blueprint maps the target audience's psychology before writing begins. The writer operates in a triple-gated loop: SEO structure validation, citation accuracy enforcement, and readability scoring. It rewrites until all three gates pass simultaneously. Banned-word sanitization runs deterministically after every draft — the system doesn't rely on prompt instructions alone.

**Claim Verification Gate** — After the article is fully written, every claim-citation pair is extracted and cross-referenced against the verified fact database. URLs not in the verified source map are flagged as fabricated. Domain-only URL matches (where the model guessed a plausible path) are treated as fabricated, not ambiguous. Zero tolerance. The article rewrites until clean.

**Final URL Gate** — A last-resort regex scan strips any URL that survived all previous checks but still isn't in the verified source set. Defense in depth.

---

## Self-Improving Intelligence

The system gets better the more you use it.

**Research playbooks** distill successful tool sequences, keyword difficulty patterns, and entity clusters across runs. After enough articles in a niche, the research agent stops exploring blindly and starts executing proven strategies.

**Writer playbooks** track which sentence structures, word choices, and readability patterns consistently hit target scores. The writer's prompt evolves per-niche.

**Style rules** learn from your edits. When you modify an article and approve it, the system diffs your changes, extracts style preferences, and applies them to every future generation. Your voice compounds over time.

---

## The Verification Stack

This isn't one check. It's seven layers, each assuming the previous one was compromised:

1. **Exa Research API** instructions demand original publisher URLs, not aggregator blogs
2. **Citation laundering detection** catches when "Organization X reports Y" but the URL points to a third party
3. **Original source tracing** searches the actual publisher's domain to find the real URL
4. **URL liveness validation** confirms every source URL is alive before it enters the writer's pool
5. **Editor allowlist** rejects any URL the writer generates that isn't in the verified citation set
6. **Post-write claim cross-referencing** extracts every claim and matches it against source facts
7. **Final URL gate** strips anything that slipped through

A fabricated URL would need to independently fool all seven layers. Each layer uses a different detection mechanism.

---

## Multi-Tenant Workspaces

Everything is scoped by profile. Research caches, style rules, playbooks, generation history — all isolated per workspace. Run ten different content brands from one instance without bleed.

---

## Quick Start

```bash
git clone <your-repo-url>
cd ark-opus

python -m venv venv
# Windows: .\venv\Scripts\activate
# Mac/Linux: source venv/bin/activate

pip install -r requirements.txt
cd mcp-dataforseo-server && npm install && cd ..

cp .env.example .env
# Fill in your API keys (see .env.example for the full list)

cp hooks/pre-commit .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit

uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/` to access the console.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| API | FastAPI (async, SSE streaming) |
| Database | PostgreSQL (SQLAlchemy ORM) |
| LLMs | Multiple models — reasoning, writing, analysis |
| Search | Neural search + SEO intelligence APIs |
| Frontend | Vanilla JS + Tailwind CSS |
| Validation | Pydantic schema enforcement at every boundary |

---

## Cost

Roughly **$1.00 - $2.50 per article** in API costs. Built-in caching drops that significantly after the first few runs in a niche.

---

## License

This project is proprietary software. All rights reserved.

You may view the source code for reference purposes only. No permission is granted to use, copy, modify, merge, publish, distribute, sublicense, or sell copies of this software without explicit written permission from the author.

For licensing inquiries, contact the repository owner.
