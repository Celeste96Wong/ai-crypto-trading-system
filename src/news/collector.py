"""Orchestrates one full news-collection cycle: fetch -> classify -> store.

This is the single entry point the dashboard's "Refresh news" button
calls. It is a plain function call triggered by the user, not a
background job - there is no scheduler or polling loop anywhere in
this module.
"""

from __future__ import annotations

from src.news.classifier import classify_article
from src.news.rss_fetcher import fetch_all_feeds
from src.news.storage import NewsStorage


def collect_and_store_news(storage: NewsStorage) -> tuple[int, int, list[str]]:
    """Fetch all configured RSS feeds, classify, and store new articles.

    Duplicate articles (same normalized URL) are silently skipped by
    NewsStorage.save_articles; classification runs on every fetched
    article (cheap, local, no API calls) so stored rows always carry
    up-to-date asset/category tags.

    Returns:
        (fetched_count, new_count, errors): how many articles were
        fetched in total, how many were newly stored (excluding
        duplicates), and any per-feed error messages.
    """
    articles, errors = fetch_all_feeds()

    for article in articles:
        article.assets, article.event_categories = classify_article(
            article.title, article.summary
        )

    new_count = storage.save_articles(articles)
    return len(articles), new_count, errors
