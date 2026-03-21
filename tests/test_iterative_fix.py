"""Test iterative search with duplicate prevention fix"""
import asyncio
import json
import httpx

async def test():
    payload = {
        "keyword": "NIST SP 800-171 compliance for manufacturing SMBs",
        "niche": "cybersecurity",
        "profile_name": "test_fix",
        "additional_context": "Focus on small manufacturers",
    }

    print("\n" + "="*80)
    print("Testing Iterative Search with Duplicate Prevention")
    print("Topic: NIST SP 800-171 for manufacturing SMBs (very niche)")
    print("="*80 + "\n")

    async with httpx.AsyncClient(timeout=600.0, follow_redirects=True) as client:
        async with client.stream("POST", "http://localhost:8000/generate", json=payload) as response:
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    try:
                        data = json.loads(line[6:])
                        event = data.get("event") or data.get("type") or data.get("status")
                        msg = data.get("message", "")

                        # Print all events for debugging
                        if event in ["source_backfill_start", "sources_verified", "complete", "error"]:
                            print(f"\n[{event.upper()}]")
                            print(f"  Message: {msg}")
                            if event == "sources_verified":
                                print(f"  Count: {data.get('count')}")

                        if "iterative" in msg.lower() or "iteration" in msg.lower():
                            print(f"[ITERATIVE] {msg}")

                        if "dedup" in msg.lower() or "duplicate" in msg.lower():
                            print(f"[DEDUP] {msg}")

                        if "cache" in msg.lower() and "hit" in msg.lower():
                            print(f"[CACHE-HIT] {msg}")

                        if event == "error":
                            print(f"\n[ERROR DETAIL]")
                            print(msg[:500])
                            break

                        if event == "complete":
                            print(f"\n[SUCCESS] Generation completed!")
                            print(f"Post ID: {data.get('post_id')}")
                            break

                    except json.JSONDecodeError:
                        continue

if __name__ == "__main__":
    asyncio.run(test())
