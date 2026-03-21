"""Quick test to verify duplicate prevention fix"""
import asyncio
import json
import httpx

async def test():
    # Use same profile that had duplicates before
    payload = {
        "keyword": "cloud security best practices 2025",
        "niche": "cybersecurity",
        "profile_name": "dedup_test",
        "additional_context": "Focus on Zero Trust architecture",
    }

    print("\n" + "="*80)
    print("Testing Duplicate Prevention Fix")
    print("="*80 + "\n")

    async with httpx.AsyncClient(timeout=180.0, follow_redirects=True) as client:
        async with client.stream("POST", "http://localhost:8000/generate", json=payload) as response:
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    try:
                        data = json.loads(line[6:])
                        event = data.get("event") or data.get("type") or data.get("status")
                        msg = data.get("message", "")

                        # Monitor for key events
                        if "dedup" in msg.lower() or "duplicate" in msg.lower():
                            print(f"✅ [DEDUP] {msg}")

                        if "iterative" in msg.lower() or "backfill" in msg.lower():
                            print(f"🔄 [ITERATIVE] {msg}")

                        if event == "sources_verified":
                            print(f"✅ [VERIFIED] {data.get('count')} sources found")

                        if event == "error":
                            if "UniqueViolation" in msg or "duplicate key" in msg:
                                print(f"❌ [BUG] Duplicate error still happening!")
                                print(msg[:200])
                                break
                            else:
                                print(f"⚠️  [ERROR] {msg[:150]}")

                        if event == "complete":
                            print(f"\n✅ [SUCCESS] Generation completed!")
                            print(f"Post ID: {data.get('post_id')}")
                            break

                    except json.JSONDecodeError:
                        continue

if __name__ == "__main__":
    asyncio.run(test())
