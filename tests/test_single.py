"""Simple test to verify implementation features"""
import asyncio
import json
import httpx

BASE_URL = "http://localhost:8000"

async def test_generation():
    """Test generation with monitoring of new features"""

    payload = {
        "keyword": "cloud migration security best practices 2025",
        "niche": "cloud-computing",
        "profile_name": "test_impl",
        "additional_context": "Focus on cost optimization and security",
    }

    print("\n" + "="*80)
    print("Testing Ares Engine with cloud migration topic")
    print("="*80 + "\n")

    events = []

    async with httpx.AsyncClient(timeout=600.0, follow_redirects=True) as client:
        async with client.stream("POST", f"{BASE_URL}/generate", json=payload) as response:
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    try:
                        data = json.loads(line[6:])
                        events.append(data)

                        event_type = data.get("event") or data.get("type") or data.get("status")
                        message = data.get("message", "")

                        # Print key events
                        if event_type in ["sources_verified", "complete", "error", "source_backfill_start"]:
                            print(f"[{event_type.upper()}] {data}")

                        if "cache" in message.lower() and "hit" in message.lower():
                            print(f"[CACHE HIT] {message}")

                        if "jargon" in message.lower():
                            print(f"[JARGON DETECTION] {message}")

                        if "iteration" in message.lower():
                            print(f"[ITERATIVE SEARCH] {message}")

                        if "domain" in message.lower() and "validation" in message.lower():
                            print(f"[CITATION V2] {message}")

                        if event_type == "complete":
                            print(f"\n{'='*80}")
                            print("GENERATION COMPLETE")
                            print(f"Post ID: {data.get('post_id')}")
                            print(f"Total events: {len(events)}")
                            print(f"{'='*80}\n")
                            break

                    except json.JSONDecodeError:
                        continue

if __name__ == "__main__":
    asyncio.run(test_generation())
