import os
from datetime import datetime, timezone

import pytest

from src.news.models import Article, NewsAnalysis
from src.news.storage import NewsStorage


@pytest.fixture
def storage(tmp_path):
    db_path = os.path.join(tmp_path, "news.db")
    return NewsStorage(db_path=db_path)


def _make_article(url="https://example.com/a", title="Title", source="Source"):
    return Article(
        title=title,
        url=url,
        source=source,
        published_at=datetime(2025, 11, 10, 12, 0, 0, tzinfo=timezone.utc),
        summary="Summary text.",
        assets=["BTC"],
        event_categories=["technology_ecosystem"],
    )


def _make_analysis(url="https://example.com/a"):
    return NewsAnalysis(
        headline="Headline",
        affected_assets=["BTC"],
        sentiment="neutral",
        impact_level="low",
        confidence=40,
        event_category="technology_ecosystem",
        short_summary="Short summary.",
        potential_market_impact="Could have a minor effect.",
        impact_horizon="uncertain",
        reasoning="Based on limited confirmed information.",
        source_url=url,
        model="gpt-4o-mini",
    )


def test_creates_db_file_and_directory(tmp_path):
    db_path = os.path.join(tmp_path, "nested", "news.db")
    NewsStorage(db_path=db_path)

    assert os.path.exists(db_path)


def test_save_and_get_recent_articles(storage):
    article = _make_article()

    inserted = storage.save_articles([article])

    assert inserted == 1
    recent = storage.get_recent_articles(limit=10)
    assert len(recent) == 1
    assert recent[0].title == "Title"
    assert recent[0].assets == ["BTC"]
    assert recent[0].event_categories == ["technology_ecosystem"]
    assert recent[0].published_at == article.published_at


def test_save_articles_skips_duplicates_by_url(storage):
    article = _make_article()
    duplicate = _make_article(title="Different title, same URL")

    first_inserted = storage.save_articles([article])
    second_inserted = storage.save_articles([duplicate])

    assert first_inserted == 1
    assert second_inserted == 0
    assert storage.count_articles() == 1
    # The original stored row is kept, not overwritten.
    assert storage.get_recent_articles(limit=10)[0].title == "Title"


def test_save_articles_treats_trivial_url_variants_as_duplicates(storage):
    a = _make_article(url="https://Example.com/a/")
    b = _make_article(url="https://example.com/a")

    storage.save_articles([a])
    inserted = storage.save_articles([b])

    assert inserted == 0
    assert storage.count_articles() == 1


def test_get_recent_articles_orders_newest_first(storage):
    older = _make_article(url="https://example.com/old", title="Older")
    older.published_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    newer = _make_article(url="https://example.com/new", title="Newer")
    newer.published_at = datetime(2025, 6, 1, tzinfo=timezone.utc)

    storage.save_articles([older, newer])

    recent = storage.get_recent_articles(limit=10)
    assert [a.title for a in recent] == ["Newer", "Older"]


def test_analysis_cache_round_trip(storage):
    article = _make_article()
    storage.save_articles([article])
    analysis = _make_analysis(url=article.url)

    assert storage.get_analysis(article.article_id) is None
    assert storage.has_analysis(article.article_id) is False

    storage.save_analysis(article.article_id, analysis)

    assert storage.has_analysis(article.article_id) is True
    cached = storage.get_analysis(article.article_id)
    assert cached.headline == "Headline"
    assert cached.affected_assets == ["BTC"]
    assert cached.confidence == 40


def test_get_unanalyzed_articles_excludes_cached_ones(storage):
    analyzed = _make_article(url="https://example.com/analyzed", title="Analyzed")
    unanalyzed = _make_article(url="https://example.com/unanalyzed", title="Unanalyzed")
    storage.save_articles([analyzed, unanalyzed])
    storage.save_analysis(analyzed.article_id, _make_analysis(url=analyzed.url))

    pending = storage.get_unanalyzed_articles(limit=10)

    assert [a.title for a in pending] == ["Unanalyzed"]


def test_save_analysis_overwrites_existing_cache_entry(storage):
    article = _make_article()
    storage.save_articles([article])
    storage.save_analysis(article.article_id, _make_analysis(url=article.url))

    updated = _make_analysis(url=article.url)
    updated.confidence = 90
    updated.sentiment = "bullish"
    storage.save_analysis(article.article_id, updated)

    cached = storage.get_analysis(article.article_id)
    assert cached.confidence == 90
    assert cached.sentiment == "bullish"
