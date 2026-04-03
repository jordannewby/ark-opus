"""Tests for readability scoring and pass/fail logic."""
import pytest
from app.services.readability_service import (
    analyze_readability,
    verify_readability,
    passes_readability,
)


class TestPassesReadability:
    """Tests for the multi-factor pass gate."""

    def test_all_passing(self):
        assert passes_readability(
            ari=8.0, cli=7.5, fk=9.0, target=10.0,
            avg_sentence_length=10.0, max_sentence_length=12.0,
            complex_sentence_count=2, total_sentence_count=20,
            target_range_percentage=60.0,
        ) is True

    def test_ari_too_high(self):
        """ARI above target + 1.5 should fail."""
        assert passes_readability(
            ari=12.0, cli=7.0, fk=8.0, target=10.0,
            avg_sentence_length=10.0,
        ) is False

    def test_ari_at_boundary(self):
        """ARI exactly at target + 1.5 should pass."""
        assert passes_readability(
            ari=11.5, cli=7.0, fk=8.0, target=10.0,
            avg_sentence_length=10.0,
        ) is True

    def test_fk_too_high(self):
        """FK above target + 2.0 should fail."""
        assert passes_readability(
            ari=9.0, cli=7.0, fk=13.0, target=10.0,
            avg_sentence_length=10.0,
        ) is False

    def test_fk_at_boundary(self):
        """FK exactly at target + 2.0 should pass."""
        assert passes_readability(
            ari=9.0, cli=7.0, fk=12.0, target=10.0,
            avg_sentence_length=10.0,
        ) is True

    def test_avg_sentence_length_too_high(self):
        """Avg sentence > max + 3.0 should fail."""
        assert passes_readability(
            ari=9.0, cli=7.0, fk=9.0, target=10.0,
            avg_sentence_length=16.0, max_sentence_length=12.0,
        ) is False

    def test_avg_sentence_zero_passes(self):
        """avg_sentence_length=0 should not penalize."""
        assert passes_readability(
            ari=9.0, cli=7.0, fk=9.0, target=10.0,
            avg_sentence_length=0.0,
        ) is True

    def test_too_many_complex_sentences(self):
        """Complex sentences > 25% of total should fail."""
        assert passes_readability(
            ari=9.0, cli=7.0, fk=9.0, target=10.0,
            avg_sentence_length=10.0,
            complex_sentence_count=10, total_sentence_count=20,
        ) is False

    def test_complex_at_boundary(self):
        """Exactly 25% complex sentences should pass."""
        assert passes_readability(
            ari=9.0, cli=7.0, fk=9.0, target=10.0,
            avg_sentence_length=10.0,
            complex_sentence_count=5, total_sentence_count=20,
        ) is True

    def test_zero_sentences_passes(self):
        """No sentences → complex check should pass."""
        assert passes_readability(
            ari=9.0, cli=7.0, fk=9.0, target=10.0,
            complex_sentence_count=0, total_sentence_count=0,
        ) is True

    def test_distribution_too_low(self):
        """Target range < 50% should fail."""
        assert passes_readability(
            ari=9.0, cli=7.0, fk=9.0, target=10.0,
            avg_sentence_length=10.0,
            target_range_percentage=30.0,
        ) is False

    def test_distribution_at_boundary(self):
        """Exactly 50% should pass."""
        assert passes_readability(
            ari=9.0, cli=7.0, fk=9.0, target=10.0,
            avg_sentence_length=10.0,
            target_range_percentage=50.0,
        ) is True

    def test_distribution_zero_passes(self):
        """target_range_percentage=0 should pass (no data)."""
        assert passes_readability(
            ari=9.0, cli=7.0, fk=9.0, target=10.0,
            target_range_percentage=0.0,
        ) is True


class TestAnalyzeReadability:
    """Tests for analyze_readability() — full scoring pipeline."""

    def test_simple_text_passes(self):
        """Short simple sentences should get a low ARI and pass."""
        text = "AI helps teams work faster. Simple tools save time. " * 20
        result = analyze_readability(text)
        assert result.passed is True
        assert result.ari_grade < 10.0

    def test_complex_text_fails(self):
        """Long complex sentences should fail readability."""
        text = (
            "The implementation of sophisticated artificial intelligence "
            "algorithms within enterprise organizations necessitates careful "
            "consideration of multifaceted architectural decisions and "
            "comprehensive evaluation of various deployment methodologies. "
        ) * 15
        result = analyze_readability(text)
        assert result.ari_grade > 10.0

    def test_empty_text(self):
        """Empty text should return a result without crashing."""
        result = analyze_readability("")
        assert result.word_count == 0

    def test_keyword_masking(self):
        """Keywords should be masked before scoring but not affect output."""
        text = "The cybersecurity-threat-detection market is growing fast. " * 20
        # Without masking, the hyphenated keyword inflates ARI
        result_no_kw = analyze_readability(text)
        result_with_kw = analyze_readability(text, keywords=["cybersecurity-threat-detection"])
        # Masking should lower or maintain the grade
        assert result_with_kw.ari_grade <= result_no_kw.ari_grade + 0.1


class TestVerifyReadability:
    """Tests for verify_readability() — dict-returning wrapper."""

    def test_returns_expected_keys(self):
        text = "AI helps teams work faster. Simple tools save time. " * 20
        result = verify_readability(text)
        assert "passed" in result or "pass" in result
        assert "details" in result
        assert "ari_grade" in result["details"]
        assert "flesch_kincaid_grade" in result["details"]
        assert "coleman_liau_grade" in result["details"]
        assert "word_count" in result["details"]

    def test_simple_text_passes(self):
        text = "AI helps teams work faster. Simple tools save time. " * 20
        result = verify_readability(text)
        passed = result.get("passed", result.get("pass"))
        assert passed is True
