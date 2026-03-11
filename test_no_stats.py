import asyncio
import os
import sys

# Add the project root to the python path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.services.writer_service import WriterService

class MockQuery:
    def filter(self, *args, **kwargs):
        return self
    def all(self):
        return []

class MockDB:
    def query(self, *args, **kwargs):
        return MockQuery()

async def main():
    # Load .env manually if needed, or assume it's loaded.
    from dotenv import load_dotenv
    load_dotenv()
    
    db = MockDB()
    writer = WriterService(db)
    
    blueprint = {
        "entities": ["cybersecurity", "data breach", "network defense"],
        "semantic_keywords": ["prevent cyber attacks", "protect sensitive data", "hacker methodology"],
        "information_gap": "Many small businesses think they are too small to be targeted, but in reality, hackers often choose them because they have weak security practices."
    }
    
    print("Starting generation...")
    text = ""
    async for event in writer.produce_article(blueprint):
        if event.get("type") == "content" and "data" in event and event["data"] != "RETRY_CLEAR":
            text += event["data"]
            print(event["data"], end="", flush=True)
        elif event.get("type") == "debug":
            print(f"\n[DEBUG] {event['message']}\n")
    
    print("\n\n--- Done ---")
    
    # Check for specific numbers or percentages
    import re
    stats = re.findall(r'\d+%|\$\d+(?:\.\d+)?(?:k|m|b| million| billion)?', text.lower())
    if stats:
        print(f"\nWARNING: Found potential fabricated stats: {stats}")
    else:
        print("\nSUCCESS: No percentages or dollar amounts found.")

if __name__ == "__main__":
    asyncio.run(main())
