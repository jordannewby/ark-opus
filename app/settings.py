import os
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path, override=True)

def get_bool_env(key: str, default: bool = False) -> bool:
    val = os.getenv(key)
    return val.lower() in ("true", "1", "yes") if val else default

DEBUG_MODE = get_bool_env("ARES_DEBUG", True) # Defaulting to True for testing
DATAFORSEO_CONTENT_ANALYSIS_ENABLED = get_bool_env("DATAFORSEO_CONTENT_ANALYSIS_ENABLED", False) # Additive feature flag

def get_clean_env(key: str) -> str | None:
    val = os.getenv(key)
    if val:
        # Strip double quotes, single quotes, and surrounding whitespace
        return val.strip(' "\'')
    return None

GEMINI_API_KEY = get_clean_env("GEMINI_API_KEY")
DEEPSEEK_API_KEY = get_clean_env("DEEPSEEK_API_KEY")
DATAFORSEO_LOGIN = get_clean_env("DATAFORSEO_LOGIN")
DATAFORSEO_PASSWORD = get_clean_env("DATAFORSEO_PASSWORD")
EXA_API_KEY = get_clean_env("EXA_API_KEY")
ANTHROPIC_API_KEY = get_clean_env("ANTHROPIC_API_KEY")

if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY is missing.")
if not DEEPSEEK_API_KEY:
    raise ValueError("DEEPSEEK_API_KEY is missing.")
# Note: DATAFORSEO credentials still loaded for ResearchAgent (SERP tools)
# Validation removed - source verification no longer requires DataForSEO
if not EXA_API_KEY:
    raise ValueError("EXA_API_KEY is missing.")
if not ANTHROPIC_API_KEY:
    raise ValueError("ANTHROPIC_API_KEY is missing.")