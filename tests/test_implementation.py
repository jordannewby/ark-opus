"""
Test script for Phase 1, 2, and 3 implementation
Tests iterative search, citation validation v2, jargon detection, and domain caching
"""
import asyncio
import json
import httpx
from datetime import datetime

BASE_URL = "http://localhost:8000"
PROFILE = "test_profile"

async def test_niche_topic():
    """Test 1: Niche topic that should trigger iterative source search"""
    print("\n" + "="*80)
    print("[TEST 1] NICHE TOPIC: CMMC compliance for DoD contractors")
    print("Expected: Iterative search triggered, threshold decay, 3 sources found")
    print("="*80 + "\n")

    payload = {
        "keyword": "CMMC compliance for DoD contractors",
        "niche": "cybersecurity",
        "profile_name": PROFILE,
        "additional_context": "Focus on recent 2024-2025 requirements",
    }

    async with httpx.AsyncClient(timeout=600.0, follow_redirects=True) as client:
        async with client.stream("POST", f"{BASE_URL}/generate", json=payload) as response:
            iteration_count = 0
            sources_found = 0
            threshold_decay_detected = False
            cache_hits = 0

            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    try:
                        data = json.loads(line[6:])
                        event_type = data.get("event") or data.get("type") or data.get("status")
                        message = data.get("message", "")

                        # Monitor iterative search
                        if "iterative" in message.lower() or "iteration" in message.lower():
                            iteration_count += 1
                            print(f"[ITERATIVE SEARCH] {message}")

                        # Monitor threshold decay
                        if "threshold" in message.lower() and ("40" in message or "35" in message):
                            threshold_decay_detected = True
                            print(f"[THRESHOLD DECAY] {message}")

                        # Monitor sources found
                        if event_type == "sources_verified":
                            sources_found = data.get("count", 0)
                            print(f"[SOURCES VERIFIED] Found {sources_found} sources")

                        # Monitor cache hits
                        if "cache" in message.lower() and "hit" in message.lower():
                            cache_hits += 1
                            print(f"[CACHE HIT] {message}")

                        # Show key events
                        if event_type in ["source_backfill_start", "debug", "error"]:
                            print(f"[{event_type.upper()}] {message}")

                        # Final result
                        if event_type == "complete":
                            print(f"\n[COMPLETE] Article generated successfully")
                            print(f"Post ID: {data.get('post_id')}")
                            break

                    except json.JSONDecodeError:
                        continue

            print(f"\n[RESULTS]")
            print(f"  Iterations: {iteration_count}")
            print(f"  Sources found: {sources_found}")
            print(f"  Threshold decay: {'Yes' if threshold_decay_detected else 'No'}")
            print(f"  Cache hits: {cache_hits}")
            print(f"  Status: {'PASS' if sources_found >= 3 else 'FAIL'}")


async def test_technical_content():
    """Test 2: Technical content that should trigger jargon detection"""
    print("\n" + "="*80)
    print("[TEST 2] TECHNICAL CONTENT: Kubernetes security hardening")
    print("Expected: Jargon detection triggered, early exit after 2 attempts")
    print("="*80 + "\n")

    payload = {
        "keyword": "Kubernetes security hardening best practices",
        "niche": "cloud-computing",
        "profile_name": PROFILE,
        "additional_context": "Focus on pod security policies and RBAC",
    }

    async with httpx.AsyncClient(timeout=600.0, follow_redirects=True) as client:
        async with client.stream("POST", f"{BASE_URL}/generate", json=payload) as response:
            readability_attempts = 0
            jargon_detected = False
            early_exit = False

            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    try:
                        data = json.loads(line[6:])
                        event_type = data.get("event") or data.get("type") or data.get("status")
                        message = data.get("message", "")

                        # Monitor readability attempts
                        if "readability" in message.lower() or "simplify" in message.lower():
                            if "attempt" in message.lower() or "retrying" in message.lower():
                                readability_attempts += 1
                                print(f"[READABILITY] Attempt {readability_attempts}: {message}")

                        # Monitor jargon detection
                        if "jargon" in message.lower() or "technical" in message.lower():
                            jargon_detected = True
                            print(f"[JARGON DETECTED] {message}")

                        # Monitor early exit
                        if "early" in message.lower() and "exit" in message.lower():
                            early_exit = True
                            print(f"[EARLY EXIT] {message}")

                        # Show key events
                        if event_type in ["debug", "error"]:
                            print(f"[{event_type.upper()}] {message}")

                        # Final result
                        if event_type == "complete":
                            print(f"\n[COMPLETE] Article generated successfully")
                            print(f"Post ID: {data.get('post_id')}")
                            break

                    except json.JSONDecodeError:
                        continue

            print(f"\n[RESULTS]")
            print(f"  Readability attempts: {readability_attempts}")
            print(f"  Jargon detected: {'Yes' if jargon_detected else 'No'}")
            print(f"  Early exit: {'Yes' if early_exit else 'No'}")
            print(f"  Status: {'PASS' if (jargon_detected and readability_attempts <= 2) else 'PARTIAL' if readability_attempts <= 3 else 'FAIL'}")


async def test_citation_validation():
    """Test 3: Citation validation with varied anchor text"""
    print("\n" + "="*80)
    print("[TEST 3] CITATION VALIDATION: Domain-based matching")
    print("Expected: Pass validation despite anchor text variation")
    print("="*80 + "\n")

    payload = {
        "keyword": "cloud migration cost optimization strategies",
        "niche": "cloud-computing",
        "profile_name": PROFILE,
        "additional_context": "Include specific statistics and data points",
    }

    async with httpx.AsyncClient(timeout=600.0, follow_redirects=True) as client:
        async with client.stream("POST", f"{BASE_URL}/generate", json=payload) as response:
            citation_attempts = 0
            validation_passed = False
            domain_validation_used = False

            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    try:
                        data = json.loads(line[6:])
                        event_type = data.get("event") or data.get("type") or data.get("status")
                        message = data.get("message", "")

                        # Monitor citation validation
                        if "citation" in message.lower():
                            citation_attempts += 1
                            print(f"[CITATION] {message}")

                            if "domain" in message.lower():
                                domain_validation_used = True
                                print(f"[DOMAIN VALIDATION] v2 validation active")

                            if "passed" in message.lower() or "success" in message.lower():
                                validation_passed = True

                        # Show key events
                        if event_type in ["debug", "error"]:
                            print(f"[{event_type.upper()}] {message}")

                        # Final result
                        if event_type == "complete":
                            print(f"\n[COMPLETE] Article generated successfully")
                            print(f"Post ID: {data.get('post_id')}")
                            break

                    except json.JSONDecodeError:
                        continue

            print(f"\n[RESULTS]")
            print(f"  Citation attempts: {citation_attempts}")
            print(f"  Domain validation used: {'Yes' if domain_validation_used else 'No'}")
            print(f"  Validation passed: {'Yes' if validation_passed else 'No'}")
            print(f"  Status: {'PASS' if validation_passed and citation_attempts <= 2 else 'FAIL'}")


async def main():
    print("\n" + "="*80)
    print("ARES ENGINE - IMPLEMENTATION TEST SUITE")
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)

    try:
        # Test 1: Iterative source search
        await test_niche_topic()
        await asyncio.sleep(2)

        # Test 2: Jargon detection and early exit
        await test_technical_content()
        await asyncio.sleep(2)

        # Test 3: Domain-based citation validation
        await test_citation_validation()

    except Exception as e:
        print(f"\n[ERROR] Test suite failed: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "="*80)
    print(f"Test suite completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
