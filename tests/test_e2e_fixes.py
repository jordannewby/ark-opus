"""E2E test to verify all 6 bug fixes from the plan."""
import asyncio
import json
import re
import sys
import time

# Fix Windows cp1252 encoding crash on Unicode chars
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')
import httpx

BASE_URL = "http://localhost:8000"

BANNED_WORDS = [
    "delve", "tapestry", "landscape", "multifaceted", "comprehensive",
    "holistic", "navigate", "crucial", "in conclusion", "ultimately",
    "fast-paced world", "digital age", "game-changer",
    "robust", "seamless", "synergy", "leverage", "scalable",
    "foster", "optimize", "ecosystem", "paradigm",
    "it's worth noting", "it's important to note", "it is worth noting",
    "whether you're a", "in the ever-evolving",
    "when it comes to", "at the end of the day", "let's face it",
    "in today's world", "in today's digital landscape",
    "it cannot be overstated", "needless to say",
]


async def test_generation():
    keyword = sys.argv[1] if len(sys.argv) > 1 else "ai-agent-frameworks"
    payload = {
        "keyword": keyword,
        "niche": "ai",
        "profile_name": "test_e2e",
    }

    print("=" * 80)
    print(f"Starting generation for: {payload['keyword']}")
    print(f"Niche: {payload['niche']}")
    print("=" * 80)

    events = []
    content_chunks = []
    errors = []
    complete_data = None
    phase_times = {}
    start = time.time()

    async with httpx.AsyncClient(timeout=1800.0, follow_redirects=True) as client:
        resp = await client.get(f"{BASE_URL}/health")
        print(f"HTTP Status: {resp.status_code}")

        async with client.stream("POST", f"{BASE_URL}/generate", json=payload) as response:
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                try:
                    data = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue

                events.append(data)
                evt = data.get("event", "")
                elapsed = round(time.time() - start, 1)

                if evt == "content":
                    content_chunks.append(data.get("data", ""))
                elif evt == "debug":
                    msg = data.get("message", "")
                    print(f"[{elapsed}s] {msg}")
                elif evt == "error":
                    errors.append(data.get("message", ""))
                    print(f"[{elapsed}s] ERROR: {data.get('message', '')}")
                elif evt == "control":
                    action = data.get("action", "")
                    print(f"[{elapsed}s] CONTROL: {action}")
                    if "retry_clear" in str(action):
                        content_chunks.clear()  # Reset for next iteration
                elif evt == "phase1_start":
                    phase_times["p1_start"] = elapsed
                    print(f"[{elapsed}s] PHASE 1 START: Gathering intelligence and analyzing context...")
                elif evt == "phase1_5_start":
                    phase_times["p15_start"] = elapsed
                    print(f"[{elapsed}s] PHASE 1.5 START: Verifying source credibility...")
                elif evt == "phase1_5_complete":
                    phase_times["p15_end"] = elapsed
                    verified = data.get("verified_count", 0)
                    rejected = data.get("rejected_count", 0)
                    avg = data.get("avg_credibility", 0)
                    print(f"[{elapsed}s] PHASE 1.5 COMPLETE: verified={verified}, rejected={rejected}, avg={avg}")
                elif evt == "fact_verification_start":
                    print(f"[{elapsed}s] FACT VERIFICATION START: Verifying extracted facts...")
                elif evt == "fact_verification_complete":
                    v = data.get("verified", 0)
                    u = data.get("unverifiable", 0)
                    c = data.get("corrected", 0)
                    print(f"[{elapsed}s] FACT VERIFICATION DONE: {v}/{v+u+c} facts independently verified, {u} unverifiable, {c} corrected")
                elif evt == "phase2_start":
                    phase_times["p2_start"] = elapsed
                    print(f"[{elapsed}s] PHASE 2 START: Mapping psychological blueprint...")
                elif evt == "phase2_complete":
                    phase_times["p2_end"] = elapsed
                    bp = data.get("blueprint", {})
                    sections = bp.get("outline_structure", []) if isinstance(bp, dict) else []
                    print(f"[{elapsed}s] PHASE 2 COMPLETE: {len(sections)} outline sections")
                    for i, s in enumerate(sections, 1):
                        heading = s.get("heading", str(s)) if isinstance(s, dict) else str(s)
                        print(f"  Section {i}: {heading[:60]}")
                elif evt == "phase3_start":
                    phase_times["p3_start"] = elapsed
                    print(f"[{elapsed}s] PHASE 3 START: Drafting final prose...")
                elif evt == "complete":
                    complete_data = data
                    post = data.get("post", {})
                    print(f"[{elapsed}s] COMPLETE: post_id={post.get('id') if isinstance(post, dict) else None}")
                    break

    total_time = round(time.time() - start, 1)
    streamed_article = "".join(content_chunks)
    # Use actual saved post content for validation (sanitized), fall back to streamed
    post_content = ""
    if complete_data:
        post_obj = complete_data.get("post", {})
        if isinstance(post_obj, dict):
            post_content = post_obj.get("content", "")
    article = post_content if post_content else streamed_article

    # Count events
    event_counts = {}
    for e in events:
        k = e.get("event", e.get("type", "unknown"))
        event_counts[k] = event_counts.get(k, 0) + 1

    print("=" * 80)
    print(f"Total time: {total_time}s")
    print(f"Total SSE events: {len(events)}")
    print(f"Content chunks: {len(content_chunks)}")
    print(f"Event breakdown:")
    for k, v in sorted(event_counts.items()):
        print(f"  {k}: {v}")

    # ==================== VALIDATION ====================
    print("\nVALIDATION:")
    all_pass = True

    # V1: Phase 1 (Research)
    p1 = "phase1_start" in [e.get("event") for e in events]
    print(f"  Phase 1 (Research):       {'PASS' if p1 else 'FAIL'}")
    all_pass = all_pass and p1

    # V2: Phase 1.5 (Verification)
    p15 = "phase1_5_complete" in [e.get("event") for e in events]
    print(f"  Phase 1.5 (Verification): {'PASS' if p15 else 'FAIL'}")
    all_pass = all_pass and p15

    # V3: Phase 2 (Psychology)
    p2 = "phase2_complete" in [e.get("event") for e in events]
    print(f"  Phase 2 (Psychology):     {'PASS' if p2 else 'FAIL'}")
    all_pass = all_pass and p2

    # V3b: Check H2 headings in phase2_complete blueprint
    p2_data = next((e for e in events if e.get("event") == "phase2_complete"), {})
    blueprint = p2_data.get("blueprint", {})
    outline_sections = blueprint.get("outline_structure", []) if isinstance(blueprint, dict) else []
    h2_in_outline = sum(1 for s in outline_sections if isinstance(s, dict) and s.get("heading", "").startswith("H2"))
    # Also check from flat outline_sections if present
    if h2_in_outline == 0:
        flat_sections = p2_data.get("outline_sections", [])
        h2_in_outline = sum(1 for s in flat_sections if isinstance(s, str) and s.strip().startswith("H2"))
    h2_outline_pass = h2_in_outline >= 5
    print(f"  Blueprint H2 count:       {'PASS' if h2_outline_pass else 'FAIL'} ({h2_in_outline} H2 headings in blueprint)")
    all_pass = all_pass and h2_outline_pass

    # V4: Phase 3 (Writer)
    p3 = len(content_chunks) > 0
    print(f"  Phase 3 (Writer):         {'PASS' if p3 else 'FAIL'}")
    all_pass = all_pass and p3

    # V5: Complete event (Fix 1 - session crash)
    complete_pass = complete_data is not None
    print(f"  Complete event:           {'PASS' if complete_pass else 'FAIL'}")
    all_pass = all_pass and complete_pass

    # V6: No error events (Fix 1)
    no_errors = len(errors) == 0
    print(f"  No error events:          {'PASS' if no_errors else 'FAIL'}{'' if no_errors else ' - see errors above'}")
    all_pass = all_pass and no_errors

    # V7: H2 headings in article (Fix 3)
    h2_matches = re.findall(r'^## .+', article, re.MULTILINE)
    h2_pass = len(h2_matches) >= 5
    print(f"  Article H2 count (>=5):   {'PASS' if h2_pass else 'FAIL'} ({len(h2_matches)} H2 headings)")
    all_pass = all_pass and h2_pass

    # V8: No banned words (Fix 4)
    article_lower = article.lower()
    found_banned = [w for w in BANNED_WORDS if w in article_lower]
    no_banned = len(found_banned) == 0
    print(f"  No banned words:          {'PASS' if no_banned else 'FAIL'}{'' if no_banned else f' - found: {found_banned}'}")
    all_pass = all_pass and no_banned

    # V9: Word count
    word_count = len(article.split())
    wc_pass = word_count >= 1500
    print(f"  Word count (>=1500):      {'PASS' if wc_pass else 'FAIL'} ({word_count} words)")
    all_pass = all_pass and wc_pass

    # V10: Post data checks (Fix 1, Fix 5, Fix 7)
    if complete_data:
        post_data = complete_data.get("post", {})
        post_id = post_data.get("id") if isinstance(post_data, dict) else None
        readability = post_data.get("readability_score")
        research_run = post_data.get("research_run_id")

        read_pass = readability is not None
        print(f"  readability_score:        {'PASS' if read_pass else 'FAIL'} ({readability})")
        all_pass = all_pass and read_pass

        rr_pass = research_run is not None
        print(f"  research_run_id:          {'PASS' if rr_pass else 'FAIL'} ({research_run})")
        all_pass = all_pass and rr_pass
    else:
        print(f"  readability_score:        FAIL (no complete event)")
        print(f"  research_run_id:          FAIL (no complete event)")
        all_pass = False

    # V11: Writer iteration count (should pass SEO gate in <=3 attempts now)
    writer_iters = [e for e in events if e.get("event") == "debug" and "Writer Iteration" in e.get("message", "") and "Starting" in e.get("message", "")]
    iter_count = len(writer_iters)
    iter_pass = iter_count <= 3
    print(f"  Writer iterations (<=3):  {'PASS' if iter_pass else 'WARN'} ({iter_count} iterations)")

    print(f"\n{'=' * 80}")
    print(f"OVERALL: {'ALL PASS' if all_pass else 'SOME FAILURES'}")
    print(f"{'=' * 80}")

    if errors:
        print("\nERRORS FOUND:")
        for e in errors:
            print(f"  - {e}")


if __name__ == "__main__":
    asyncio.run(test_generation())
