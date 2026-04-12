import os
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path, override=True)

def get_bool_env(key: str, default: bool = False) -> bool:
    val = os.getenv(key)
    return val.lower() in ("true", "1", "yes") if val else default

DEBUG_MODE = get_bool_env("ARK_DEBUG", False)
DATAFORSEO_CONTENT_ANALYSIS_ENABLED = get_bool_env("DATAFORSEO_CONTENT_ANALYSIS_ENABLED", False) # Additive feature flag

def get_clean_env(key: str) -> str | None:
    val = os.getenv(key)
    if val:
        # Strip double quotes, single quotes, and surrounding whitespace
        return val.strip(' "\'')
    return None

DEEPSEEK_API_KEY = get_clean_env("DEEPSEEK_API_KEY")
DATAFORSEO_LOGIN = get_clean_env("DATAFORSEO_LOGIN")
DATAFORSEO_PASSWORD = get_clean_env("DATAFORSEO_PASSWORD")
EXA_API_KEY = get_clean_env("EXA_API_KEY")
ANTHROPIC_API_KEY = get_clean_env("ANTHROPIC_API_KEY")
ZAI_API_KEY = get_clean_env("ZAI_API_KEY")
if not DEEPSEEK_API_KEY:
    raise ValueError("DEEPSEEK_API_KEY is missing.")
if not ZAI_API_KEY:
    raise ValueError("ZAI_API_KEY is missing.")
# Note: DATAFORSEO credentials still loaded for ResearchAgent (SERP tools)
# Validation removed - source verification no longer requires DataForSEO
if not EXA_API_KEY:
    raise ValueError("EXA_API_KEY is missing.")
if not ANTHROPIC_API_KEY:
    raise ValueError("ANTHROPIC_API_KEY is missing.")

ADMIN_SECRET = get_clean_env("ADMIN_SECRET")

# ── Operational Constants ──────────────────────────────────────────
# Timeouts (seconds)
BRIEFING_TIMEOUT = 30
DEEPSEEK_TIMEOUT = 60
DEEPSEEK_REASONER_TIMEOUT = 90
CARTOGRAPHER_TIMEOUT = 300
EXA_TIMEOUT = 30

# Research tuning
CACHE_TTL_HOURS = 24
MAX_AGENTIC_ITERATIONS = 5
EXA_NUM_RESULTS = 10
EXA_MAX_CHARACTERS = 25000
SERP_DEPTH = 10
LOCATION_CODE = 2840
LANGUAGE_CODE = "en"

# Model constants
CLAUDE_MODEL = "claude-sonnet-4-5-20250929"
DEEPSEEK_MODEL = "deepseek-chat"
DEEPSEEK_REASONER_MODEL = "deepseek-reasoner"

# GLM-5 Deep Thinking
GLM5_MODEL = "glm-5"
GLM5_API_URL = "https://api.z.ai/api/paas/v4/chat/completions"
GLM5_MAX_TOKENS = 4096
GLM5_TEMPERATURE = 1.0
GLM5_TIMEOUT = 120  # Reasoning tasks may take longer
GLM5_MAX_RETRIES = 3
GLM5_RETRY_BASE_DELAY = 1  # seconds, exponential backoff: 1s, 2s, 4s
GLM5_CONCURRENCY_LIMIT = 2  # GLM-5 API allows max 2 simultaneous requests

# Exa rate limiting (Phase 1 raw calls)
EXA_SEARCH_CONCURRENCY = 8       # Max concurrent /search + /findSimilar (Exa limit: 10 QPS)
EXA_CONTENTS_CONCURRENCY = 20    # Max concurrent /contents (Exa limit: 100 QPS)
EXA_MAX_RETRIES = 3
EXA_RETRY_BASE_DELAY = 1         # seconds, exponential backoff: 1s, 2s, 4s
EXA_INTER_REQUEST_DELAY = 0.12   # seconds between search releases (~8 QPS sustained)

# Exa Research API (Phase 1.5 fact discovery + verification)
EXA_RESEARCH_TIMEOUT = 300          # seconds to poll before giving up (Research API p90 ~90s, complex niches can take longer)
EXA_RESEARCH_MODEL = "exa-research" # or "exa-research-pro" for complex niches
EXA_RESEARCH_ENABLED = True         # feature flag — False skips Phase 1.5 entirely
EXA_RESEARCH_SUBMIT_RETRIES = 3     # retry attempts for initial POST to /research/v1
EXA_RESEARCH_SUBMIT_BASE_DELAY = 2.0  # seconds, doubles each retry (2s → 4s → 8s)

