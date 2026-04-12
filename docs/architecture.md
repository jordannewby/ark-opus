# Ark Opus — Architecture Reference

Load this file when working on pipeline logic, agent behavior, or the workspace system: `@docs/architecture.md`

---

## Pipeline Overview (7 Phases)

### Phase -1 — CartographerAgent (`app/services/cartographer_service.py`)
- **Model**: `deepseek-reasoner` (DeepSeek-R1)
- **Trigger**: `/campaigns/plan` endpoint via the Cartographer UI
- **Logic**: Fetches top 700 keyword ideas from DataForSEO, sends compressed schema (keyword + search_volume + keyword_difficulty only) to DeepSeek-R1 to map Hub-and-Spoke structure, and saves result strictly as JSON to database. User inputs (`seed_topic`, `niche_context`) sanitized via `sanitize_prompt_input()` before prompt injection.
- **Output**: Persists a `ContentCampaign` containing 1 Pillar and up to 10 Spoke keywords, output via `/campaigns` to the UI.

### Phase 0 — BriefingAgent (`app/services/briefing_agent.py`)
- **Model**: `deepseek-chat` (DeepSeek-V3)
- **Trigger**: `/clarify` endpoint before the main `/generate` call
- **Logic**: Evaluates the user's Keyword + free-form Niche input, asks exactly 3 targeted clarifying questions via a custom frontend modal
- **Output**: User answers injected into Phase 1 as additional context

### Phase 1 — ResearchAgent (`app/services/research_service.py`)
- **Models**: `glm-5` (GLM-5 Deep Thinking) via ZhipuAI API for agentic tool decisions
- **Tools**: DataForSEO MCP server + Native Exa.ai tools (`exa_scout_search`, `exa_extract_full_text`)
- **Exa.ai Domain Quality Filters**: Defense-in-depth source credibility filtering. `exa_scout_search` now accepts `include_domains`, `exclude_domains`, `start_published_date`, and `num_results` (increased to 10 from 5) parameters. `EXA_INCLUDE_DOMAINS` dict defines **9 niche categories** with comprehensive domain coverage: (1) **general** (.edu, .gov, nature.com, science.org), (2) **cybersecurity** (50 domains: all Tier 1-3 from domain_tiers.py — government standards, security vendors, expert blogs, publications), (3) **ai** (22 domains: AI labs, academic institutions, conferences), (4) **blueteam** (31 domains: detection engineering, EDR/SIEM/XDR vendors, open source tools like wazuh.com, zeek.org, suricata.io, osquery.io), (5) **redteam** (18 domains: offensive security, bug bounty platforms like hackerone.com, bugcrowd.com, vulnerability databases), (6) **purple-team** (17 domains: simulation platforms like attackiq.com, scythe.io, ATT&CK framework, detection engineering), (7) **grc** (17 domains: standards bodies, Big 4 consulting, privacy/compliance orgs), (8) **networking** (15 domains: standards bodies, vendors, cloud providers), (9) **compliance** (22 domains: data protection authorities like gdpr.eu, ico.org.uk, edps.europa.eu, cnil.fr, privacy organizations like iapp.org, eff.org). `_build_agentic_prompt()`, `_exa_elite_discovery()`, and `niche_filtered_backfill()` all use shared `_get_niche_include_domains()` helper method (lines 697-737) — single source of truth for niche→domain mapping with **30+ aliases** (e.g., "blue-team"→blueteam, "infosec"→cybersecurity, "data-compliance"→compliance, "privacy"→compliance, "gdpr"→compliance). **Unrecognized niches** fall back to `None` (no `include_domains` restriction — Exa searches broadly across all domains) instead of restricting to .edu/.gov, relying on Phase 1.5 scoring as the quality gate. Excludes low-quality domains (medium.com, blogspot.com, wordpress.com, etc.) automatically. Enforces 2-year recency filter (`start_published_date`). **Agentic loop argument passthrough** (March 2026 bugfix): GLM-5's `exa_scout_search` tool calls now pass all filter arguments (`include_domains`, `exclude_domains`, `start_published_date`, `num_results`) through to the actual API call — was previously only passing `query`, silently discarding filters.
- **Exa Metadata Preservation** (March 2026): All Exa search functions now use `url_metadata_map` pattern to preserve `publishedDate` + `score` from search step through extract step. Search results stored as `{url: {score, published_date}}` dict, then merged into extract results by URL key. Fixes 20pts of lost scoring (Freshness 15pts + Relevance 5pts). Implemented in `_exa_elite_discovery()`, `backfill_search()`, `niche_filtered_backfill()`, and agentic loop `exa_scout_search` → `exa_extract_full_text` merge using `exa_score_map`.
- **Agentic Logic**: GLM-5 runs in an **iterative loop** (max 5 iterations). It autonomously orchestrates both MCP tools (Keyword Ideas, Live SERP, etc.) and native Exa tools to scout and extract full article bodies (truncated to 20,000 chars for context safety). The agentic prompt uses a **3-step sequencing pattern** to prevent GLM-5 from skipping tools: Step 1 provides a literal JSON example of mandatory tool calls (keyword_ideas + SERP) pre-filled with the target keyword; Step 2 lists strategic tools (Exa scout/extract with quality filters, backlinks, on_page, related keywords); Step 3 defines the final output format — placed last so GLM-5 doesn't fill it in prematurely. A `CRITICAL` preamble enforces tool-calling before any final analysis. Debug logging (`[DEBUG] GLM-5 raw response`) prints the first 500 chars of each response to diagnose tool-skipping.
- **Niche Playbook Injection**: Before the agentic loop, `_get_niche_playbook()` retrieves distilled or heuristic intelligence for the current `(profile_name, niche)` and injects it into GLM-5's prompt (~200 extra tokens) wrapped in `<niche_playbook>` XML tags. A **CRITICAL INSTRUCTION** explicitly directs GLM-5 to use the playbook ONLY for strategic patterns (tool sequence, KD thresholds, audience insights) and NOT to research past topics mentioned within. Omitted entirely on cold start.
- **Keyword Relevance Scoring** (March 2026): `_keyword_relevance_score()` helper tokenizes slug-style keywords on hyphens (e.g., `"ai-observability-platforms"` → `{"ai", "observability", "platforms"}`), drops tokens <3 chars, then checks each result's title + first 500 chars of content for token matches. Requires majority match: `min_match = max(1, min(2, len(tokens)))` — for 1-token keywords need 1, for 2-token need both, for 3+ need 2. Used in three places: (1) `research()` supplement trigger — fires when `relevant_count < 3` even if total sources ≥5, (2) `_exa_elite_discovery()` unfiltered fallback — when niche-filtered results are mostly off-topic, retries WITHOUT `include_domains` and deduplicates by URL, (3) broad `backfill_search()` — last resort if relevance still <3 after elite discovery. This fixes the "off-topic sources" problem where niche domain filters (e.g., AI niche returning general deepmind.com articles) produced sources that score well on credibility but don't cover the specific keyword topic.
- **MCP Rate-Limit Retry** (March 2026): All `session.call_tool()` MCP calls wrapped with `mcp_call_with_retry()` helper (exponential backoff: 1s→2s→4s, max 3 retries). Catches 429 / "rate limit" / "too many requests" errors from DataForSEO. Non-429 errors pass through immediately. Applied to all 4 MCP call sites: agentic loop tool execution, fallback keyword_ideas, fallback SERP, and content analysis.
- **Fallback / Safety**: Circuit breaker forces output at 5 iterations. Hallucinated tools return a simulated error to allow GLM-5 to self-correct. **Elite discovery supplement** (March 2026): When R1 finds <5 sources OR <3 keyword-relevant sources, `_exa_elite_discovery()` supplement fires with URL deduplication to avoid duplicates. Uses normalized `niche` variable (earlier bugfix: was passing undefined `niche_context`). **Exa metadata propagation**: `url_metadata_map` in all Exa functions and `exa_score_map` in agentic loop preserve both `publishedDate` and `score` from search results, merging them into extract results by URL. Critical for Phase 1.5 scoring: Freshness (15pts) and Topical Relevance (5pts).
- **Opportunity Score Algorithm**: Filters semantic entities by Volume, CPC, KD — discards any keyword with KD > 65
- **Expanded Output**: GLM-5 returns an expanded dict with keys: `information_gap` (string), `unique_angles` (list), `competitor_weaknesses` (list), `data_points` (list), `practitioner_insights` (list). Legacy string format still supported via fallback. String responses auto-parsed via `json.loads` in case GLM-5 returns stringified JSON. On-page metrics and backlink authority extracted from real MCP tool results (no hardcoded placeholders). All fields unpacked into the top-level result dict for downstream consumption by PsychologyAgent and WriterService.
- **Telemetry Capture**: After each run, `_capture_run_telemetry()` stores tool sequence, KD stats, Exa queries, entity clusters, and info gap into `ResearchRun`. Triggers distillation check.
- **Noise filter**: `_strip_webhook_noise` removes large DataForSEO webhook payloads from MCP schemas before passing to R1
- **Cache Strategy**: ResearchCache enforces strict multi-tenant isolation via composite unique constraint `(keyword, profile_name, niche)`. Cache lookups require exact match on all three fields. Existing entries are checked for expiration (default 24h TTL) and deleted if stale. Migration adds `profile_name` and `niche` columns to legacy cache entries with `'default'` values.

