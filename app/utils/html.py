"""Sanitising and flattening the rich-text product descriptions.

Descriptions are authored in TipTap and stored as HTML. Only admins can write
them, but `manager` currently carries the same rights as `admin`, and a crafted
API call bypasses the editor entirely — so anything that ends up on a public
product page is sanitised on write rather than trusted.
"""

import re

import nh3

# Matches what TipTap's StarterKit can produce, and nothing that executes.
ALLOWED_TAGS = {
    "p",
    "br",
    "strong",
    "b",
    "em",
    "i",
    "u",
    "s",
    "ul",
    "ol",
    "li",
    "h2",
    "h3",
    "h4",
    "blockquote",
    "code",
    "pre",
    "a",
    "hr",
}

# `rel` is deliberately absent: nh3 rejects the allowlist if it is present
# while `link_rel` is set, and link_rel is what forces noopener on every link.
ALLOWED_ATTRIBUTES = {"a": {"href", "title", "target"}}

_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


def sanitize_html(value: str | None) -> str | None:
    """Strip scripts, event handlers and unknown tags from authored HTML."""
    if value is None:
        return None
    return nh3.clean(
        value,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        link_rel="noopener noreferrer",
    )


def to_plain_text(value: str | None, limit: int | None = None) -> str:
    """Flatten HTML for meta descriptions, listing cards and search.

    Those places need text, not markup — storing both descriptions as HTML
    means every such consumer has to strip it, so this is the one helper that
    does it.
    """
    if not value:
        return ""
    text = _TAG_RE.sub(" ", value)
    text = nh3.clean(text, tags=set(), attributes={})
    text = _WHITESPACE_RE.sub(" ", text).strip()
    if limit is not None and len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text
