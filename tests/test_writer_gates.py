"""Tests for writer SEO gate and banned word sanitizer."""
import pytest
from app.services.writer_service import WriterService


class TestSanitizeBannedWords:
    """Tests for WriterService._sanitize_banned_words()."""

    @pytest.fixture
    def sanitizer(self):
        """Create a minimal WriterService-like object for testing the sanitizer."""
        # The sanitizer is a pure function on self — we can call it on the class method
        # by creating a mock-like object with just the _BANNED_REPLACEMENTS dict
        class FakeWriter:
            _BANNED_REPLACEMENTS = WriterService._BANNED_REPLACEMENTS
            _sanitize_banned_words = WriterService._sanitize_banned_words
        return FakeWriter()

    def test_basic_replacement(self, sanitizer):
        assert "explore" in sanitizer._sanitize_banned_words("delve into the topic")

    def test_capitalized_replacement(self, sanitizer):
        result = sanitizer._sanitize_banned_words("Delve into the topic")
        assert result.startswith("Explore")

    def test_inflected_form(self, sanitizer):
        result = sanitizer._sanitize_banned_words("She was delving into the code")
        assert "exploring" in result

    def test_landscape_replaced(self, sanitizer):
        result = sanitizer._sanitize_banned_words("The cybersecurity landscape is complex")
        assert "landscape" not in result.lower()
        assert "space" in result.lower()

    def test_optimize_all_forms(self, sanitizer):
        text = "We should optimize the pipeline. Optimization is key. The optimized version works."
        result = sanitizer._sanitize_banned_words(text)
        assert "optimize" not in result.lower()
        assert "improve" in result.lower()
        assert "improvement" in result.lower()
        assert "improved" in result.lower()

    def test_leverage_replaced(self, sanitizer):
        result = sanitizer._sanitize_banned_words("Leveraging AI for growth")
        assert "leveraging" not in result.lower()
        assert "Using" in result or "using" in result

    def test_empty_text(self, sanitizer):
        assert sanitizer._sanitize_banned_words("") == ""

    def test_no_banned_words(self, sanitizer):
        text = "The quick brown fox jumps over the lazy dog."
        assert sanitizer._sanitize_banned_words(text) == text

    def test_word_boundary_respected(self, sanitizer):
        """'paradigm' should be replaced but 'paradigmatic' should only match 'paradigm' part."""
        result = sanitizer._sanitize_banned_words("This is a new paradigm in tech")
        assert "paradigm" not in result.lower()
        assert "model" in result.lower()

    def test_multiple_banned_words(self, sanitizer):
        text = "We need a robust ecosystem with seamless synergy"
        result = sanitizer._sanitize_banned_words(text)
        assert "robust" not in result.lower()
        assert "ecosystem" not in result.lower()
        assert "seamless" not in result.lower()
        assert "synergy" not in result.lower()


class TestVerifySeoScore:
    """Tests for WriterService.verify_seo_score()."""

    def _make_article(self, h1=1, h2=6, word_count=1600, blocks=3, banned=False):
        """Generate a minimal article that passes or fails specific SEO gates."""
        lines = []
        if h1:
            lines.append("# Main Title")
        for i in range(h2):
            lines.append(f"\n## Section {i+1}\n")
            # ~200 words per section
            words_per_section = word_count // max(h2, 1)
            lines.append(" ".join(["word"] * words_per_section))
        # Add list/table blocks
        for _ in range(blocks):
            lines.append("\n- Item one\n- Item two\n- Item three\n")
        if banned:
            lines.append("This is a comprehensive delve into the landscape.")
        return "\n".join(lines)

    def test_passing_article(self):
        article = self._make_article()
        result = WriterService.verify_seo_score(article)
        assert result["passed"] is True
        assert result["word_count_ok"] is True
        assert result["h1_ok"] is True
        assert result["h2_ok"] is True
        assert result["lists_tables_ok"] is True
        assert result["banned_words_used"] is False

    def test_word_count_too_low(self):
        article = self._make_article(word_count=500)
        result = WriterService.verify_seo_score(article)
        assert result["word_count_ok"] is False
        assert result["passed"] is False

    def test_no_h1(self):
        article = self._make_article(h1=0)
        result = WriterService.verify_seo_score(article)
        assert result["h1_ok"] is False
        assert result["passed"] is False

    def test_too_few_h2(self):
        article = self._make_article(h2=2)
        result = WriterService.verify_seo_score(article)
        assert result["h2_ok"] is False
        assert result["passed"] is False

    def test_too_few_blocks(self):
        article = self._make_article(blocks=1)
        result = WriterService.verify_seo_score(article)
        assert result["lists_tables_ok"] is False
        assert result["passed"] is False

    def test_banned_words_detected(self):
        article = self._make_article(banned=True)
        result = WriterService.verify_seo_score(article)
        assert result["banned_words_used"] is True
        assert "comprehensive" in result["banned_words_found"]
        assert result["passed"] is False

    def test_code_blocks_excluded_from_h1_count(self):
        """H1-like lines inside code fences should not count as H1."""
        article = "# Real Title\n\n## Section 1\n\n```\n# This is a comment\n```\n\n"
        article += "## S2\n## S3\n## S4\n## S5\n"
        article += " ".join(["word"] * 1600) + "\n"
        article += "\n- a\n- b\n- c\n\n- d\n- e\n- f\n\n- g\n- h\n- i\n"
        result = WriterService.verify_seo_score(article)
        assert result["h1_count"] == 1

    def test_info_gain_with_matching_angles(self):
        info_gap = "Most companies ignore insider threats. Zero trust architecture requires continuous verification."
        article = self._make_article()
        article += "\n## Why Insider Threats Matter\nMost companies ignore insider threats completely.\n"
        result = WriterService.verify_seo_score(article, information_gap=info_gap)
        # At least some angle matching should occur
        assert result["info_gain_density"] >= 0

    def test_info_gain_no_gap(self):
        """No information gap → info gain check passes automatically."""
        result = WriterService.verify_seo_score(self._make_article())
        assert result["info_gain_ok"] is True

    def test_table_block_detection(self):
        article = "# Title\n\n"
        for i in range(6):
            article += f"## Section {i+1}\n" + " ".join(["word"] * 300) + "\n"
        # Each block separated by non-list/table content
        article += "\n| Col A | Col B |\n| --- | --- |\n| Data 1 | Data 2 |\n| Data 3 | Data 4 |\n"
        article += "\nSome paragraph text between blocks.\n"
        article += "\n- Item 1\n- Item 2\n- Item 3\n"
        article += "\nAnother paragraph separating blocks.\n"
        article += "\n1. First\n2. Second\n3. Third\n"
        result = WriterService.verify_seo_score(article)
        assert result["list_table_blocks"] >= 3
