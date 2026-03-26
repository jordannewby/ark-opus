import os
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path, override=True)

def get_bool_env(key: str, default: bool = False) -> bool:
    val = os.getenv(key)
    return val.lower() in ("true", "1", "yes") if val else default

DEBUG_MODE = get_bool_env("ARES_DEBUG", False)
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
if not DEEPSEEK_API_KEY:
    raise ValueError("DEEPSEEK_API_KEY is missing.")
# Note: DATAFORSEO credentials still loaded for ResearchAgent (SERP tools)
# Validation removed - source verification no longer requires DataForSEO
if not EXA_API_KEY:
    raise ValueError("EXA_API_KEY is missing.")
if not ANTHROPIC_API_KEY:
    raise ValueError("ANTHROPIC_API_KEY is missing.")

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
CLAIM_TEXT_SIMILARITY_THRESHOLD = 0.2
LLM_SOURCE_CONTEXT_CHARS = 5000
MAX_UNCITED_CLAIMS = 0

# Source credibility penalties
BLOG_DOMAIN_PENALTY = 10.0        # pts deducted for blog.* subdomains
BLOG_PATH_PENALTY = 5.0           # pts deducted for /blog/ in URL path
UNSOURCED_CLAIMS_PENALTY = 15.0   # pts deducted for Tier 0 with claim_sourcing < 0.4

# Feedback
RULE_CONSOLIDATION_THRESHOLD = 20