# URL liveness validation (Phase 1 + Phase 1.5 ingestion gate)
URL_VALIDATION_TIMEOUT = 10          # seconds per HEAD/GET check
URL_VALIDATION_CONCURRENCY = 10      # max concurrent URL checks
URL_VALIDATION_ENABLED = True        # feature flag — False skips URL validation

# Original source tracing (Phase 1.5 citation laundering resolution)
ORIGINAL_SOURCE_TRACING_ENABLED = True  # feature flag — False skips source tracing
ORIGINAL_SOURCE_MAX_LOOKUPS = 3         # max Exa searches per article for source tracing

# Fact Grounding Agent (Phase 1.7 — pre-writer source verification)
FACT_GROUNDING_ENABLED = True                # Feature flag — False skips Phase 1.7 (falls back to current behavior)
FACT_GROUNDING_TIMEOUT = 240                 # Max seconds for entire grounding phase (increased from 180 for Step 4 GLM-5 + Step 3.5 corroboration)
FACT_GROUNDING_MAX_PRIMARY_LOOKUPS = 3       # Max Exa searches for secondary citation tracing
FACT_GROUNDING_VERSION_CURRENCY_MAX = 3      # Max Exa searches for version currency checks
FACT_GROUNDING_CONTENT_MAX_CHARS = 8000      # Max chars per source from Exa /contents
FACT_GROUNDING_GLM5_TEMPERATURE = 0.1        # Low temp for verification precision (lower than extraction's 0.3)

# Cross-source corroboration (Phase 1.7 Step 3.5)
FACT_GROUNDING_CORROBORATION_ENABLED = True    # Feature flag — False skips corroboration
FACT_GROUNDING_MAX_CORROBORATION_SEARCHES = 5  # Max Exa searches for independent confirmation

# Writer tuning
MAX_WRITER_ATTEMPTS = 5
WRITER_MAX_TOKENS = 8192

# Source verification
SOURCE_CREDIBILITY_THRESHOLD = 45.0
SOURCE_THRESHOLD_DECAY = 5.0
MAX_VERIFICATION_ITERATIONS = 3

# Claim verification
MAX_EXA_FACT_CHECKS = 15
MAX_LLM_VERIFICATIONS = 10
CLAIM_TEXT_SIMILARITY_THRESHOLD = 0.45
LLM_SOURCE_CONTEXT_CHARS = 5000
MAX_UNCITED_CLAIMS = 2
MAX_UNGROUNDED_RATIO = 0.15  # Max fraction of total claims allowed to be ungrounded before gate fails
CLAIM_NUMBER_CONTEXT_WORDS = 3  # Min shared context words for number matching (was 2)

# Source rescue bonus
RESCUE_SERP_TOP5_BONUS = 5.0     # Was 10 — halved to prevent SERP-only rescues
RESCUE_SERP_TOP10_BONUS = 3.0    # Was 7
RESCUE_SERP_TOP20_BONUS = 1.0    # Was 4
RESCUE_MAX_BONUS = 10.0          # Was 15 — cap total rescue contribution
RESCUE_MIN_SCORE = 38.0          # Was 35 — narrows the rescue eligibility window

# Source credibility penalties
BLOG_DOMAIN_PENALTY = 10.0        # pts deducted for blog.* subdomains
BLOG_PATH_PENALTY = 5.0           # pts deducted for /blog/ in URL path
UNSOURCED_CLAIMS_PENALTY = 15.0   # pts deducted for Tier 0 with claim_sourcing < 0.4

# Database pool
DB_POOL_RECYCLE = 240  # seconds — safely under Neon's 5-min idle timeout

# Claim gate enforcement
CLAIM_GATE_HARD_BLOCK = True  # Block article save when claim verification fails after retries
VERIFY_QUALITATIVE_CLAIMS = True  # Verify qualitative claims (research shows, according to, etc.)
MAX_CLAIM_RETRIES = 2               # Max writer retries on claim verification failure

# Feedback
RULE_CONSOLIDATION_THRESHOLD = 20

