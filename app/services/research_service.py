"""
ResearchAgent — uses Brave Web Search API to gather competitive intel for a keyword.

Returns structured JSON with:
  - Top 5 competitor H2/H3 headers
  - "People Also Ask" questions
  - 10 key semantic entities

Results are cached in blog.db (research_cache table) to stay within our $10 budget.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy.orm import Session

from ..models import ResearchCache

BRAVE_API_KEY = os.getenv(
    "BRAVE_API_KEY", "REDACTED_BRAVE_KEY"
)
BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
CACHE_TTL_HOURS = 24


class ResearchAgent:
    """Gathers SEO research data for a keyword via Brave Search."""

    def __init__(self, db: Session):
        self.db = db

    async def research(self, keyword: str) -> dict:
        """Run full research pipeline for *keyword*. Returns cached data if fresh."""
        cached = self._get_cached(keyword)
        if cached is not None:
            return cached

        search_results = await self._brave_web_search(keyword)

        result = {
            "keyword": keyword,
            "competitor_headers": self._extract_headers(search_results),
            "people_also_ask": self._extract_paa(search_results),
            "semantic_entities": self._extract_entities(search_results),
        }

        self._save_cache(keyword, result)
        return result

    # ------------------------------------------------------------------
    # Brave Search API
    # ------------------------------------------------------------------

    async def _brave_web_search(self, query: str) -> dict:
        """Call Brave Web Search API and return raw JSON response."""
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": BRAVE_API_KEY,
        }
        params = {"q": query, "count": 10}

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                BRAVE_SEARCH_URL, headers=headers, params=params
            )
            resp.raise_for_status()
            return resp.json()

    # ------------------------------------------------------------------
    # Extraction helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_headers(data: dict) -> list[dict]:
        """
        Pull H2/H3-style headers from search result snippets and titles.

        Brave doesn't return raw HTML, so we treat each result title as a
        competitor H2 and split multi-sentence descriptions to approximate
        sub-headings (H3).
        """
        headers: list[dict] = []
        results = data.get("web", {}).get("results", [])

        for r in results[:5]:
            entry = {"source": r.get("url", ""), "h2": r.get("title", "")}
            description = r.get("description", "")
            # Split on sentence boundaries to approximate H3s
            parts = re.split(r"(?<=[.!?])\s+", description)
            entry["h3s"] = [p.strip() for p in parts if len(p.strip()) > 20]
            headers.append(entry)

        return headers

    @staticmethod
    def _extract_paa(data: dict) -> list[str]:
        """
        Extract 'People Also Ask' questions.

        Brave surfaces related queries in the `query` section and
        sometimes in a `faq` or `discussions` block.
        """
        questions: list[str] = []

        # Related search suggestions
        for item in data.get("query", {}).get("related_queries", []):
            text = item if isinstance(item, str) else item.get("query", "")
            if text:
                questions.append(text)

        # FAQ results (if present)
        for faq in data.get("faq", {}).get("results", []):
            q = faq.get("question", "")
            if q:
                questions.append(q)

        # Deduplicate while preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for q in questions:
            low = q.lower()
            if low not in seen:
                seen.add(low)
                unique.append(q)

        return unique

    @staticmethod
    def _extract_entities(data: dict) -> list[str]:
        """
        Derive semantic entities from search results.

        We extract recurring nouns / noun-phrases from titles and
        descriptions by simple frequency analysis — no NLP library needed,
        keeping deps (and budget) lean.
        """
        stopwords = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "being", "have", "has", "had", "do", "does", "did", "will",
            "would", "could", "should", "may", "might", "shall", "can",
            "to", "of", "in", "for", "on", "with", "at", "by", "from",
            "as", "into", "through", "during", "before", "after", "and",
            "but", "or", "nor", "not", "so", "yet", "both", "either",
            "neither", "each", "every", "all", "any", "few", "more",
            "most", "other", "some", "such", "no", "only", "own", "same",
            "than", "too", "very", "just", "about", "above", "below",
            "between", "up", "down", "out", "off", "over", "under",
            "again", "further", "then", "once", "here", "there", "when",
            "where", "why", "how", "what", "which", "who", "whom", "this",
            "that", "these", "those", "it", "its", "i", "me", "my", "we",
            "our", "you", "your", "he", "him", "his", "she", "her", "they",
            "them", "their",
        }

        text_blob = ""
        for r in data.get("web", {}).get("results", []):
            text_blob += " " + r.get("title", "")
            text_blob += " " + r.get("description", "")

        words = re.findall(r"[A-Za-z]{3,}", text_blob)
        freq: dict[str, int] = {}
        for w in words:
            low = w.lower()
            if low not in stopwords:
                freq[low] = freq.get(low, 0) + 1

        ranked = sorted(freq.items(), key=lambda x: x[1], reverse=True)
        return [word for word, _ in ranked[:10]]

    # ------------------------------------------------------------------
    # Cache layer
    # ------------------------------------------------------------------

    def _get_cached(self, keyword: str) -> dict | None:
        """Return cached result if it exists and hasn't expired."""
        row = (
            self.db.query(ResearchCache)
            .filter(ResearchCache.keyword == keyword.lower())
            .first()
        )
        if row is None:
            return None

        age = datetime.now(timezone.utc) - row.created_at.replace(
            tzinfo=timezone.utc
        )
        if age > timedelta(hours=row.cache_ttl_hours):
            self.db.delete(row)
            self.db.commit()
            return None

        return json.loads(row.result_json)

    def _save_cache(self, keyword: str, result: dict) -> None:
        """Upsert research result into the cache table."""
        row = (
            self.db.query(ResearchCache)
            .filter(ResearchCache.keyword == keyword.lower())
            .first()
        )
        payload = json.dumps(result, ensure_ascii=False)

        if row:
            row.result_json = payload
            row.created_at = datetime.now(timezone.utc)
        else:
            row = ResearchCache(
                keyword=keyword.lower(),
                result_json=payload,
                cache_ttl_hours=CACHE_TTL_HOURS,
            )
            self.db.add(row)

        self.db.commit()
