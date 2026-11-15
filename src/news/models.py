"""Data models shared across the news intelligence module."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone


def compute_article_id(url: str) -> str:
    """Build a stable dedupe key for an article from its URL.

    Normalizes trivial differences (scheme/host case, trailing slash)
    so the same article linked slightly differently still maps to the
    same id, then hashes it. Used as the SQLite primary key so storing
    the same article twice is a no-op rather than a duplicate row.
    """
    normalized = url.strip().rstrip("/")
    normalized = normalized.split("#", 1)[0]
    return hashlib.sha256(normalized.lower().encode("utf-8")).hexdigest()


@dataclass
class Article:
    """A single normalized news article."""

    title: str
    url: str
    source: str
    published_at: datetime  # always timezone-aware, UTC
    summary: str = ""
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    assets: list[str] = field(default_factory=list)
    event_categories: list[str] = field(default_factory=list)

    @property
    def article_id(self) -> str:
        return compute_article_id(self.url)


@dataclass
class NewsAnalysis:
    """Structured AI analysis of a single article.

    Field names and allowed values follow the Phase 2 specification.
    """

    headline: str
    affected_assets: list[str]
    sentiment: str
    impact_level: str
    confidence: int
    event_category: str
    short_summary: str
    potential_market_impact: str
    impact_horizon: str
    reasoning: str
    source_url: str
    model: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
