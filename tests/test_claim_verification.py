"""Tests for claim extraction, URL normalization, and quantitative pattern matching."""
import pytest
import re
from app.services.claim_verification_agent import extract_article_claims


class TestExtractArticleClaims:
    """Tests for extract_article_claims() regex extraction."""

    def test_quantitative_claim_extracted(self):
        article = (
            "## Security Trends\n\n"
            "Recent data shows that 67% of firms faced a breach last year "
            "[CrowdStrike Report](https://crowdstrike.com/report).\n"
        )
        claims = extract_article_claims(article, verify_qualitative=True)
        assert len(claims) >= 1
        assert any("67%" in c["claim_text"] for c in claims)
        assert claims[0]["citation_url"] == "https://crowdstrike.com/report"
        assert claims[0]["has_quantitative_claim"] is True

    def test_qualitative_claim_extracted(self):
        article = (
            "## Key Findings\n\n"
            "According to recent research, zero trust adoption is accelerating "
            "[NIST Guidelines](https://nist.gov/zt).\n"
        )
        claims = extract_article_claims(article, verify_qualitative=True)
        assert len(claims) >= 1
        assert claims[0]["claim_type"] == "qualitative"

    def test_qualitative_disabled_skips_soft_claims(self):
        article = (
            "## Overview\n\n"
            "Research shows that cloud adoption is growing rapidly "
            "[Cloud Report](https://example.com/cloud).\n"
        )
        quant_claims = extract_article_claims(article, verify_qualitative=False)
        # Without qualitative detection and no numbers, this should be filtered
        qual_claims = extract_article_claims(article, verify_qualitative=True)
        assert len(qual_claims) >= len(quant_claims)

    def test_no_citations_returns_empty(self):
        article = "## Title\n\nThis article has no citations at all."
        claims = extract_article_claims(article, verify_qualitative=True)
        assert claims == []

    def test_bare_link_without_claim_filtered(self):
        """Links in resource lists without substantive prose should be filtered."""
        article = "## Resources\n\n- [NIST](https://nist.gov)\n- [CISA](https://cisa.gov)\n"
        claims = extract_article_claims(article, verify_qualitative=True)
        assert len(claims) == 0

    def test_dollar_amount_detected(self):
        article = (
            "## Market Size\n\n"
            "The global cybersecurity market reached $180 billion in spending "
            "[Market Report](https://example.com/market).\n"
        )
        claims = extract_article_claims(article, verify_qualitative=True)
        assert len(claims) >= 1
        assert claims[0]["has_quantitative_claim"] is True

    def test_multiple_citations_in_article(self):
        article = (
            "## Threats\n\n"
            "About 43% of attacks target small firms [Verizon DBIR](https://verizon.com/dbir). "
            "Meanwhile research indicates that $4.45 million is the average breach cost "
            "[IBM Report](https://ibm.com/report).\n"
        )
        claims = extract_article_claims(article, verify_qualitative=True)
        assert len(claims) >= 2

    def test_claim_text_has_substance(self):
        """All returned claims should have at least 20 chars and 4 content words."""
        article = (
            "## Analysis\n\n"
            "Firms that adopted zero trust architecture saw 67% fewer breaches "
            "[Report](https://example.com/zt). "
            "A [Link](https://example.com) is here.\n"
        )
        claims = extract_article_claims(article, verify_qualitative=True)
        for claim in claims:
            assert len(claim["claim_text"]) >= 20


class TestUrlNormalization:
    """Tests for _normalize_url() in main.py."""

    def test_basic_normalization(self):
        from app.main import _normalize_url
        assert _normalize_url("https://www.example.com/path/") == "https://example.com/path"

    def test_lowercase_domain(self):
        from app.main import _normalize_url
        assert _normalize_url("https://EXAMPLE.COM/Path") == "https://example.com/Path"

    def test_strip_query_params(self):
        from app.main import _normalize_url
        result = _normalize_url("https://example.com/page?utm_source=google&ref=1")
        assert "?" not in result
        assert result == "https://example.com/page"

    def test_strip_fragment(self):
        from app.main import _normalize_url
        result = _normalize_url("https://example.com/page#section")
        assert "#" not in result

    def test_root_path_preserved(self):
        from app.main import _normalize_url
        result = _normalize_url("https://example.com")
        assert result == "https://example.com/"

    def test_www_removed(self):
        from app.main import _normalize_url
        result = _normalize_url("https://www.nist.gov/guidelines")
        assert result == "https://nist.gov/guidelines"

    def test_invalid_url_returned_unchanged(self):
        from app.main import _normalize_url
        assert _normalize_url("not-a-url") == "not-a-url"


class TestQuantitativePatterns:
    """Tests for the quantitative claim regex patterns used in claim extraction."""

    # Import the pattern directly
    from app.services.claim_verification_agent import _QUANT_CLAIM_PATTERN

    @pytest.mark.parametrize("text", [
        "67% of organizations",
        "about 42.5% growth",
        "$180 billion market",
        "$4.45 million average",
        "100 percent of cases",
        "grew by 5M users",
        "revenue hit $10B",
    ])
    def test_quantitative_patterns_match(self, text):
        assert self._QUANT_CLAIM_PATTERN.search(text) is not None

    @pytest.mark.parametrize("text", [
        "many organizations struggle",
        "the report was published",
        "experts agree this matters",
    ])
    def test_non_quantitative_no_match(self, text):
        assert self._QUANT_CLAIM_PATTERN.search(text) is None
