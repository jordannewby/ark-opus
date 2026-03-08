"""
Readability Service for Ares Engine
====================================
Composite readability scorer using ARI (primary), Coleman-Liau (secondary),
and Flesch-Kincaid (cross-check). Designed to integrate with WriterService's
existing iterative SEO loop.

Zero paid dependencies. Zero API cost. Pure Python.
"""

import re
import math
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class ReadabilityScore:
    """Result of a full readability analysis."""
    ari_grade: float
    coleman_liau_grade: float
    flesch_kincaid_grade: float
    composite_grade: float
    passed: bool
    target_grade: float
    word_count: int
    sentence_count: int
    avg_sentence_length: float
    complex_sentences: list = field(default_factory=list)
    feedback: str | None = None


@dataclass
class SentenceAnalysis:
    """Readability breakdown for a single sentence."""
    text: str
    word_count: int
    ari_grade: float
    coleman_liau_grade: float
    avg_grade: float


# ---------------------------------------------------------------------------
# Text Preprocessing
# ---------------------------------------------------------------------------

def strip_markdown(text: str) -> str:
    """Remove Markdown formatting while preserving readable prose.
    
    Strips headers, links, images, code blocks, bold/italic markers,
    and HTML tags so they don't inflate or deflate readability scores.
    """
    # Remove code blocks (fenced)
    text = re.sub(r'```[\s\S]*?```', '', text)
    # Remove inline code
    text = re.sub(r'`[^`]+`', '', text)
    # Remove images ![alt](url)
    text = re.sub(r'!\[[^\]]*\]\([^)]*\)', '', text)
    # Convert links [text](url) → text
    text = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', text)
    # Remove header markers (## Header → Header)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    # Remove bold/italic markers
    text = re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', text)
    text = re.sub(r'_{1,3}([^_]+)_{1,3}', r'\1', text)
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    # Remove horizontal rules
    text = re.sub(r'^[-*_]{3,}\s*$', '', text, flags=re.MULTILINE)
    # Remove list markers but keep text
    text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)
    # Remove blockquote markers
    text = re.sub(r'^\s*>\s+', '', text, flags=re.MULTILINE)
    # Collapse multiple newlines/whitespace
    text = re.sub(r'\n{2,}', '\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    return text.strip()


def mask_keywords(text: str, keywords: list[str]) -> str:
    """Replace target SEO keywords with simple placeholder words.
    
    This prevents multi-syllable technical keywords (e.g., 'cybersecurity',
    'authentication') from inflating the readability score. The keywords
    MUST stay in the actual article — we only mask them for scoring.
    
    Each keyword is replaced with 'word' (1 syllable, 4 chars) to maintain
    accurate word/sentence counts while neutralizing complexity inflation.
    """
    masked = text
    for kw in sorted(keywords, key=len, reverse=True):
        # Case-insensitive replacement, preserve word boundaries
        pattern = re.compile(re.escape(kw), re.IGNORECASE)
        masked = pattern.sub('word', masked)
    return masked


# ---------------------------------------------------------------------------
# Counting Primitives
# ---------------------------------------------------------------------------

def count_sentences(text: str) -> int:
    """Count sentences using punctuation boundaries.
    
    Handles abbreviations (Mr., Dr., U.S.) and decimal numbers
    to avoid false splits.
    """
    # Protect common abbreviations
    protected = text
    abbreviations = [
        'Mr.', 'Mrs.', 'Ms.', 'Dr.', 'Prof.', 'Sr.', 'Jr.',
        'vs.', 'etc.', 'i.e.', 'e.g.', 'U.S.', 'U.K.', 'a.m.', 'p.m.'
    ]
    for abbr in abbreviations:
        protected = protected.replace(abbr, abbr.replace('.', '<<DOT>>'))
    
    # Protect decimal numbers (3.14, 99.9%)
    protected = re.sub(r'(\d)\.(\d)', r'\1<<DOT>>\2', protected)
    
    # Split on sentence-ending punctuation
    sentences = re.split(r'[.!?]+', protected)
    # Filter out empty strings
    sentences = [s.strip() for s in sentences if s.strip() and len(s.split()) >= 2]
    return max(len(sentences), 1)


def split_sentences(text: str) -> list[str]:
    """Split text into individual sentences for per-sentence analysis."""
    protected = text
    abbreviations = [
        'Mr.', 'Mrs.', 'Ms.', 'Dr.', 'Prof.', 'Sr.', 'Jr.',
        'vs.', 'etc.', 'i.e.', 'e.g.', 'U.S.', 'U.K.', 'a.m.', 'p.m.'
    ]
    for abbr in abbreviations:
        protected = protected.replace(abbr, abbr.replace('.', '<<DOT>>'))
    protected = re.sub(r'(\d)\.(\d)', r'\1<<DOT>>\2', protected)
    
    # Split but keep the delimiter for reconstruction
    raw = re.split(r'(?<=[.!?])\s+', protected)
    sentences = []
    for s in raw:
        restored = s.replace('<<DOT>>', '.')
        restored = restored.strip()
        if restored and len(restored.split()) >= 2:
            sentences.append(restored)
    return sentences


def count_words(text: str) -> int:
    """Count words in text."""
    words = re.findall(r'[a-zA-Z0-9]+(?:\'[a-zA-Z]+)?', text)
    return len(words)


def count_characters(text: str) -> int:
    """Count alphanumeric characters (letters + digits), no spaces/punctuation."""
    return sum(1 for c in text if c.isalnum())


def count_letters(text: str) -> int:
    """Count only alphabetic characters."""
    return sum(1 for c in text if c.isalpha())


def _estimate_syllables(word: str) -> int:
    """Estimate syllable count for a single word using a rule-based approach.
    
    This is used ONLY for the Flesch-Kincaid cross-check. ARI and Coleman-Liau
    don't need syllables at all, which is why they're our primary scorers.
    
    Algorithm: vowel-group counting with English-specific corrections.
    Not perfect, but over a 2500-word article the errors average out.
    """
    word = word.lower().strip()
    if not word:
        return 0
    if len(word) <= 3:
        return 1
    
    # Remove trailing silent-e
    if word.endswith('e') and not word.endswith('le'):
        word = word[:-1]
    
    # Count vowel groups
    vowels = 'aeiouy'
    count = 0
    prev_vowel = False
    for char in word:
        is_vowel = char in vowels
        if is_vowel and not prev_vowel:
            count += 1
        prev_vowel = is_vowel
    
    # Corrections
    # -ed ending (usually not a syllable unless preceded by t or d)
    if word.endswith('ed') and len(word) > 3:
        if word[-3] not in ('t', 'd'):
            count = max(count - 1, 1)
    
    # -le ending IS a syllable (handle, simple)
    if word.endswith('le') and len(word) > 2 and word[-3] not in vowels:
        count += 1
    
    # Common suffixes that add syllables
    for suffix in ['tion', 'sion', 'cious', 'tious', 'gious']:
        if word.endswith(suffix):
            count = max(count, 2)
            break
    
    return max(count, 1)


def count_syllables(text: str) -> int:
    """Count total syllables in text."""
    words = re.findall(r'[a-zA-Z]+', text)
    return sum(_estimate_syllables(w) for w in words)


# ---------------------------------------------------------------------------
# Readability Formulas
# ---------------------------------------------------------------------------

def compute_ari(text: str) -> float:
    """Automated Readability Index — primary scorer.
    
    Formula: 4.71 × (characters/words) + 0.5 × (words/sentences) − 21.43
    
    Uses character count instead of syllables, making it 100% deterministic.
    This is what Hemingway App uses under the hood for real-time scoring.
    """
    words = count_words(text)
    if words == 0:
        return 0.0
    chars = count_characters(text)
    sents = count_sentences(text)
    
    score = 4.71 * (chars / words) + 0.5 * (words / sents) - 21.43
    return round(score, 1)


def compute_coleman_liau(text: str) -> float:
    """Coleman-Liau Index — secondary scorer.
    
    Formula: 0.0588 × L − 0.296 × S − 15.8
    Where L = avg letters per 100 words, S = avg sentences per 100 words
    
    Also character-based (no syllables). Provides a second opinion
    that's calculated differently from ARI.
    """
    words = count_words(text)
    if words == 0:
        return 0.0
    letters = count_letters(text)
    sents = count_sentences(text)
    
    L = (letters / words) * 100
    S = (sents / words) * 100
    
    score = 0.0588 * L - 0.296 * S - 15.8
    return round(score, 1)


def compute_flesch_kincaid_grade(text: str) -> float:
    """Flesch-Kincaid Grade Level — cross-check scorer.
    
    Formula: 0.39 × (words/sentences) + 11.8 × (syllables/words) − 15.59
    
    Uses syllable counting (less accurate programmatically), which is why
    this is the cross-check, not the primary scorer.
    """
    words = count_words(text)
    if words == 0:
        return 0.0
    syllables = count_syllables(text)
    sents = count_sentences(text)
    
    score = 0.39 * (words / sents) + 11.8 * (syllables / words) - 15.59
    return round(score, 1)


# ---------------------------------------------------------------------------
# Composite Scoring
# ---------------------------------------------------------------------------

def compute_composite_grade(ari: float, cli: float, fk: float) -> float:
    """Compute composite grade using 2-of-3 voting logic.
    
    If 2+ scores agree the text is at or below target, it passes.
    The composite is the median of the three scores, which naturally
    dampens any one formula's outlier behavior.
    """
    scores = sorted([ari, cli, fk])
    # Median of 3 = middle value
    return scores[1]


def passes_readability(
    ari: float,
    cli: float,
    fk: float,
    target: float = 5.9
) -> bool:
    """Check if at least 2 of 3 formulas score at or below target grade."""
    at_or_below = sum(1 for s in [ari, cli, fk] if s <= target)
    return at_or_below >= 2


# ---------------------------------------------------------------------------
# Sentence-Level Analysis
# ---------------------------------------------------------------------------

def analyze_sentence(sentence: str) -> SentenceAnalysis:
    """Score a single sentence with ARI and Coleman-Liau.
    
    For individual sentences, we only use character-based formulas
    since FK syllable errors are amplified on short text.
    """
    words = count_words(sentence)
    ari = compute_ari(sentence)
    cli = compute_coleman_liau(sentence)
    avg = round((ari + cli) / 2, 1)
    
    return SentenceAnalysis(
        text=sentence,
        word_count=words,
        ari_grade=ari,
        coleman_liau_grade=cli,
        avg_grade=avg
    )


def find_complex_sentences(
    text: str,
    threshold: float = 8.0,
    max_results: int = 5
) -> list[SentenceAnalysis]:
    """Find the most complex sentences that need simplification.
    
    Args:
        text: Cleaned prose text (Markdown already stripped)
        threshold: Grade level above which a sentence is flagged
        max_results: Maximum number of sentences to return (for focused feedback)
    
    Returns:
        List of SentenceAnalysis objects, sorted worst-first
    """
    sentences = split_sentences(text)
    complex_sents = []
    
    for sent in sentences:
        analysis = analyze_sentence(sent)
        if analysis.avg_grade > threshold and analysis.word_count >= 5:
            complex_sents.append(analysis)
    
    # Sort by grade descending (worst offenders first)
    complex_sents.sort(key=lambda s: s.avg_grade, reverse=True)
    return complex_sents[:max_results]


# ---------------------------------------------------------------------------
# Main Analysis Function
# ---------------------------------------------------------------------------

def analyze_readability(
    content: str,
    target_grade: float = 5.9,
    keywords: list[str] | None = None
) -> ReadabilityScore:
    """Full readability analysis with composite scoring.
    
    This is the main entry point for WriterService integration.
    
    Args:
        content: Raw Markdown article content from the writer
        target_grade: Maximum acceptable grade level (default 5.9 for 5th grade)
        keywords: SEO target keywords to exclude from scoring
    
    Returns:
        ReadabilityScore with pass/fail, all sub-scores, and feedback if failing
    """
    # Step 1: Strip Markdown formatting
    clean = strip_markdown(content)
    
    # Step 2: Mask SEO keywords for scoring (they stay in the real article)
    scoring_text = mask_keywords(clean, keywords) if keywords else clean
    
    # Step 3: Compute all three scores
    ari = compute_ari(scoring_text)
    cli = compute_coleman_liau(scoring_text)
    fk = compute_flesch_kincaid_grade(scoring_text)
    
    # Step 4: Composite + pass/fail
    composite = compute_composite_grade(ari, cli, fk)
    passed = passes_readability(ari, cli, fk, target_grade)
    
    # Step 5: Count stats
    words = count_words(clean)
    sents = count_sentences(clean)
    avg_sent_len = round(words / sents, 1) if sents > 0 else 0.0
    
    # Step 6: Find complex sentences (use clean text, not masked)
    complex_sents = [] if passed else find_complex_sentences(clean, threshold=8.0)
    
    # Step 7: Generate feedback if failing
    feedback = None if passed else _build_feedback(
        ari=ari,
        cli=cli,
        fk=fk,
        composite=composite,
        target=target_grade,
        avg_sent_len=avg_sent_len,
        complex_sentences=complex_sents
    )
    
    return ReadabilityScore(
        ari_grade=ari,
        coleman_liau_grade=cli,
        flesch_kincaid_grade=fk,
        composite_grade=composite,
        passed=passed,
        target_grade=target_grade,
        word_count=words,
        sentence_count=sents,
        avg_sentence_length=avg_sent_len,
        complex_sentences=complex_sents,
        feedback=feedback
    )


# ---------------------------------------------------------------------------
# Feedback Generation (injected into Claude's retry prompt)
# ---------------------------------------------------------------------------

def _build_feedback(
    ari: float,
    cli: float,
    fk: float,
    composite: float,
    target: float,
    avg_sent_len: float,
    complex_sentences: list[SentenceAnalysis]
) -> str:
    """Build structured feedback for Claude's readability retry loop.
    
    This feedback is injected into the writer prompt on the next iteration,
    exactly like SEO validation feedback is today.
    """
    lines = []
    lines.append(f"READABILITY REVISION REQUIRED — Current grade: {composite} | Target: ≤{target}")
    lines.append(f"  ARI: {ari} | Coleman-Liau: {cli} | Flesch-Kincaid: {fk}")
    lines.append("")
    
    # Diagnose the root cause
    if avg_sent_len > 15:
        lines.append(f"PRIMARY ISSUE: Sentences are too long (avg {avg_sent_len} words). Target: 10-14 words per sentence.")
        lines.append("ACTION: Break long sentences into two or three shorter ones. Each sentence should hold one idea.")
    
    # Flag specific offending sentences
    if complex_sentences:
        lines.append("")
        lines.append(f"TOP {len(complex_sentences)} COMPLEX SENTENCES TO REWRITE:")
        for i, sent in enumerate(complex_sentences, 1):
            # Truncate very long sentences for prompt efficiency
            display = sent.text[:150] + "..." if len(sent.text) > 150 else sent.text
            lines.append(f"  {i}. [Grade {sent.avg_grade}] \"{display}\"")
        lines.append("")
        lines.append("Rewrite each sentence above at a 5th grade level.")
    
    # Universal guidance
    lines.append("")
    lines.append("RULES FOR THIS REVISION:")
    lines.append("- DO NOT remove any facts, statistics, data points, or insights")
    lines.append("- DO NOT remove or merge any H2 sections")
    lines.append("- DO NOT reduce the word count below the SEO minimum")
    lines.append("- DO NOT remove list blocks or table blocks")
    lines.append("- USE short sentences (under 15 words each)")
    lines.append("- USE common, everyday words (1-2 syllables)")
    lines.append("- WHEN using a technical term, explain it right away in plain words")
    lines.append("- USE active voice ('Hackers steal data' not 'Data is stolen by hackers')")
    lines.append("- KEEP the same structure, sections, and SEO keywords")
    
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Convenience: Verify function matching WriterService pattern
# ---------------------------------------------------------------------------

def verify_readability(
    content: str,
    target_grade: float = 5.9,
    keywords: list[str] | None = None
) -> dict:
    """Verify readability — matches the return pattern of verify_seo_score.
    
    Returns:
        dict with 'pass', 'score', 'feedback', and 'details' keys
    """
    result = analyze_readability(content, target_grade, keywords)
    
    return {
        "pass": result.passed,
        "score": result.composite_grade,
        "feedback": result.feedback,
        "details": {
            "ari_grade": result.ari_grade,
            "coleman_liau_grade": result.coleman_liau_grade,
            "flesch_kincaid_grade": result.flesch_kincaid_grade,
            "composite_grade": result.composite_grade,
            "word_count": result.word_count,
            "sentence_count": result.sentence_count,
            "avg_sentence_length": result.avg_sentence_length,
            "complex_sentence_count": len(result.complex_sentences),
        }
    }


# ---------------------------------------------------------------------------
# Writer Prompt Directive (injected dynamically, not in writer.md)
# ---------------------------------------------------------------------------

READABILITY_DIRECTIVE = """
## READABILITY REQUIREMENT — 5th Grade Level

Write every sentence at a 5th grade reading level. This is non-negotiable.

RULES:
- Keep sentences SHORT: 10-14 words max. One idea per sentence.
- Use COMMON words: prefer 1-2 syllable words over longer ones.
- Use ACTIVE voice: "Hackers steal data" not "Data is stolen by hackers."
- When you MUST use a technical term, explain it immediately in plain language.
  Example: "Ransomware is a type of attack. It locks your files until you pay."
- Vary sentence length slightly to maintain rhythm and personality.
  Mix 8-word sentences with 14-word sentences. Avoid robotic uniformity.
- This does NOT mean writing for children. It means explaining complex ideas simply.
  Ernest Hemingway wrote about war and death at a 5th grade level.

WHAT TO PRESERVE:
- Every fact, statistic, and data point from the research brief
- All SEO keywords in headings and body text
- All H2 sections, list blocks, and table blocks
- The emotional hooks and identity triggers from the psychology blueprint
- The personality and style rules from the workspace
""".strip()