# Prompt injection bounds (max chars for user-controlled inputs injected into LLM prompts)
MAX_USER_CONTEXT_CHARS = 2000       # Briefing answers injected into GLM-5 research prompt
MAX_STYLE_RULES_CHARS = 1500        # Accumulated style rules injected into writer prompt
MAX_RESEARCH_JSON_CHARS = 6000      # Research data JSON injected into psychology prompt
MAX_PLAYBOOK_CHARS = 1500           # Niche/writer playbook text injected into prompts
RESEARCH_TIMEOUT = 300              # Phase 1 timeout (seconds)

# Rate limiting
MAX_DAILY_GENERATIONS = 50          # Per-profile daily cap (~$15 at $0.30/gen)
MAX_STYLE_RULES_PER_PROFILE = 25    # Prevent unbounded style rule accumulation

# ── User-Configurable Settings Registry ──────────────────────────────
# Each entry defines type, default, bounds/choices, and UI metadata.
# The GET /settings endpoint returns this so the frontend renders dynamically.
CONFIGURABLE_SETTINGS = {
    "claim_gate_hard_block": {
        "type": "bool", "default": CLAIM_GATE_HARD_BLOCK,
        "label": "Strict Fact-Check Mode",
        "tooltip": "When ON, articles are blocked from saving if claim verification fails. Turn OFF to allow draft previews even with unverified claims.",
    },
    "verify_qualitative_claims": {
        "type": "bool", "default": VERIFY_QUALITATIVE_CLAIMS,
        "label": "Verify Soft Claims",
        "tooltip": "Check qualitative claims like 'research shows' and 'according to experts.' Turn OFF for opinion or editorial content.",
    },
    "dataforseo_content_analysis_enabled": {
        "type": "bool", "default": DATAFORSEO_CONTENT_ANALYSIS_ENABLED,
        "label": "Content Analysis (DataForSEO)",
        "tooltip": "Enable advanced content analysis during research. Adds depth but uses additional API credits.",
    },
    "debug_mode": {
        "type": "bool", "default": DEBUG_MODE,
        "label": "Debug Events",
        "tooltip": "Show detailed engine events in the generation stream. Useful for troubleshooting but noisy for normal use.",
    },
    "source_credibility_threshold": {
        "type": "float", "default": SOURCE_CREDIBILITY_THRESHOLD, "min": 35.0, "max": 75.0,
        "label": "Source Trust Threshold",
        "tooltip": "Minimum credibility score (out of 100) a source must reach. Higher = stricter, fewer citations. Lower = broader coverage.",
    },
    "exa_num_results": {
        "type": "int", "default": EXA_NUM_RESULTS, "min": 5, "max": 25,
        "label": "Research Depth",
        "tooltip": "How many sources to pull per search. More = deeper research but slower and costs more.",
    },
    "max_agentic_iterations": {
        "type": "int", "default": MAX_AGENTIC_ITERATIONS, "min": 2, "max": 10,
        "label": "Research Rounds",
        "tooltip": "Maximum research iterations before stopping. More rounds = more thorough but takes longer.",
    },
    "cache_ttl_hours": {
        "type": "int", "default": CACHE_TTL_HOURS, "choices": [1, 6, 24, 72],
        "label": "Cache Freshness",
        "tooltip": "How long to reuse previous research before fetching new data. Shorter = always fresh. Longer = faster repeats.",
    },
    "writer_max_tokens": {
        "type": "int", "default": WRITER_MAX_TOKENS, "choices": [4096, 8192, 12288, 16384],
        "label": "Max Article Length",
        "tooltip": "Upper limit on article length (in tokens). ~4096 = short post, ~16384 = long-form guide.",
    },
    "max_writer_attempts": {
        "type": "int", "default": MAX_WRITER_ATTEMPTS, "min": 1, "max": 10,
        "label": "Writer Retry Limit",
        "tooltip": "How many times the writer retries if quality checks fail. More retries = better odds but costs more.",
    },
}


def resolve_settings(profile_settings_row, configurable=CONFIGURABLE_SETTINGS) -> dict:
    """
    Merge DB overrides with hardcoded defaults.

    Args:
        profile_settings_row: A ProfileSettings ORM object (or None).
        configurable: The CONFIGURABLE_SETTINGS registry.

    Returns:
        dict with all configurable keys resolved (DB override or default).
    """
    import json as _json
    defaults = {k: v["default"] for k, v in configurable.items()}

    if not profile_settings_row:
        return defaults

    try:
        overrides = _json.loads(profile_settings_row.settings_json)
    except (ValueError, TypeError):
        return defaults

    merged = dict(defaults)
    for key, val in overrides.items():
        if key in configurable:
            merged[key] = val
    return merged