### Phase 1.5 — SourceVerificationService (`app/services/source_verification_service.py`)
- **Models**: `glm-5` (GLM-5 Deep Thinking) via ZhipuAI API (`call_glm5_with_retry()`) for fact extraction, content integrity, and content quality assessment
- **Tools**: DataForSEO MCP (backlinks_domain_summary) for domain authority with 7-day caching. MCP calls use `mcp_call_with_retry()` from `research_service.py` for 429 rate-limit protection (2 call sites: domain_rank_overview, serp_organic_live_advanced). Improved JSON parsing with defensive MCP response handling (supports `.content[0].text`, `.text`, or fallback formats), field validation before int casting, and detailed debug logging (raw result type, content attributes, parsed keys). Catches JSONDecodeError separately from generic exceptions for better error diagnosis.
- **URL Deduplication** (March 2026): Deduplicates `elite_competitors` by URL at function start to prevent database unique constraint violations when research returns duplicate URLs. Logs skipped duplicates with `[DEDUP]` prefix. Passes `research_run_id` from main.py upfront (no longer uses placeholder `0`).
- **Trigger**: Runs automatically after Phase 1 completes if `elite_competitors` list exists
- **Logic**: Validates credibility of each Exa.ai source using **7-factor credibility scoring** (0-85 base scale + up to 15pts rescue bonus = 100pts max, March 2026). Each source evaluated against 7 base factors: (1) **Content Integrity** via GLM-5 adversarial trustworthiness check — promotional intent, claim sourcing, specificity, originality, editorial standards (25pts), (2) **Content Quality** via GLM-5 depth/evidence/structure assessment (15pts), (3) **Domain Tier + DataForSEO Authority** — curated tiers from `domain_tiers.py` primary, DataForSEO top10 keyword count fallback for unknown domains (20pts), (4) **Content Freshness** via Exa `publishedDate` extraction (primary) + OpenGraph meta tags fallback (4 patterns: article:published_time, og:published_time, name="publish_date", name="date") + regex URL/content patterns — <1yr (15pts), <2yr (10pts), <3yr (5pts), (5) **Author Attribution** — E-E-A-T signal from Exa author field (5pts), (6) **Topical Relevance** — Exa neural search score from `url_metadata_map` (5pts). **Spam penalty**: -10pts if promotional_intent ≥ 0.9 (heavy sales language). **Minimum threshold: 45.0/100 to pass verification (53% pass rate)**. Score breakdown logged as `[SCORE]` with all 7 factor values. **Borderline rescue mechanism** (March 2026): Sources scoring 35.0-44.9 with `promotional_intent >= 0.6` (non-salesy) get supplementary `calculate_rescue_bonus()` check using 5 signals: content depth/word count >2000w (+3), code blocks (+3), external reference density 5+ domains (+2), **SERP ranking** top5 (+10) / top10 (+7) / top20 (+4), **internal citations** credible count (+5 max) — up to +15 bonus points total. Rescued sources logged with `[RESCUED]` tag. **SERP and Citations moved to rescue**: These factors were unreliable in main scoring (SERP uses generic keywords, citations extracted post-verification), now applied as supplementary signals for borderline sources only. **Current date injection**: GLM-5 integrity prompt includes `Today's date is {date}` to prevent false "future date" flags on recent articles.
- **Enhanced Date Extraction** (March 2026): Three-layer fallback system: (1) **Primary**: Exa `publishedDate` field preserved via `url_metadata_map` from search results (highest confidence), (2) **Secondary**: OpenGraph meta tags (`article:published_time`, `og:published_time`, `name="publish_date"`, `name="date"`) scanned in first 5000 chars of HTML (4 patterns), (3) **Tertiary**: Regex patterns (10 patterns: ISO 8601, "published:", "date:", "updated:", "last-modified:", slash/dot formats) + URL path extraction (`/2024/03/15/article`). Sanity checks reject pre-2000 dates. **30-day future tolerance** on all validation points to handle timezone offsets and pre-dated content. Accepts optional `source_url` parameter for URL-based extraction. This fixes the 0/47 source failure (all sources lost 15pts for freshness due to missing Exa date extraction).
- **Backlink Verification**: Extracts URLs from source content (markdown links + HTML anchors + plain URLs) via regex. Validates each cited URL's domain against cached authority scores. Marks as credible if .gov/.edu OR domain_authority > 50. Skips self-references and social media domains. Limited to 10 citations per source.
- **Fact Extraction** (Improved March 2026): Uses GLM-5 to extract verifiable factual claims from each verified source (credibility ≥45). **Enhanced prompt** includes explicit examples of each fact type: (1) statistics with specific examples ("67% of SMBs experienced..."), (2) benchmarks ("Average cost of data breach is $4.35M"), (3) case_studies ("Shopify reduced load time by 40%"), (4) expert_quotes ("According to Gartner analyst..."). Returns JSON array with fact_text, fact_type, citation_anchor, and confidence (0.0-1.0). **Lowered confidence threshold to ≥0.6** (was 0.7) to capture more facts. Cost: ~$0.0001 per source.
- **Citation Map Building**: Stores extracted facts in FactCitation table linked to VerifiedSource. Citation map passed to WriterService as **pre-rendered bullet list** with copy-paste-ready markdown links (e.g., `• [Verizon 2024](https://verizon.com/dbir) — 67% of SMBs experienced...`). Replaces prior nested JSON format for better LLM comprehension. Injected into Claude's prompt with **critical emphasis** (visual borders, explicit examples, strict prohibitions against fabricating stats).
- **Iterative Source Search** (March 2026): Adaptive search with threshold decay when <3 sources verified. Max 3 iterations (45 sources total): (1) FindSimilar (seed: best verified source), (2) Niche-filtered (authoritative domains via `_get_niche_include_domains()`), (3) Broad search (no domain restrictions). **Threshold decay**: 45.0 → 40.0 → 35.0 across iterations to progressively lower standards if struggling. **Early exit**: stops mid-iteration when 3 sources found. **Deduplication**: tracks rejected domains to avoid re-verification. Implemented in `iterative_source_search()` function (source_verification_service.py line 1285).
- **3-Step Backfill Cascade** (main.py lines 346-432): Original backfill system (pre-iterative search). When Phase 1.5 verifies <3 credible sources, a 3-step cascade fires: (1) **FindSimilar** — uses highest-scoring verified source as seed for Exa find_similar, (2) **Niche-filtered backfill** — `niche_filtered_backfill()` searches curated domains via `_get_niche_include_domains()`, returns `[]` for unrecognized niches, (3) **Broad backfill** — `backfill_search()` with no domain restrictions. Each step only fires if still <3 verified sources. **Note**: Superseded by iterative_source_search in most cases.
- **Strict Enforcement**: Generation **fails** if <3 credible sources found after all backfill/iterative attempts. Error event yielded to frontend: "Insufficient credible sources: only X found (need 3 minimum)". User must choose different keyword or topic.
- **Output**: Returns `{verified_sources: list[VerifiedSource], rejected_sources: list[dict]}`. Verified sources saved to database with full credibility metrics. Research result enriched with `verified_sources` list for downstream phases.
- **Cost**: ~$0.05/article for Phase 1.5 alone (DataForSEO $0.01 for 5 domains + GLM-5 for integrity/quality/fact extraction). ~$0.005/article Phase 1.5 after caching (80%+ cache hit rate expected after 20 articles). Iterative search adds negligible cost (<$0.001) when triggered. **Full pipeline cost** (all 7 phases including GLM-5 research, DeepSeek-V3 psychology, Claude Sonnet 4.5 writer with agentic RAG, readability service, feedback loop): ~$0.15-$0.30 per generation. With the $10 budget this allows approximately 35-65 full generations.
- **Multi-Tenant**: All tables scoped by `(profile_name, niche)`. Domain credibility uses static tier lists in `domain_tiers.py`.
- **SSE Events**: `phase1_5_start`, `source_verification` (per-source progress with credibility scores color-coded: green ≥60, yellow ≥45, red <45), `source_backfill_start` (iterative search triggered), `phase1_5_complete` (summary stats: verified/rejected counts + avg credibility), `error` (if <3 sources).
- **March 2026 Scoring Fixes**: Restored 20pts of lost scoring via metadata extraction fixes (Freshness +15pts via `url_metadata_map`, Relevance +5pts via Exa score mapping). Moved SERP (10pts) and Citations (5pts) from base scoring to rescue bonus (more appropriate for borderline evaluation). Changed from 9-factor (100pts max) to 7-factor (85pts base + 15pts rescue). Threshold restored from emergency 35.0 → 45.0 after fixes. Sources that scored 44.8/100 before (0.2pts below threshold) now score ~60-65pts with proper metadata extraction.

