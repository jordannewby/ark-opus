import os
from pathlib import Path
from dotenv import load_dotenv

# Resolve the absolute path to the root directory's .env file
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# 1. Primary Model (Flash - Writing/General)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# 2. Pro Model (Psychology Agent - Logic/Strategy)
GEMINI_PSYCH_API_KEY = os.getenv("GEMINI_PSYCH_API_KEY")

# Fallback: Manual Pure Text parsing if dotenv fails due to Windows encoding/quotes
if (not GEMINI_API_KEY or not GEMINI_PSYCH_API_KEY) and env_path.exists():
    with open(env_path, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
        for line in lines:
            line = line.strip()
            # Parse General Flash Key
            if line.startswith("GEMINI_API_KEY="):
                parts = line.split("=", 1)
                if len(parts) == 2:
                    GEMINI_API_KEY = parts[1].strip().strip("'").strip('"')
                    os.environ["GEMINI_API_KEY"] = GEMINI_API_KEY

            # Parse Psychology Pro Key
            if line.startswith("GEMINI_PSYCH_API_KEY="):
                parts = line.split("=", 1)
                if len(parts) == 2:
                    GEMINI_PSYCH_API_KEY = parts[1].strip().strip("'").strip('"')
                    os.environ["GEMINI_PSYCH_API_KEY"] = GEMINI_PSYCH_API_KEY

# Final Validation
if not GEMINI_API_KEY:
    raise ValueError(f"GEMINI_API_KEY is missing in: {env_path}")
if not GEMINI_PSYCH_API_KEY:
    raise ValueError(f"GEMINI_PSYCH_API_KEY is missing in: {env_path}")

BRAVE_API_KEY = os.getenv("BRAVE_API_KEY") # Ensure this is also captured