import os
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path, override=True)

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
BRAVE_API_KEY = get_clean_env("BRAVE_API_KEY")

GOGGLE_MAP = {
    "default": "https://gist.githubusercontent.com/jordannewby/fea9a69f11623139000599fad46fbc31/raw/3dc9f41319dc70a7679ebc5412d8a4b0ee30da4a/gistfile1.txt",
    "marketing": "https://gist.githubusercontent.com/jordannewby/0f11c19387aae2faa202f4d5df547f3d/raw/18e935934340a80b72cfa0cd1464c67918190b17/marketing",
    "cybersecurity": "https://gist.githubusercontent.com/jordannewby/5fd8992c925c3b6a03a079794ef4927f/raw/aa28023afdcd2a605e1a51474ddce4b4c60d8f28/cybersecurity",
    "technical": "https://gist.githubusercontent.com/jordannewby/fea9a69f11623139000599fad46fbc31/raw/3dc9f41319dc70a7679ebc5412d8a4b0ee30da4a/gistfile1.txt"
}

if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY is missing.")
if not DEEPSEEK_API_KEY:
    raise ValueError("DEEPSEEK_API_KEY is missing.")
if not DATAFORSEO_LOGIN or not DATAFORSEO_PASSWORD:
    raise ValueError("DATAFORSEO credentials missing.")
if not BRAVE_API_KEY:
    raise ValueError("BRAVE_API_KEY is missing.")