### Phase 1.5b — Exa Research API (`app/services/exa_research_service.py`)
- **Model**: `exa-research` (Exa Research API) — single async call replacing multi-step GLM-5 verification for fact discovery
- **Trigger**: After Phase 1, when `EXA_RESEARCH_ENABLED = True` (default). Falls back gracefully on failure (non-fatal — yields `phase1_5_warning` and continues with Phase 1 data).
- **Logic**: Calls Exa Research API with keyword + niche, returns structured facts with source URLs. Research instructions (April 2026) lead with original-source requirement: "source_url MUST point to the ORIGINAL publisher — not a blog or news site that quotes it." Facts validated (`_validate_facts`), stored as `FactCitation` rows. **Citation laundering detection** applied per-fact via `detect_citation_laundering()` from source_verification_service.py — checks if named research orgs (Gartner, Forrester, etc.) match the actual source domain.
- **Tier-aware confidence scoring** (April 2026): Replaces hardcoded `confidence=0.85` with domain-tier-aware values: Tier 1-2 → 0.90 ("trusted"), Tier 3-4 → 0.75 ("corroborated"), Unknown → 0.60 ("corroborated"), Laundered → 0.40 ("suspect"). Composite score: `(confidence * 100 + credibility) / 2`.
- **source_content_map integration**: After fact discovery, all Phase 1.5 facts are added to `source_content_map` keyed by normalized URL (`_normalize_url()`). This ensures Phase 4 claim cross-referencing can verify claims against Research API sources (not just Phase 1 competitor articles).
- **Original source tracing** (April 2026): When citation laundering is detected, `resolve_original_source()` searches Exa constrained to the org's canonical domains (`KNOWN_RESEARCH_ORGS`) to find the actual publisher URL. If found, substitutes URL and clears laundered flag. Max `ORIGINAL_SOURCE_MAX_LOOKUPS=3` per article (~$0.001/lookup).
- **URL liveness validation** (April 2026): Before Phase 2, all URLs in `source_content_map` validated via `batch_validate_urls()` from `url_validation_service.py`. Dead URLs removed. 403 (paywalled) and timeouts kept. Config: `URL_VALIDATION_ENABLED=True`, `URL_VALIDATION_TIMEOUT=10`, `URL_VALIDATION_CONCURRENCY=10`.
- **Config**: `EXA_RESEARCH_TIMEOUT=300`, `EXA_RESEARCH_MODEL="exa-research"`, `EXA_RESEARCH_ENABLED=True`, `ORIGINAL_SOURCE_TRACING_ENABLED=True`, `ORIGINAL_SOURCE_MAX_LOOKUPS=3` in settings.py
- **Cost**: Single async API call per generation + 0-3 Exa search calls for source tracing (~$0.003 max). Reported cost per-call via `cost_dollars` field.

### Phase 1.7 — FactGroundingAgent (`app/services/fact_grounding_service.py`)
- **Model**: `glm-5` (GLM-5 Deep Thinking) via `call_glm5_with_retry()`
- **Trigger**: After Phase 1.5b (Exa Research API), before Phase 2 (Psychology). Runs when FactCitations exist for the research run.
- **Purpose**: Verifies Exa Research API facts against actual source page content before they enter the writer's citation pool. Prevents the self-fulfilling loop where `fact_text` was stored as "source content" and verified against itself.
- **Steps**:
  1. **Fetch real content** — Batch-fetch actual page content for source URLs via Exa `/contents` endpoint (`FACT_GROUNDING_CONTENT_MAX_CHARS` per page)
  2. **GLM-5 verification** — AI Analyst verifies each fact against real page content. Facts not present in source → `is_verified=False`, `verification_status="rejected_not_in_source"`. Facts confirmed → `is_verified=True`, `is_grounded=True` (upstream `verification_status` preserved — see ownership rule below)
  3. **Step 3.5 cross-source corroboration** — When `FACT_GROUNDING_CORROBORATION_ENABLED=True`, searches for independent confirmation of each surviving in-pool fact across other verified sources. Updates `consensus_count` and adjusts `composite_score` (×1.3 boost for corroborated, ×0.85 penalty for uncorroborated). Max `FACT_GROUNDING_MAX_CORROBORATION_SEARCHES` Exa searches.
  4. **Primary source tracing (Step 4)** — For secondary citations (e.g., blog citing a Gartner report), traces to the primary source via Exa search constrained to canonical domains. Regex fast-path extracts numbers from primary content; falls back to GLM-5 comparison. Branches: **confirmed** (confidence boost), **contradicted with number** (hard reject: `is_verified=False`), **contradicted no number** (soft reject: `verification_status="suspect"`, confidence penalty), **different_metric/not_found** (annotation only, status preserved)
  5. **Version currency check** — Detects versioned documents and checks for newer editions
  6. **Methodology tagging** — Tags conflatable facts with methodology context
