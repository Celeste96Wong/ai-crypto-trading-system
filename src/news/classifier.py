"""Lightweight, deterministic classification of news articles.

Uses simple keyword matching rather than a paid API or ML model, since
this classification just narrows down which assets/categories an
article is relevant to before (optionally) spending AI budget on it.
It deliberately does not assume every article affects every asset:
articles can match zero, one, or several assets/categories.
"""

from __future__ import annotations

import re

from src.news.config import (
    ASSET_KEYWORDS,
    EVENT_CATEGORY_KEYWORDS,
    UNCATEGORIZED_EVENT_CATEGORY,
)


def _contains_keyword(text: str, keyword: str) -> bool:
    """Case-insensitive, word-boundary-aware substring check.

    A plain `in` check would match "sol" inside "solution" or "eth"
    inside "method". Keywords that already end in a space (e.g. "sol ")
    are matched as a literal substring instead, since they are meant to
    guard against exactly that kind of false positive by requiring a
    trailing word boundary.
    """
    if keyword.endswith(" "):
        return keyword in text
    pattern = r"(?<![a-z0-9])" + re.escape(keyword) + r"(?![a-z0-9])"
    return re.search(pattern, text) is not None


def identify_assets(text: str) -> list[str]:
    """Return the list of supported assets (BTC/ETH/SOL/XRP) mentioned.

    Returns an empty list if the text does not clearly mention any of
    them - an article is not assumed to affect every asset by default.
    """
    lowered = text.lower()
    matched = [
        asset
        for asset, keywords in ASSET_KEYWORDS.items()
        if any(_contains_keyword(lowered, keyword) for keyword in keywords)
    ]
    return matched


def categorize_event(text: str) -> list[str]:
    """Return the list of event categories a text matches.

    Returns [UNCATEGORIZED_EVENT_CATEGORY] if nothing matches, so
    callers always get a non-empty category list to display.
    """
    lowered = text.lower()
    matched = [
        category
        for category, keywords in EVENT_CATEGORY_KEYWORDS.items()
        if any(_contains_keyword(lowered, keyword) for keyword in keywords)
    ]
    return matched or [UNCATEGORIZED_EVENT_CATEGORY]


def classify_article(title: str, summary: str) -> tuple[list[str], list[str]]:
    """Classify an article's assets and event categories from its text.

    Combines title and summary (title first, since it carries more
    signal) and returns (assets, event_categories).
    """
    text = f"{title} {summary}"
    return identify_assets(text), categorize_event(text)
