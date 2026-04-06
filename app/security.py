"""Prompt injection mitigations for LLM input boundaries."""
import re

_CONTROL_CHAR_RE = re.compile(
    r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f'
    r'\u200b-\u200f'
    r'\u2028\u2029'
    r'\u202a-\u202e'
    r'\u2060-\u2064'
    r'\ufeff'
    r'\ufff9-\ufffb'
    r']'
)

_HTML_COMMENT_RE = re.compile(r'<!--.*?-->', re.DOTALL)


def sanitize_prompt_input(text: str, max_chars: int | None = None, tag: str = 'user_input') -> str:
    """Sanitize user-controlled text before injecting into LLM prompts.
    Strips HTML comments and control chars, truncates, wraps in XML boundary tags."""
    if not text:
        return ''
    text = _HTML_COMMENT_RE.sub('', text)
    text = _CONTROL_CHAR_RE.sub('', text)
    if max_chars and len(text) > max_chars:
        text = text[:max_chars]
    return f'<{tag}>\n{text}\n</{tag}>'


def sanitize_external_content(text: str, max_chars: int | None = None) -> str:
    """Sanitize external/untrusted content (Exa results, tool outputs).
    Strips HTML comments and control chars. No boundary wrapping."""
    if not text:
        return ''
    text = _HTML_COMMENT_RE.sub('', text)
    text = _CONTROL_CHAR_RE.sub('', text)
    if max_chars and len(text) > max_chars:
        text = text[:max_chars]
    return text
