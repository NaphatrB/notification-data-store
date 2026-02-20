"""Candidate filter for the pricing parser.

Two layers:
1. **Metadata filter** — source_type, package_name, app_name allowlists
   configured via env vars.  If no allowlists are set, every event passes.
2. **Text heuristic filter** (optional) — checks notification text for
   pricing keywords (kg, numeric patterns).  Only active when
   PARSER_TEXT_FILTER_ENABLED=true.

Only messages passing *both* active layers are sent to the LLM.
"""

import re

from app.parser.config import (
    PARSER_APP_FILTER,
    PARSER_PACKAGE_FILTER,
    PARSER_SOURCE_FILTER,
    PARSER_TEXT_FILTER_ENABLED,
)

# Pattern: one or more digits, optionally with decimal point
_NUMERIC_PATTERN = re.compile(r"\d+\.?\d*")


def _passes_metadata_filter(
    source_type: str | None,
    package_name: str | None,
    app_name: str | None,
) -> bool:
    """Check event metadata against configured allowlists.

    Each non-empty allowlist is an independent gate: the event must match
    *every* configured list.  If an allowlist is empty, that dimension is
    unrestricted.
    """
    if PARSER_SOURCE_FILTER:
        if (source_type or "").lower() not in PARSER_SOURCE_FILTER:
            return False
    if PARSER_PACKAGE_FILTER:
        if (package_name or "").lower() not in PARSER_PACKAGE_FILTER:
            return False
    if PARSER_APP_FILTER:
        if (app_name or "").lower() not in PARSER_APP_FILTER:
            return False
    return True


def _passes_text_heuristic(
    title: str | None, text: str | None, big_text: str | None
) -> bool:
    """Return True if the message text contains pricing-like patterns."""
    combined = " ".join([title or "", text or "", big_text or ""]).lower()
    if not combined.strip():
        return False
    if not _NUMERIC_PATTERN.search(combined):
        return False
    if "kg" in combined:
        return True
    return False


def is_pricing_candidate(
    source_type: str | None,
    package_name: str | None,
    app_name: str | None,
    title: str | None,
    text: str | None,
    big_text: str | None,
) -> bool:
    """Return True if the event should be sent to the LLM."""
    if not _passes_metadata_filter(source_type, package_name, app_name):
        return False

    if PARSER_TEXT_FILTER_ENABLED:
        return _passes_text_heuristic(title, text, big_text)

    # No text filter — metadata match is enough
    return True
