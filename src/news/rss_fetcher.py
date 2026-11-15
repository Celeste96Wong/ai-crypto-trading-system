"""Fetches and normalizes articles from free, public RSS feeds.

No paid news API is used. Network failures and malformed feeds/entries
are handled gracefully: a broken feed or a bad entry is skipped rather
than raising and interrupting collection from the other feeds.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

import feedparser
import requests

from src.news.config import RSS_REQUEST_TIMEOUT_SECONDS, RSS_SOURCES
from src.news.models import Article

_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


class FeedFetchError(Exception):
    """Raised when a single feed cannot be reached or read.

    Callers collecting from multiple feeds should catch this per feed
    and continue with the others rather than aborting the whole batch.
    """


def _clean_text(raw: str | None) -> str:
    """Strip HTML tags and collapse whitespace from feed text fields."""
    if not raw:
        return ""
    without_tags = _TAG_RE.sub(" ", raw)
    return _WHITESPACE_RE.sub(" ", without_tags).strip()


def _parse_published_at(entry, fallback: datetime) -> datetime:
    """Extract a UTC-aware published time from a feedparser entry.

    Falls back to `fallback` (normally "now") if the feed does not
    provide a parseable date - we would rather show the article with
    an approximate time than drop it entirely.
    """
    for field_name in ("published_parsed", "updated_parsed"):
        time_struct = getattr(entry, field_name, None)
        if time_struct is not None:
            try:
                # feedparser's *_parsed fields are already UTC struct_time.
                timestamp = (
                    datetime(*time_struct[:6], tzinfo=timezone.utc).timestamp()
                )
                return datetime.fromtimestamp(timestamp, tz=timezone.utc)
            except (TypeError, ValueError, OverflowError):
                continue
    return fallback


def _entry_to_article(entry, source_name: str) -> Article | None:
    """Convert one feedparser entry into an Article, or None if unusable.

    An entry without a title or a link carries no useful information
    for this app, so it is skipped rather than stored as a blank row.
    """
    title = _clean_text(getattr(entry, "title", None))
    url = getattr(entry, "link", None)
    if not title or not url:
        return None

    now = datetime.now(timezone.utc)
    return Article(
        title=title,
        url=url.strip(),
        source=source_name,
        published_at=_parse_published_at(entry, fallback=now),
        summary=_clean_text(getattr(entry, "summary", None)),
        fetched_at=now,
    )


def fetch_feed(source_name: str, feed_url: str, timeout: int = RSS_REQUEST_TIMEOUT_SECONDS) -> list[Article]:
    """Fetch and normalize articles from a single RSS feed.

    Raises FeedFetchError if the feed cannot be reached at all.
    Individual malformed entries within a reachable feed are skipped
    silently rather than raising, so one bad entry doesn't lose the
    rest of the feed.
    """
    try:
        response = requests.get(feed_url, timeout=timeout)
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        raise FeedFetchError(f"Could not reach feed '{source_name}'.") from exc

    parsed = feedparser.parse(response.content)

    # feedparser sets `bozo` on malformed XML but often still manages to
    # recover some entries - only treat it as a hard failure when there
    # is truly nothing usable in the feed.
    if parsed.bozo and not parsed.entries:
        raise FeedFetchError(f"Feed '{source_name}' returned malformed data.")

    articles = []
    for entry in parsed.entries:
        article = _entry_to_article(entry, source_name)
        if article is not None:
            articles.append(article)
    return articles


def fetch_all_feeds(sources: list[tuple[str, str]] | None = None) -> tuple[list[Article], list[str]]:
    """Fetch articles from every configured RSS source.

    Returns (articles, errors): articles from every feed that could be
    read, and a list of short error messages for feeds that could not
    be - collection continues across sources even if one fails.
    """
    sources = sources if sources is not None else RSS_SOURCES
    all_articles: list[Article] = []
    errors: list[str] = []

    for source_name, feed_url in sources:
        try:
            all_articles.extend(fetch_feed(source_name, feed_url))
        except FeedFetchError as exc:
            errors.append(str(exc))

    return all_articles, errors