- **verification_status ownership**: Phase 1.7 does NOT set `verification_status` on verified facts — the upstream value from `create_citations_from_research()` (Tier 1-2 → `"trusted"`, Tier 3-4 → `"corroborated"`, laundered → `"suspect"`) is the authoritative label. Phase 1.7 gates facts via `is_verified` boolean. The only exception is Step 4's contradicted-no-number branch, which downgrades status to `"suspect"`.
- **Writer citation filter dependency**: The writer (`writer_service.py`) has a two-gate citation filter: (1) `is_verified` boolean gate, (2) for quantitative claims (matching `\d+%|\$\d|percent|\d+\.\d+`), `verification_status` must be in `("corroborated", "trusted")`. Phase 1.7's `is_verified=True` passes gate 1; the preserved upstream status passes gate 2.
- **Config**: `FACT_GROUNDING_CONTENT_MAX_CHARS`, `FACT_GROUNDING_CORROBORATION_ENABLED`, `FACT_GROUNDING_GLM5_TEMPERATURE`, `FACT_GROUNDING_MAX_CORROBORATION_SEARCHES`, `FACT_GROUNDING_MAX_PRIMARY_LOOKUPS`, `FACT_GROUNDING_VERSION_CURRENCY_MAX` in `settings.py`
- **Cost**: ~$0.01-0.03/article (GLM-5 verification calls + Exa content fetches + corroboration searches)

### Claim Verification Agent (`app/services/claim_verification_agent.py`)
Cross-cutting service used by both Phase 1.5 (fact verification) and Phase 3 (post-writer claim verification). Four capabilities:

