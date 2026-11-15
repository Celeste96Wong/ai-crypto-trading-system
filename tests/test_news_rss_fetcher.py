from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
import requests

from src.news.models import Article
from src.news.rss_fetcher import FeedFetchError, fetch_all_feeds, fetch_feed

VALID_RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <item>
      <title>Bitcoin hits new high</title>
      <link>https://example.com/btc-high</link>
      <description><![CDATA[<p>Bitcoin price <b>surges</b> past $100k.</p>]]></description>
      <pubDate>Mon, 10 Nov 2025 12:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Ethereum upgrade announced</title>
      <link>https://example.com/eth-upgrade</link>
      <description>Ethereum developers announce a new network upgrade.</description>
      <pubDate>Tue, 11 Nov 2025 08:30:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""

MISSING_FIELDS_RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <item>
      <title>No link article</title>
      <description>This entry has no link and must be skipped.</description>
    </item>
    <item>
      <title>Good article</title>
      <link>https://example.com/good</link>
      <description>This one is fine.</description>
      <pubDate>Wed, 12 Nov 2025 00:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""

NO_DATE_RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <item>
      <title>Undated article</title>
      <link>https://example.com/undated</link>
      <description>No pubDate supplied.</description>
    </item>
  </channel>
</rss>
"""


def _mock_response(content: bytes, status_ok: bool = True):
    resp = Mock()
    resp.content = content
    if status_ok:
        resp.raise_for_status.return_value = None
    else:
        resp.raise_for_status.side_effect = requests.exceptions.HTTPError("bad status")
    return resp


@patch("src.news.rss_fetcher.requests.get")
def test_fetch_feed_parses_valid_entries(mock_get):
    mock_get.return_value = _mock_response(VALID_RSS)

    articles = fetch_feed("TestSource", "https://example.com/rss")

    assert len(articles) == 2
    assert all(isinstance(a, Article) for a in articles)
    assert articles[0].title == "Bitcoin hits new high"
    assert articles[0].url == "https://example.com/btc-high"
    assert articles[0].source == "TestSource"
    assert "surges" in articles[0].summary
    assert "<" not in articles[0].summary  # HTML tags stripped
    assert articles[0].published_at.tzinfo is not None
    assert articles[0].published_at == datetime(2025, 11, 10, 12, 0, 0, tzinfo=timezone.utc)


@patch("src.news.rss_fetcher.requests.get")
def test_fetch_feed_skips_entries_missing_required_fields(mock_get):
    mock_get.return_value = _mock_response(MISSING_FIELDS_RSS)

    articles = fetch_feed("TestSource", "https://example.com/rss")

    assert len(articles) == 1
    assert articles[0].title == "Good article"


@patch("src.news.rss_fetcher.requests.get")
def test_fetch_feed_falls_back_to_now_when_no_date_available(mock_get):
    mock_get.return_value = _mock_response(NO_DATE_RSS)

    before = datetime.now(timezone.utc)
    articles = fetch_feed("TestSource", "https://example.com/rss")
    after = datetime.now(timezone.utc)

    assert len(articles) == 1
    assert before <= articles[0].published_at <= after


@patch("src.news.rss_fetcher.requests.get")
def test_fetch_feed_raises_on_network_error(mock_get):
    mock_get.side_effect = requests.exceptions.ConnectionError("down")

    with pytest.raises(FeedFetchError):
        fetch_feed("TestSource", "https://example.com/rss")


@patch("src.news.rss_fetcher.requests.get")
def test_fetch_feed_raises_on_http_error(mock_get):
    mock_get.return_value = _mock_response(b"", status_ok=False)

    with pytest.raises(FeedFetchError):
        fetch_feed("TestSource", "https://example.com/rss")


@patch("src.news.rss_fetcher.requests.get")
def test_fetch_feed_raises_on_completely_malformed_feed(mock_get):
    mock_get.return_value = _mock_response(b"this is not xml at all {{{")

    with pytest.raises(FeedFetchError):
        fetch_feed("TestSource", "https://example.com/rss")


@patch("src.news.rss_fetcher.fetch_feed")
def test_fetch_all_feeds_continues_after_one_feed_fails(mock_fetch_feed):
    good_article = Article(
        title="Good",
        url="https://example.com/good",
        source="GoodSource",
        published_at=datetime.now(timezone.utc),
    )

    def side_effect(source_name, feed_url, timeout=10):
        if source_name == "Broken":
            raise FeedFetchError("Could not reach feed 'Broken'.")
        return [good_article]

    mock_fetch_feed.side_effect = side_effect

    articles, errors = fetch_all_feeds([("Broken", "https://x"), ("Good", "https://y")])

    assert articles == [good_article]
    assert len(errors) == 1
    assert "Broken" in errors[0]
