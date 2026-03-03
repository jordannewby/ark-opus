import os
import sys
from pathlib import Path

# Add the project root to sys.path so we can import app.settings
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import settings

key = os.getenv("GEMINI_API_KEY")
if key:
    print(f"Key found: {key[:5]}...")
else:
    print("Key not found in os.environ")