- **Capability A — AI Content Detection**: `detect_ai_generated_content()` scores sources using 6 LLM signals via DeepSeek-V3 (lexical diversity, sentence rhythm, hedging patterns, transition formulaism, specificity gradient, idiosyncrasy) merged with 4 deterministic signals (TTR, sentence variance, hedging density, transition density). `compute_ai_detection_penalty()` applies -5 to -15pts based on probability thresholds (≥0.55/-5, ≥0.70/-10, ≥0.85/-15). Applied after 7-factor scoring, before rescue bonus.
- **Capability B — Independent Fact Verification via Exa**: `verify_fact_independently()` builds verification queries from statistical claims, searches Exa with Tier 1-2 domain filter, validates via number-matching with context. Returns corroborated (+0.2), corrected (-0.3), or unverifiable (-0.5) adjustments. `batch_verify_facts()` prioritizes Tier 3-4/unknown sources, auto-trusts Tier 1-2 (faithfulness only). Max 15 Exa searches for budget control.
- **Capability C — Fact Faithfulness Check** (free, no API): `verify_fact_faithfulness()` uses 3-tier check: exact substring → number anchoring (all numbers within 300-char window) → n-gram overlap (55% threshold). Returns `is_grounded`, `grounding_method`, and `confidence_multiplier`. Zero cost — pure Python string matching.
- **Capability D — Post-Writer Claim Cross-Referencing**: `extract_article_claims()` uses regex-only extraction of claim+citation pairs from markdown, filters bare resource links. `cross_reference_claims()` does 3-tier URL matching (exact → normalized → path-prefix). **Domain-only fallback removed** (April 2026): Previously, domain-only matches (e.g., `gartner.com/fake-path` matching `gartner.com/real-path`) were sent to LLM for approval — this allowed path-level URL fabrication. Now domain-only matches are immediately flagged as "fabricated" with diagnostic info showing the correct verified URLs for that domain. Number-matching with context validation, text similarity fallback (30% word overlap). `format_claim_verification_feedback()` separates FABRICATED (URL not in map OR path fabricated) from UNGROUNDED (URL exists, claim doesn't match) and shows candidate facts with fix instructions. **Attribution mismatch detection**: `detect_attribution_mismatches()` in `source_verification_service.py` — single helper (extracted April 2026 to eliminate 50-line duplication) reusing module-level `_ORG_PATTERN` regex and `KNOWN_RESEARCH_ORGS` dict. Called from `event_generator()` in both initial check and retry loop.
- **Capability E — Final URL Allowlist Gate** (April 2026): `enforce_url_allowlist()` is the last-resort safety net before article save. Scans every `[text](url)` markdown link in the final article, strips any URL not in the verified source set (normalized `source_content_map` keys + `FactCitation.source_url` values). Unauthorized links replaced with plain anchor text. Called in `main.py` after claim verification, before `Post(...)` save. Logged as `[URL-GATE]`.

### Phase 2 — PsychologyAgent (`app/services/psychology_agent.py`)
- **Model**: `deepseek-chat` (DeepSeek-V3)
- **Timeout**: `asyncio.wait_for(..., timeout=90)` wrapper in `event_generator()` — prevents indefinite SSE hang if DeepSeek is slow
- **Input bounds**: Research JSON truncated to `MAX_RESEARCH_JSON_CHARS=6000` before prompt injection
- **Prompt**: `app/services/prompts/persuasion.md` — PAS (Problem-Agitation-Solution) framework
- **Output**: Structured JSON psychological blueprint with Identity Hooks, emotional triggers

### Phase 3 — WriterService (`app/services/writer_service.py`)
- **Model**: `claude-sonnet-4-5-20250929` via native `anthropic` SDK
- **Logic**: Operates in an **iterative triple-gate loop** (max 5 attempts). Each draft is validated by three sequential gates:
  1. **Gate 1 (SEO)**: `verify_seo_score` checks word count (min 1500), H2 count (min 5), list/table density (min 3 blocks), and Information Gain Density (min 2.0)
  2. **Gate 2 (Citations + Claim Verification)** (Enhanced March 2026): Two-stage gate. **Stage A** — `verify_citation_requirements` enforces minimum citations based on **intelligent quantitative claim detection**. Only runs if `research_run_id` provided (Phase 1.5 completed). **Expanded claim detection** uses **8 regex patterns** (was 4): percentages, dollar amounts, "X out of Y" stats, benchmarks (average/median/mean), spelled-out fractions (half/quarter/majority of companies), narrative claims (studies show/research indicates), comparative stats (twice as likely/2x more effective), year-based stats (In 2024, X organizations). **Relaxed format validation** accepts **3 citation formats**: (1) Markdown links `[text](url)` (preferred), (2) Parenthetical citations `(Source 2024)` — enhanced regex supports numbers, hyphens, periods in source names, (3) Footnote markers `[1]`, `[2]`. Citation requirements: 0-2 claims = 3 citations minimum, 3+ claims = 1 citation per claim. **Stage B** — Post-writer **Claim Cross-Referencing** via `claim_verification_agent.py`. Extracts every claim+citation pair from the article, matches each citation URL against the FactCitation database using 3-tier matching (exact URL → normalized URL → path-prefix). For each match, verifies the claim text actually corresponds to facts from that source using number anchoring + context word matching + text similarity (30% word overlap). Claims classified as: **VERIFIED** (claim matches source facts), **FABRICATED** (URL not in citation map — writer invented a source), **UNGROUNDED** (URL exists but claim doesn't match any fact), **AMBIGUOUS** (sent to DeepSeek LLM tiebreaker, max 10/article). **Fabricated = zero-tolerance always.** **Ungrounded tolerance**: always enforced via `max(2, int(total_claims * MAX_UNGROUNDED_RATIO))` threshold (MAX_UNGROUNDED_RATIO=0.15 in settings.py), further softened when low topical coverage detected. Feedback to writer shows available facts per source with fix instructions. **Topical coverage softening** (March 2026): Before applying the claim gate, tokenizes the keyword and counts how many FactCitations match the topic. If <3 on-topic facts found (`low_topical_coverage = True`), allows `max(2, int(total_claims * 0.15))` ungrounded claims instead of zero — prevents guaranteed failure when niche domain filters returned credible but off-topic sources. Yields `debug` event when triggered.
  3. **Gate 2 (Readability)**: `verify_readability` enforces 7th-10th grade reading level (target ≤10.0, accepts 7.5-10 range) using composite scoring: ARI (primary gate), Flesch-Kincaid (cross-check, target +1.5 buffer), Coleman-Liau (advisory only — over-penalizes technical vocabulary). Also enforces avg sentence length ≤12 words, **50% distribution gate** (requires ≥50% of sentences in 8-14 word range), and complex sentence gate (≤25% of sentences can exceed 15 words). Broad keyword masking during scoring: semantic keywords + blueprint entities + 58+ common niche terms including business jargon (security, business, software, streamline, leverage, optimize, enhance, framework, methodology, ecosystem, paradigm, establish, execute, implement, facilitate, comprehensive, infrastructure, capability, operational, strategic, scalable) that inflate ARI but have no shorter synonym. **Citation masking**: inline markdown citations treated as single words (URLs stripped during readability scoring). Readability scores (ARI, FK, CLI, avg sentence length) persisted to Post.readability_score JSON column for analytics.
- **Readability Service** (`app/services/readability_service.py`): Zero-cost pure Python implementation. ARI is the primary gatekeeper (character-based, deterministic). FK cross-check uses +1.5 buffer to absorb syllable-counting noise. CLI is advisory only — reported in debug but does not block publishing (it over-penalizes technical vocabulary that IS the SEO strategy). `READABILITY_DIRECTIVE` injected dynamically into prompt (never modifies `writer.md`). Includes **pre-flight simplicity primer** before main directive and **7th-grade template sentences** for pattern-matching. Uses **layer-cake scanning format** — optimized for how busy readers actually read (scan headings, first sentences, bold text). Requires benefit-driven H2 headings every 150-200 words, key takeaway as first sentence of each section, bold anchor phrase per section. Includes a concrete **word-swap reference table** (implement→set up, utilize→use, demonstrate→show, streamline→simplify, leverage→using, etc.) that is **repeated in feedback on every iteration** giving Claude explicit short-word alternatives. **Distribution feedback** shows exact breakdown ("Only 62% in 8-12 range, need 80%") with actionable rebalancing steps. Per-sentence analysis identifies complex sentences. Sentence splitting uses shared `_protect_abbreviations()` / `_restore_abbreviations()` helpers for consistent abbreviation handling (Mr., Dr., U.S., decimals) across `count_sentences()` and `split_sentences()`. Typical convergence: 1-2 passes for SEO, 1-2 passes for readability (down from 5 failures).
- **Writer Intelligence Injection**: After UserStyleRules, fetches `WriterPlaybook` for `(profile_name, niche)` and injects learned readability patterns (~100 tokens). Includes niche-specific ARI baseline, target sentence length, effective sentence patterns (future LLM distillation), and preferred word swaps (future LLM distillation). Example: "This niche typically achieves ARI: 7.15 grade level. Target sentence length: 11.2 words. (Playbook version 1, based on 10 successful articles)". Omitted on cold start (first 10 articles in a niche).
- **Citation Map Injection** (Reformatted March 2026): If `research_run_id` provided (Phase 1.5 completed), fetches `FactCitation` rows from database and builds **pre-rendered citation list** sorted by composite score. Each entry formatted as a bullet with copy-paste-ready markdown link: `• [anchor](url) — fact_preview`. Replaces prior nested JSON format that was too complex for LLM comprehension (caused 0-citation failures). Injected into prompt with **CRITICAL CITATION REQUIREMENTS** (visual emphasis with borders, explicit formatting). Instructions include: (1) Mandatory inline citations for all factual claims, (2) Pre-rendered citation list with exact markdown format, (3) Format examples for all 3 accepted formats (markdown, parenthetical, footnotes), (4) Minimum citation requirements (0-2 claims = 3 sources, 3+ claims = 1 per claim), (5) **Strict prohibitions** against inventing statistics/percentages/dollar amounts (must use ONLY citation map facts), (6) Proper citation examples. Citation map typically contains 10-30 facts from 3-5 verified sources. Claude copies pre-rendered markdown links directly into sentences during generation. **Topical Mismatch Warning** (March 2026): Before injecting the citation map, tokenizes the keyword and counts how many citations match the topic. If <3 on-topic citations found, injects a `*** TOPICAL MISMATCH WARNING ***` block instructing Claude to: only cite facts that genuinely support claims, prefer 2-3 well-matched citations over 8 forced ones, write authoritative prose without citations when no matching source exists, and accept sections with zero citations if the topic is not covered by available sources.
- **Prompt**: `app/services/prompts/writer.md` — Anti-AI-slop rules (bans: "delve", "tapestry", "crucial", corporate fluff) + dynamic SEO length directive (1,500-1,800 words) + **pre-flight simplicity primer** (7th-grade readability checklist) + `READABILITY_DIRECTIVE` (layer-cake scanning: benefit-driven H2s every 150-200 words, first-sentence takeaways, bold text anchoring, H1 + ≥5 H2s + ≥3 list/table blocks; 7th-8th grade target ≤7.5, 8-12 words/sentence target with 15-word hard ceiling, active voice, 7th-grade template sentences for pattern-matching, banned AI-slop words list + word-swap reference table embedded in directive) + **Citation Map** (if Phase 1.5 completed). **No Fake Assets** constraint bans references to non-existent templates, tools, downloads, checklists, or frameworks — requires actionable steps instead. **No Fabricated Data** constraint bans inventing statistics, percentages, or study results — must use ONLY verified facts from citation map provided.
- **LangGraph Editor Readability Alignment** (April 2026): Editor node in `writer_agent_graph.py` uses `verify_readability()` from `readability_service.py` instead of a separate hardcoded ARI threshold. Multi-factor check (ARI ≤ target + 1.5, FK ≤ target + 2.0, sentence distribution, complex sentence ratio) is consistent between section-level and article-level gates.
- **URL Credibility Hardening** (April 2026): Defense-in-depth against LLM URL fabrication/modification. **Prompt hardening**: `<no_fabrication>` block explicitly bans modified/guessed/invented URLs; `<citations>` block states "These are the ONLY URLs you may link to — copy-paste exactly"; `<self_check>` includes step 6 "every URL exists VERBATIM in citations block." **Editor check #7**: Deterministic regex scan in `editor_node` rejects any `[text](url)` where the URL (normalized via `_normalize_url_simple()`) is not in the citation allowlist (`state['all_citations']`). Failed sections sent back to writer for retry (max 2x). This catches URL fabrication at generation time, before post-writer verification.
- **Deterministic Banned-Word Sanitizer**: `_sanitize_banned_words()` runs after every LLM generation (before Gate 1). Dictionary of 22 banned words with all inflected forms (leveraging, optimized, landscapes, etc.) matched via case-preserving regex and replaced with natural alternatives. This is a safety net — prompt instructions alone cannot guarantee zero banned words from the LLM.
- **SEO Feedback**: On validation failure, reports all 6 conditions with specific counts: word count, H1 count, H2 count, list/table blocks, information gain density, and banned words found. Eliminates blind retry loops.
- **Citation Feedback**: On Gate 3 failure, reports citation count with specific guidance: "Only X citations found, need 3 minimum. Add more inline citations using [Source Title](URL) format. Use the citation map provided in the prompt."
- **Input**: Psychology blueprint + UserStyleRules from DB (scoped to active workspace) + WriterPlaybook (if ≥10 articles) + Citation map (if Phase 1.5 completed)
- **Output**: ~1,600 word Markdown article streamed in real-time. Yields `debug` events for iteration tracking (SEO pass/fail with specific failure reasons, Readability pass/fail with grade metrics) and `content` events for prose. Yields `RETRY_CLEAR` on validation failure to reset editor.

### Phase 6 — FeedbackAgent (`app/services/feedback_service.py`)
- **Model**: `deepseek-chat` (DeepSeek-V3)
- **Trigger**: `/posts/{post_id}/approve` endpoint when user submits human-edited Markdown
- **Logic**: Semantically diffs `original_ai_content` vs `human_edited_content`, extracts `UserStyleRule` entities
- **Output**: Permanent style rules saved to Neon PostgreSQL, injected into Phase 3 next run

### Research Intelligence Loop (`app/services/research_intel_service.py`)

A closed-loop system that makes the ResearchAgent self-improving across runs. Four phases:

1. **Capture** ($0/run) — `_capture_run_telemetry()` in `research_service.py` extracts structured telemetry (tool sequence, KD stats, Exa queries, entity clusters) from data already in memory. Stored as `ResearchRun` rows.
2. **Recall** (~200 tokens) — `_get_niche_playbook()` retrieves the distilled `NichePlaybook` for `(profile_name, niche)` and injects it into R1's agentic prompt. Falls back to heuristic aggregation of last 5 raw runs. Returns `None` on true cold start.
3. **Reinforce** ($0 on `/approve`) — `ResearchIntelService.score_research_run()` computes `SequenceMatcher` edit-distance ratio (0.0–1.0) between `original_ai_content` and human-edited content. Persisted as `ResearchRun.quality_score`.
4. **Distill** (~$0.001 per 10 runs) — `maybe_distill()` triggers when ≥10 undistilled runs accumulate for a niche. Uses `_compute_heuristic_playbook()` (zero LLM cost, Counter-based stats) if <5 quality-scored runs, otherwise `_distill_with_flash()` via `deepseek-chat` (DeepSeek-V3). Result upserted into `NichePlaybook`.

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
- Future: LLM-based distillation via DeepSeek to extract sentence patterns and word swaps from article content

**Complementary to UserStyleRule**:
- `UserStyleRule` (FeedbackAgent) learns *what humans prefer* (tone, voice, specificity)
- `WriterPlaybook` (WriterIntelService) learns *what achieves readability targets* (sentence patterns, word choices, structure)
- Both systems feed into WriterService prompts, optimizing for different goals

---

## SSE Streaming Architecture

- `/generate` endpoint → `event_generator()` async generator → `StreamingResponse` (Uses Pydantic `model_dump(mode='json')` for safe datetime serialization)
- Frontend `static/js/console.js` consumes SSE events and renders them in the Cyber-Glassmorphism console. Uses `AbortController` to cancel in-flight SSE streams when a new generation starts (prevents duplicate requests).
- **Real-time Content**: Phase 3 (Writer) streams `content` events which are appended directly to the UI editor for a "live typing" effect. Supports `RETRY_CLEAR` data to reset the editor during iterative SEO loops.
- **Debug Propagation**: Forwarding `debug` events from all backend agents (Phase 1 tool decisions, Phase 1.5 source verification progress, Phase 3 iteration logs) to the Cyber-Glass terminal for full visibility.
- Each phase streams progress events (tool decisions, intermediate results) in real time.
- DataForSEO MCP tool names are streamed directly to the UI as R1 selects them
- **Phase 1.5 Events**: `phase1_5_start` (verification begins), `source_verification` (per-source progress with credibility scores color-coded: green ≥80, yellow ≥45, red <45), `phase1_5_complete` (summary: verified/rejected counts + avg credibility), `phase1_5_warning` (Research API failed — non-fatal, pipeline continues with Phase 1 data), `error` (generation halted if <3 credible sources)

---

## SSL Retry on Post-Generation Commit

The DB session (`db`) is checked out via FastAPI's `Depends(get_db)` before `event_generator()` starts. With up to 5 iterations of Claude API calls (15-30s each), total generation can run 2-3 minutes. Neon PostgreSQL drops idle SSL connections before that completes. `pool_pre_ping` only helps at checkout time, not for connections already held open.

**Fix** (in `app/main.py`, `event_generator()`):
- `nonlocal db` declared at top of generator so reassignment works across Python's closure scoping
- Both post-generation `db.commit()` calls wrapped in `try/except OperationalError` → rollback → close → `SessionLocal()` → re-add/merge → commit
- Only applied to the two commits after article generation (Post save + ResearchRun linking), not every commit in the file

---

## State Management & Bleed Prevention

Ark Opus implements multi-layered state isolation to prevent topic bleed across keyword generations:

### Backend Cache Isolation
- **ResearchCache Table**: Composite unique key `(keyword, profile_name, niche)` enforces strict workspace and niche scoping
- **Cache Lookup**: `_get_cached(keyword, profile_name, niche)` in `research_service.py` requires exact match on all three fields
- **Cache Save**: `_save_cache(keyword, profile_name, niche, result)` upserts with full composite key
- **Migration**: `migrate_research_cache()` in `app/database.py` adds `profile_name` and `niche` columns to existing cache entries with `'default'` values

### Playbook Topic Boundaries
- **XML Wrapper**: Niche playbooks injected within `<niche_playbook>` tags in R1 prompt
- **Critical Instruction**: Explicit direction to GLM-5: "Use playbook STRICTLY for tone, audience insights, and strategic style. DO NOT research past topics. Focus EXCLUSIVELY on current Target Keyword: '{keyword}'"
- **Location**: `_build_agentic_prompt()` method in `research_service.py`

### Frontend State Clearing
- **Global Variables**: `lastGeneratedMarkdown`, `currentPostId`, `currentQuestions` cleared at two points:
  1. Generate button click handler (line ~246 in `console.js`)
  2. `executeGeneration()` function start (line ~304 in `console.js`)
- **AbortController**: `currentAbortController` aborts any in-flight SSE stream before starting a new generation. Nulled in `finally` block. `AbortError` caught separately with a yellow "aborted" terminal message (not a red error).
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
- **Cartographer panel**: `#cartographer-modal` slide-out provides an interface to plan Content Campaigns mappings. Spoke "Generate" buttons use `showConfirmModal()` (custom modal in `#confirm-modal-overlay`) instead of `window.confirm()`.
- **Confirm modal**: Reusable `showConfirmModal(message, onConfirm)` function in console.js + `#confirm-modal-overlay` HTML element. Matches workspace modal's center-zoom animation pattern. Used for cartographer spoke generation confirmation.

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
- `VerifiedSource` — credibility-scored sources from Phase 1.5. Stores (`url`, `title`, `domain`, `credibility_score` 0-100 (7-factor base 0-85 + rescue bonus 0-15), `domain_authority`, `publish_date`, `freshness_score`, `internal_citations_count`, `has_credible_citations`, `citation_urls_json`, `is_academic`, `is_authoritative_domain`, `content_snippet` 500 chars, `verification_passed` (threshold: ≥45.0), `rejection_reason`). Composite unique constraint `(research_run_id, url)`. Linked to `ResearchRun` via `research_run_id`. Scoped by `profile_name`. March 2026: Scoring changed from 9-factor (100pts) to 7-factor (85pts base) + rescue bonus (15pts max).
- `FactCitation` — extracted facts mapped to verified sources. Stores (`fact_text`, `fact_type` stat/benchmark/case_study/expert_quote, `source_url`, `source_title`, `citation_anchor`, `confidence_score` 0.0-1.0, `composite_score`, `source_credibility`, `verification_status` enum: `"trusted"|"corroborated"|"suspect"|"not_checked"|"corrected"|"unverifiable"|"ungrounded"`, `is_verified` boolean, `is_grounded` boolean, `grounding_method`, `consensus_count`). Indexed by `verified_source_id` and `research_run_id`. `verification_status` set by upstream producer (`create_citations_from_research()`) based on domain tier — preserved through Phase 1.7 verification. Writer citation filter requires `is_verified=True` AND `verification_status in ("corroborated", "trusted")` for quantitative claims.

- `MigrationHistory` — tracks applied migrations (`name`, `applied_at`). Prevents re-running migrations and detects partial failures.

**FK Constraints** (April 2026): `posts.research_run_id` → `research_runs.id` (ON DELETE SET NULL), `writer_runs.post_id` → `posts.id` (ON DELETE CASCADE). Applied via `migrate_fk_constraints()` in `database.py`.

**Migration Versioning** (April 2026): `migration_history` table tracks all applied migrations. `migrate_version_tracking()` creates the table and seeds it with existing migrations. All migration functions are idempotent (`IF NOT EXISTS` / `ALTER TABLE` guards).

- `UserStyleRuleArchive` — archived style rules before pruning (`rule_descriptions_json`, `pruned_to_count`, `archived_at`). Data loss prevention for FeedbackAgent consolidation.
- `ProfileSettings` — per-profile settings overrides (`settings_json`, `updated_at`). Unique constraint on `profile_name`. Merged with `CONFIGURABLE_SETTINGS` defaults via `resolve_settings()`.
- `DomainCredibilityCache` — cached domain credibility scores (`domain`, `niche`, `tier_level`, `base_score`, `integrity_score`, `quality_score`, `check_count`, `last_checked`). Composite unique constraint `(domain, niche)`. 7-day TTL.
- `ApiKey` — API key authentication (`key_hash` SHA256, `profile_name`, `label`, `is_active`). Unique constraint on `key_hash`. Created via `/admin/api-keys` endpoint.

Connection configured in `app/database.py` — Neon PostgreSQL with `pool_pre_ping`, `pool_recycle=240`, TCP keepalives.

---

## Anti-AI-Slop Enforcement

- Banned words list in `app/services/prompts/writer.md` (delve, tapestry, crucial, foster, etc.)
- **7th-10th grade readability enforcement** via `readability_service.py` — ARI-primary scoring with FK cross-check (+1.5 buffer) and CLI advisory. Target ≤10.0, accepts 7.5-10 range. Broad keyword masking (semantic keywords + entities + 58+ niche terms including business jargon: streamline, leverage, optimize, enhance, framework, methodology, ecosystem, paradigm, etc.) prevents unavoidable subject-matter nouns from inflating scores. Enforces avg sentence length ≤12 words, **50% distribution gate** (requires ≥50% of sentences in 8-14 word range), complex sentence gate (≤25% can exceed 15 words), active voice, immediate technical term explanations. READABILITY_DIRECTIVE includes **pre-flight simplicity primer** and **7th-grade template sentences** for pattern-matching. Uses **layer-cake scanning format**: benefit-driven H2s every 150-200 words, first-sentence takeaways per section, bold anchor phrases, 1,500-1,800 word target. Embeds banned AI-slop words list + concrete word-swap reference table (implement→set up, utilize→use, streamline→simplify, leverage→using, etc.) directly in the directive and **repeated in feedback on every iteration**. **Distribution feedback** shows exact breakdown with actionable rebalancing steps when below 50% gate threshold. Directive targets 8-12 words/sentence aspirationally (never exceed 15 words). Readability scores persisted to Post.readability_score JSON for analytics.
- PAS framework enforced via `app/services/prompts/persuasion.md`
- Identity Hooks target reader psychology via specific audience archetypes
- UserStyleRules from FeedbackAgent mathematically converge on the user's exact writing style over runs

---

## Centralized Configuration (`app/settings.py`)

All operational constants centralized in `settings.py` — imported by service files:
- **Timeouts**: `BRIEFING_TIMEOUT`, `DEEPSEEK_TIMEOUT`, `DEEPSEEK_REASONER_TIMEOUT`, `CARTOGRAPHER_TIMEOUT`, `EXA_TIMEOUT`, `RESEARCH_TIMEOUT`
- **Research tuning**: `CACHE_TTL_HOURS`, `MAX_AGENTIC_ITERATIONS`, `EXA_NUM_RESULTS`, `EXA_MAX_CHARACTERS`, `SERP_DEPTH`, `LOCATION_CODE`, `LANGUAGE_CODE`
- **Writer tuning**: `MAX_WRITER_ATTEMPTS`, `WRITER_MAX_TOKENS`
- **Source verification**: `SOURCE_CREDIBILITY_THRESHOLD`, `SOURCE_THRESHOLD_DECAY`, `MAX_VERIFICATION_ITERATIONS`
- **Claim verification**: `MAX_EXA_FACT_CHECKS`, `MAX_LLM_VERIFICATIONS`, `MAX_CLAIM_RETRIES`, `MAX_UNCITED_CLAIMS`, `CLAIM_TEXT_SIMILARITY_THRESHOLD`, `LLM_SOURCE_CONTEXT_CHARS`, `CLAIM_NUMBER_CONTEXT_WORDS`, `MAX_UNGROUNDED_RATIO`, `VERIFY_QUALITATIVE_CLAIMS`
- **Source rescue bonus**: `RESCUE_SERP_TOP5_BONUS`, `RESCUE_SERP_TOP10_BONUS`, `RESCUE_SERP_TOP20_BONUS`, `RESCUE_MAX_BONUS`, `RESCUE_MIN_SCORE`
- **Source penalties**: `BLOG_DOMAIN_PENALTY`, `BLOG_PATH_PENALTY`, `UNSOURCED_CLAIMS_PENALTY`
- **GLM-5**: `GLM5_MODEL`, `GLM5_API_URL`, `GLM5_MAX_TOKENS`, `GLM5_TEMPERATURE`, `GLM5_TIMEOUT`, `GLM5_MAX_RETRIES`, `GLM5_RETRY_BASE_DELAY`, `GLM5_CONCURRENCY_LIMIT`
- **Exa rate limiting**: `EXA_SEARCH_CONCURRENCY`, `EXA_CONTENTS_CONCURRENCY`, `EXA_MAX_RETRIES`, `EXA_RETRY_BASE_DELAY`, `EXA_INTER_REQUEST_DELAY`
- **Exa Research API**: `EXA_RESEARCH_TIMEOUT`, `EXA_RESEARCH_MODEL`, `EXA_RESEARCH_ENABLED`
- **URL validation**: `URL_VALIDATION_TIMEOUT`, `URL_VALIDATION_CONCURRENCY`, `URL_VALIDATION_ENABLED`
- **Fact grounding (Phase 1.7)**: `FACT_GROUNDING_CONTENT_MAX_CHARS`, `FACT_GROUNDING_CORROBORATION_ENABLED`, `FACT_GROUNDING_GLM5_TEMPERATURE`, `FACT_GROUNDING_MAX_CORROBORATION_SEARCHES`, `FACT_GROUNDING_MAX_PRIMARY_LOOKUPS`, `FACT_GROUNDING_VERSION_CURRENCY_MAX`
- **Original source tracing**: `ORIGINAL_SOURCE_TRACING_ENABLED`, `ORIGINAL_SOURCE_MAX_LOOKUPS`
- **Input bounds**: `MAX_USER_CONTEXT_CHARS`, `MAX_STYLE_RULES_CHARS`, `MAX_RESEARCH_JSON_CHARS`, `MAX_PLAYBOOK_CHARS`
- **Feedback**: `RULE_CONSOLIDATION_THRESHOLD`
- **Rate limiting**: `MAX_DAILY_GENERATIONS`
- **Database**: `DB_POOL_RECYCLE`
- **Feature flags**: `DEBUG_MODE`, `DATAFORSEO_CONTENT_ANALYSIS_ENABLED`, `CLAIM_GATE_HARD_BLOCK`, `URL_VALIDATION_ENABLED`, `ORIGINAL_SOURCE_TRACING_ENABLED`

All service files import what they need (e.g., `from ..settings import DEEPSEEK_TIMEOUT`). New constants should be added here, not hardcoded in service files.

---

## Resilience Patterns

- **MCP 429 Retry**: `mcp_call_with_retry(session, tool_name, arguments, max_retries=3)` in `research_service.py`. Exponential backoff (1s→2s→4s) on 429/rate-limit errors from DataForSEO MCP. Non-429 errors re-raised immediately. Used by all 6 MCP call sites across `research_service.py` (4) and `source_verification_service.py` (2).
- **5xx Retry** (April 2026): GLM-5 (`glm_client.py`) and Exa (`exa_client.py`) clients retry on 429, 500, 502, 503 with exponential backoff (1s→2s→4s, max 3 retries). Previously only 429 was retryable — transient 5xx server errors caused immediate failure.
- **Phase 1.5 Graceful Degradation** (April 2026): Exa Research API failure (`ExaResearchError`, `asyncio.TimeoutError`) is non-fatal. Pipeline yields `phase1_5_warning` SSE event and continues with Phase 1 data only. Writer handles zero-citations gracefully. **Claim gate bypass**: When no FactCitations exist for the research run, claim verification is skipped entirely (prevents false rejection).
- **Psychology Timeout** (April 2026): `asyncio.wait_for(..., timeout=90)` on DeepSeek-V3 psychology blueprint generation. Prevents indefinite SSE stream hang.
- **Input Length Bounds** (April 2026): User-controlled inputs truncated before LLM prompt injection to prevent token overflow: `MAX_USER_CONTEXT_CHARS=2000` (briefing), `MAX_STYLE_RULES_CHARS=1500` (writer), `MAX_RESEARCH_JSON_CHARS=6000` (psychology), `MAX_PLAYBOOK_CHARS=1500` (research/writer).
- **SSL Retry**: `nonlocal db` pattern in `event_generator()` for Neon PostgreSQL dropped connections (see SSL Retry section).
- **URL Liveness Validation** (April 2026): `url_validation_service.py` validates source URLs via async HEAD (fallback GET stream) before they enter `source_content_map`. Semaphore-limited concurrency (`URL_VALIDATION_CONCURRENCY=10`). 403 (paywalled) treated as live (Gartner/McKinsey return 403 for direct access). Timeouts treated as live (network transients shouldn't block pipeline). Dead URLs (404, 410, 5xx) removed from source map. Adds ~1-2s to pipeline, $0 cost.
- **URL Allowlist Enforcement** (April 2026): 3-layer defense-in-depth against LLM URL fabrication: (1) Editor check #7 in `writer_agent_graph.py` catches fabricated URLs during writer loop (sends back for retry), (2) `cross_reference_claims()` marks domain-only URL matches as fabricated, (3) `enforce_url_allowlist()` strips unauthorized URLs before article save. Any URL surviving all 3 layers would need to exactly match a verified source URL.
- **Frontend Abort**: `currentAbortController` cancels in-flight SSE streams before new generation starts. Prevents duplicate request overlap.

---

## Security Infrastructure (April 2026)

### API Key Authentication (`app/auth.py`)
- All endpoints except `/health` and `/` require `X-API-Key` header
- `verify_api_key()` FastAPI dependency: extracts header, SHA256 hashes, validates against `api_keys` table (is_active=True), returns `profile_name`
- Keys created via `POST /admin/api-keys` (requires `X-Admin-Secret` header, validated with `secrets.compare_digest()`)

### Prompt Injection Defense (`app/security.py`)
- `sanitize_prompt_input(text, max_chars, tag)` — strips HTML comments, control characters (zero-width spaces, bidi overrides, paragraph separators), truncates, wraps in XML boundary tags
- `sanitize_external_content(text, max_chars)` — same stripping without XML wrapping, for untrusted external content
- Applied in: briefing_agent, research_service, psychology_agent, writer_agent_graph, cartographer_service

### Rate Limiting
- `slowapi` with API key hash or client IP as key
- `/campaigns/plan`: 10/minute
- `/research/{keyword}`: 10/minute
- `/generate/{keyword}`: 5/minute
- Daily cap: `MAX_DAILY_GENERATIONS=50` per profile

### Security Headers
- `SecurityHeadersMiddleware` in `main.py` adds CSP, X-Content-Type-Options, X-Frame-Options to all responses

### Error Sanitization
- SSE error events send generic "An internal error occurred" message
- Stack traces and exception details logged server-side only (`logger.error`)
- Debug tracebacks logged when `runtime["debug_mode"]` is True, but never sent to client

### Phase 1.5 Claim Gate Bypass (April 2026)
- When Exa Research API fails, `research_run_id` remains truthy (set in Phase 1) but no FactCitation rows exist
- Phase 4 now checks if `run_fact_citations` is empty before running claim verification
- If empty: skips verification, yields `claim_verification_complete` event with all-zero counts
- Prevents false article rejection when Phase 1.5 degrades gracefully

---

## NEVER
- Never rewrite entire files for small logic changes
- Never remove `pool_pre_ping` or keepalive args from `database.py`
- Never modify `app/services/prompts/*.md` without explicit approval
- Never bypass `profile_name` filtering — all style rules are workspace-scoped
- Never duplicate source code into `.md` memory files
