"""Local SQLite storage for collected news articles and AI analysis.

SQLite is used because it ships with Python (no new dependency), needs
no separate server process, and is more than sufficient for a single
user's local news cache. Each public method opens and closes its own
short-lived connection, so this is safe to call from Streamlit's
rerun-per-interaction model without managing a shared connection.
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from src.news.config import NEWS_DB_PATH
from src.news.models import Article, NewsAnalysis, compute_article_id

_CREATE_ARTICLES_TABLE = """
CREATE TABLE IF NOT EXISTS articles (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    source TEXT NOT NULL,
    published_at TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    fetched_at TEXT NOT NULL,
    assets TEXT NOT NULL DEFAULT '[]',
    event_categories TEXT NOT NULL DEFAULT '[]'
)
"""

_CREATE_ANALYSIS_TABLE = """
CREATE TABLE IF NOT EXISTS ai_analysis (
    article_id TEXT PRIMARY KEY,
    headline TEXT NOT NULL,
    affected_assets TEXT NOT NULL DEFAULT '[]',
    sentiment TEXT NOT NULL,
    impact_level TEXT NOT NULL,
    confidence INTEGER NOT NULL,
    event_category TEXT NOT NULL,
    short_summary TEXT NOT NULL,
    potential_market_impact TEXT NOT NULL,
    impact_horizon TEXT NOT NULL,
    reasoning TEXT NOT NULL,
    source_url TEXT NOT NULL,
    model TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY (article_id) REFERENCES articles(id)
)
"""


class NewsStorage:
    """SQLite-backed storage for articles and their AI analysis."""

    def __init__(self, db_path: str = NEWS_DB_PATH):
        self.db_path = db_path
        directory = os.path.dirname(db_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.db_path)
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _init_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(_CREATE_ARTICLES_TABLE)
            connection.execute(_CREATE_ANALYSIS_TABLE)

    # --- Articles --------------------------------------------------------

    def save_articles(self, articles: list[Article]) -> int:
        """Insert new articles, skipping any already stored (by URL).

        Returns the number of articles that were newly inserted.
        """
        inserted = 0
        with self._connect() as connection:
            for article in articles:
                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO articles
                        (id, title, url, source, published_at, summary,
                         fetched_at, assets, event_categories)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        article.article_id,
                        article.title,
                        article.url,
                        article.source,
                        article.published_at.isoformat(),
                        article.summary,
                        article.fetched_at.isoformat(),
                        json.dumps(article.assets),
                        json.dumps(article.event_categories),
                    ),
                )
                inserted += cursor.rowcount
        return inserted

    def get_recent_articles(self, limit: int = 50) -> list[Article]:
        """Return the most recent articles, newest published_at first."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT title, url, source, published_at, summary,
                       fetched_at, assets, event_categories
                FROM articles
                ORDER BY published_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [_row_to_article(row) for row in rows]

    def get_unanalyzed_articles(self, limit: int) -> list[Article]:
        """Return recent articles that have no cached AI analysis yet."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT a.title, a.url, a.source, a.published_at, a.summary,
                       a.fetched_at, a.assets, a.event_categories
                FROM articles AS a
                LEFT JOIN ai_analysis AS n ON n.article_id = a.id
                WHERE n.article_id IS NULL
                ORDER BY a.published_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [_row_to_article(row) for row in rows]

    def count_articles(self) -> int:
        with self._connect() as connection:
            (count,) = connection.execute("SELECT COUNT(*) FROM articles").fetchone()
        return count

    # --- AI analysis (cache) ----------------------------------------------

    def get_analysis(self, article_id: str) -> NewsAnalysis | None:
        """Return the cached analysis for an article, if any.

        Used to avoid re-analyzing (and re-billing) the same article.
        """
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT headline, affected_assets, sentiment, impact_level,
                       confidence, event_category, short_summary,
                       potential_market_impact, impact_horizon, reasoning,
                       source_url, model, created_at
                FROM ai_analysis
                WHERE article_id = ?
                """,
                (article_id,),
            ).fetchone()
        if row is None:
            return None
        return _row_to_analysis(row)

    def has_analysis(self, article_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM ai_analysis WHERE article_id = ?", (article_id,)
            ).fetchone()
        return row is not None

    def save_analysis(self, article_id: str, analysis: NewsAnalysis) -> None:
        """Cache an AI analysis result, keyed by article id.

        Uses INSERT OR REPLACE so re-saving the same article_id (e.g. a
        deliberate re-analysis) overwrites rather than duplicates.
        """
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO ai_analysis
                    (article_id, headline, affected_assets, sentiment,
                     impact_level, confidence, event_category, short_summary,
                     potential_market_impact, impact_horizon, reasoning,
                     source_url, model, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    article_id,
                    analysis.headline,
                    json.dumps(analysis.affected_assets),
                    analysis.sentiment,
                    analysis.impact_level,
                    analysis.confidence,
                    analysis.event_category,
                    analysis.short_summary,
                    analysis.potential_market_impact,
                    analysis.impact_horizon,
                    analysis.reasoning,
                    analysis.source_url,
                    analysis.model,
                    analysis.created_at.isoformat(),
                ),
            )


def _row_to_article(row: tuple) -> Article:
    (title, url, source, published_at, summary, fetched_at, assets, event_categories) = row
    return Article(
        title=title,
        url=url,
        source=source,
        published_at=datetime.fromisoformat(published_at),
        summary=summary,
        fetched_at=datetime.fromisoformat(fetched_at),
        assets=json.loads(assets),
        event_categories=json.loads(event_categories),
    )


def _row_to_analysis(row: tuple) -> NewsAnalysis:
    (
        headline,
        affected_assets,
        sentiment,
        impact_level,
        confidence,
        event_category,
        short_summary,
        potential_market_impact,
        impact_horizon,
        reasoning,
        source_url,
        model,
        created_at,
    ) = row
    return NewsAnalysis(
        headline=headline,
        affected_assets=json.loads(affected_assets),
        sentiment=sentiment,
        impact_level=impact_level,
        confidence=confidence,
        event_category=event_category,
        short_summary=short_summary,
        potential_market_impact=potential_market_impact,
        impact_horizon=impact_horizon,
        reasoning=reasoning,
        source_url=source_url,
        model=model,
        created_at=datetime.fromisoformat(created_at),
    )


__all__ = ["NewsStorage", "compute_article_id"]
