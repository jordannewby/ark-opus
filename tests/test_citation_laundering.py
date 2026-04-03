"""Tests for citation laundering detection and attribution mismatch logic."""
import pytest
from app.services.source_verification_service import (
    detect_citation_laundering,
    detect_attribution_mismatches,
    extract_domain,
)


class TestDetectCitationLaundering:
    """Tests for detect_citation_laundering()."""

    def test_laundered_gartner_on_random_domain(self):
        result = detect_citation_laundering(
            "Gartner reports that 40% of SMBs will adopt AI agents",
            "randomsite.com",
        )
        assert result["is_laundered"] is True
        assert result["claimed_org"] == "gartner"
        assert result["source_domain"] == "randomsite.com"

    def test_legitimate_gartner_on_gartner_domain(self):
        result = detect_citation_laundering(
            "Gartner reports that 40% of SMBs will adopt AI agents",
            "gartner.com",
        )
        assert result["is_laundered"] is False

    def test_legitimate_subdomain_match(self):
        result = detect_citation_laundering(
            "According to NIST guidelines",
            "nvd.nist.gov",
        )
        assert result["is_laundered"] is False

    def test_org_in_anchor_not_text(self):
        result = detect_citation_laundering(
            "40% of organizations experienced a breach",
            "random-blog.com",
            citation_anchor="Gartner 2024",
        )
        assert result["is_laundered"] is True
        assert result["claimed_org"] == "gartner"

    def test_no_org_mentioned(self):
        result = detect_citation_laundering(
            "40% of organizations experienced a breach in 2024",
            "example.com",
        )
        assert result["is_laundered"] is False
        assert result["claimed_org"] is None

    def test_empty_text(self):
        result = detect_citation_laundering("", "example.com")
        assert result["is_laundered"] is False

    def test_case_insensitive_org_match(self):
        result = detect_citation_laundering(
            "GARTNER found that cloud adoption is rising",
            "blog.example.com",
        )
        assert result["is_laundered"] is True
        assert result["claimed_org"] == "gartner"

    def test_multiple_canonical_domains(self):
        """Google has multiple canonical domains — match any of them."""
        result = detect_citation_laundering(
            "Google research shows improved latency",
            "deepmind.com",
        )
        assert result["is_laundered"] is False

    def test_crowdstrike_on_crowdstrike(self):
        result = detect_citation_laundering(
            "CrowdStrike's 2024 threat report shows...",
            "crowdstrike.com",
        )
        assert result["is_laundered"] is False

    def test_crowdstrike_on_wrong_domain(self):
        result = detect_citation_laundering(
            "CrowdStrike's 2024 threat report shows...",
            "techblog.io",
        )
        assert result["is_laundered"] is True
        assert result["claimed_org"] == "crowdstrike"


class TestDetectAttributionMismatches:
    """Tests for detect_attribution_mismatches()."""

    def test_empty_claims(self):
        assert detect_attribution_mismatches([]) == []

    def test_no_org_in_claims(self):
        claims = [
            {
                "claim_text": "This is a generic claim about security",
                "citation_anchor": "Source 2024",
                "citation_url": "https://example.com/article",
            }
        ]
        assert detect_attribution_mismatches(claims) == []

    def test_mismatched_claim(self):
        claims = [
            {
                "claim_text": "Gartner predicts 40% AI adoption by 2025",
                "citation_anchor": "Gartner 2024",
                "citation_url": "https://random-blog.com/ai-stats",
            }
        ]
        result = detect_attribution_mismatches(claims)
        assert len(result) == 1
        assert result[0]["named_org"] == "gartner"
        assert result[0]["citation_domain"] == "random-blog.com"

    def test_legitimate_claim_no_mismatch(self):
        claims = [
            {
                "claim_text": "Gartner predicts 40% AI adoption",
                "citation_anchor": "Gartner",
                "citation_url": "https://gartner.com/report",
            }
        ]
        assert detect_attribution_mismatches(claims) == []

    def test_org_in_anchor_only(self):
        claims = [
            {
                "claim_text": "40% of firms will adopt AI agents",
                "citation_anchor": "Forrester 2024",
                "citation_url": "https://blog.example.com/ai",
            }
        ]
        result = detect_attribution_mismatches(claims)
        assert len(result) == 1
        assert result[0]["named_org"] == "forrester"

    def test_claim_text_truncated_to_120(self):
        long_text = "Gartner " + "x" * 200
        claims = [
            {
                "claim_text": long_text,
                "citation_anchor": "",
                "citation_url": "https://example.com/page",
            }
        ]
        result = detect_attribution_mismatches(claims)
        assert len(result) == 1
        assert len(result[0]["claim_text"]) == 120

    def test_multiple_claims_mixed(self):
        claims = [
            {
                "claim_text": "NIST recommends zero trust",
                "citation_anchor": "NIST",
                "citation_url": "https://nist.gov/guidelines",
            },
            {
                "claim_text": "Forrester says AI spending will rise",
                "citation_anchor": "Forrester",
                "citation_url": "https://techcrunch.com/ai",
            },
        ]
        result = detect_attribution_mismatches(claims)
        assert len(result) == 1
        assert result[0]["named_org"] == "forrester"


class TestExtractDomain:
    def test_basic_url(self):
        assert extract_domain("https://example.com/path") == "example.com"

    def test_www_stripped(self):
        assert extract_domain("https://www.example.com/path") == "example.com"

    def test_subdomain_preserved(self):
        assert extract_domain("https://blog.example.com/post") == "blog.example.com"

    def test_invalid_url(self):
        assert extract_domain("not-a-url") == ""
