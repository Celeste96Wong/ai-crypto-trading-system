import json
import os
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
import requests

from src.news import ai_analyst
from src.news.ai_analyst import (
    OpenAIAnalysisError,
    OpenAINotConfiguredError,
    OpenAIQuotaExceededError,
    analyze_article,
    analyze_articles,
    get_api_key,
    is_configured,
    validate_analysis_schema,
)
from src.news.config import OPENAI_API_KEY_ENV_VAR
from src.news.models import Article
from src.news.storage import NewsStorage


VALID_ANALYSIS_PAYLOAD = {
    "headline": "Bitcoin ETF sees record inflows",
    "affected_assets": ["BTC"],
    "sentiment": "bullish",
    "impact_level": "medium",
    "confidence": 70,
    "event_category": "etf_institutional",
    "short_summary": "A spot Bitcoin ETF reported record daily inflows.",
    "potential_market_impact": "Could modestly increase buy-side demand.",
    "impact_horizon": "short-term",
    "reasoning": "Based on confirmed inflow figures reported in the article.",
}


@pytest.fixture
def storage(tmp_path):
    return NewsStorage(db_path=os.path.join(tmp_path, "news.db"))


@pytest.fixture
def article():
    return Article(
        title="Bitcoin ETF sees record inflows",
        url="https://example.com/btc-etf",
        source="TestSource",
        published_at=datetime(2025, 11, 10, tzinfo=timezone.utc),
        summary="A spot Bitcoin ETF reported record daily inflows yesterday.",
    )


@pytest.fixture(autouse=True)
def _clear_api_key(monkeypatch):
    monkeypatch.delenv(OPENAI_API_KEY_ENV_VAR, raising=False)


def _mock_openai_response(payload: dict, status_code: int = 200):
    resp = Mock()
    resp.status_code = status_code
    resp.json.return_value = {
        "choices": [{"message": {"content": json.dumps(payload)}}]
    }
    return resp


# --- Schema validation ---------------------------------------------------


def test_validate_analysis_schema_accepts_valid_payload():
    assert validate_analysis_schema(VALID_ANALYSIS_PAYLOAD) == []


def test_validate_analysis_schema_rejects_missing_field():
    bad = {k: v for k, v in VALID_ANALYSIS_PAYLOAD.items() if k != "confidence"}
    errors = validate_analysis_schema(bad)
    assert any("confidence" in e for e in errors)


def test_validate_analysis_schema_rejects_invalid_sentiment():
    bad = dict(VALID_ANALYSIS_PAYLOAD, sentiment="very bullish")
    errors = validate_analysis_schema(bad)
    assert any("sentiment" in e for e in errors)


def test_validate_analysis_schema_rejects_out_of_range_confidence():
    bad = dict(VALID_ANALYSIS_PAYLOAD, confidence=150)
    errors = validate_analysis_schema(bad)
    assert any("confidence" in e for e in errors)


def test_validate_analysis_schema_rejects_unsupported_asset():
    bad = dict(VALID_ANALYSIS_PAYLOAD, affected_assets=["DOGE"])
    errors = validate_analysis_schema(bad)
    assert any("affected_assets" in e for e in errors)


def test_validate_analysis_schema_accepts_empty_affected_assets():
    payload = dict(VALID_ANALYSIS_PAYLOAD, affected_assets=[])
    assert validate_analysis_schema(payload) == []


def test_validate_analysis_schema_rejects_non_dict():
    assert validate_analysis_schema(["not", "a", "dict"]) != []


# --- Missing API key handling ---------------------------------------------


def test_is_configured_false_without_key():
    assert is_configured() is False
    assert get_api_key() is None


def test_analyze_article_raises_when_api_key_missing(article, storage):
    with pytest.raises(OpenAINotConfiguredError):
        analyze_article(article, storage)


def test_analyze_articles_reports_missing_key_without_raising(article, storage):
    results, errors = analyze_articles([article], storage)

    assert results == []
    assert len(errors) == 1
    assert "OPENAI_API_KEY" in errors[0]


# --- Successful analysis + caching -----------------------------------------


@patch("src.news.ai_analyst.requests.post")
def test_analyze_article_succeeds_and_caches_result(mock_post, article, storage, monkeypatch):
    monkeypatch.setenv(OPENAI_API_KEY_ENV_VAR, "test-key")
    mock_post.return_value = _mock_openai_response(VALID_ANALYSIS_PAYLOAD)

    analysis = analyze_article(article, storage)

    assert analysis.headline == VALID_ANALYSIS_PAYLOAD["headline"]
    assert analysis.affected_assets == ["BTC"]
    assert analysis.source_url == article.url
    assert storage.has_analysis(article.article_id) is True
    assert mock_post.call_count == 1


@patch("src.news.ai_analyst.requests.post")
def test_analyze_article_does_not_call_api_again_once_cached(
    mock_post, article, storage, monkeypatch
):
    monkeypatch.setenv(OPENAI_API_KEY_ENV_VAR, "test-key")
    mock_post.return_value = _mock_openai_response(VALID_ANALYSIS_PAYLOAD)

    analyze_article(article, storage)
    analyze_article(article, storage)
    analyze_article(article, storage)

    assert mock_post.call_count == 1  # cached on subsequent calls


@patch("src.news.ai_analyst.requests.post")
def test_analyze_article_never_sends_api_key_in_message_bodies(
    mock_post, article, storage, monkeypatch
):
    """The API key must only ever appear in the Authorization header,
    never echoed back into any exception message."""
    monkeypatch.setenv(OPENAI_API_KEY_ENV_VAR, "super-secret-key-abc123")
    mock_post.return_value = Mock(status_code=401)

    with pytest.raises(OpenAIAnalysisError) as exc_info:
        analyze_article(article, storage)

    assert "super-secret-key-abc123" not in str(exc_info.value)


# --- API errors and quota exhaustion ---------------------------------------


@patch("src.news.ai_analyst.requests.post")
def test_analyze_article_raises_quota_exceeded_on_429(mock_post, article, storage, monkeypatch):
    monkeypatch.setenv(OPENAI_API_KEY_ENV_VAR, "test-key")
    mock_post.return_value = Mock(status_code=429)

    with pytest.raises(OpenAIQuotaExceededError):
        analyze_article(article, storage)

    assert storage.has_analysis(article.article_id) is False


@patch("src.news.ai_analyst.requests.post")
def test_analyze_article_raises_on_invalid_api_key(mock_post, article, storage, monkeypatch):
    monkeypatch.setenv(OPENAI_API_KEY_ENV_VAR, "bad-key")
    mock_post.return_value = Mock(status_code=401)

    with pytest.raises(OpenAIAnalysisError):
        analyze_article(article, storage)


@patch("src.news.ai_analyst.requests.post")
def test_analyze_article_raises_on_network_error(mock_post, article, storage, monkeypatch):
    monkeypatch.setenv(OPENAI_API_KEY_ENV_VAR, "test-key")
    mock_post.side_effect = requests.exceptions.ConnectionError("internal detail 42")

    with pytest.raises(OpenAIAnalysisError) as exc_info:
        analyze_article(article, storage)

    assert "internal detail 42" not in str(exc_info.value)


@patch("src.news.ai_analyst.requests.post")
def test_analyze_article_raises_on_schema_violation(mock_post, article, storage, monkeypatch):
    monkeypatch.setenv(OPENAI_API_KEY_ENV_VAR, "test-key")
    bad_payload = dict(VALID_ANALYSIS_PAYLOAD, sentiment="extremely bullish")
    mock_post.return_value = _mock_openai_response(bad_payload)

    with pytest.raises(OpenAIAnalysisError):
        analyze_article(article, storage)

    assert storage.has_analysis(article.article_id) is False


@patch("src.news.ai_analyst.requests.post")
def test_analyze_article_raises_on_malformed_json_content(mock_post, article, storage, monkeypatch):
    monkeypatch.setenv(OPENAI_API_KEY_ENV_VAR, "test-key")
    resp = Mock(status_code=200)
    resp.json.return_value = {"choices": [{"message": {"content": "not valid json {{"}}]}
    mock_post.return_value = resp

    with pytest.raises(OpenAIAnalysisError):
        analyze_article(article, storage)


# --- Batch analysis: limits + skipping already-analyzed articles -----------


@patch("src.news.ai_analyst.requests.post")
def test_analyze_articles_respects_batch_limit(mock_post, storage, monkeypatch):
    monkeypatch.setenv(OPENAI_API_KEY_ENV_VAR, "test-key")
    mock_post.return_value = _mock_openai_response(VALID_ANALYSIS_PAYLOAD)
    articles = [
        Article(
            title=f"Article {i}",
            url=f"https://example.com/{i}",
            source="Test",
            published_at=datetime(2025, 11, 10, tzinfo=timezone.utc),
        )
        for i in range(5)
    ]

    results, errors = analyze_articles(articles, storage, limit=2)

    assert len(results) == 2
    assert errors == []
    assert mock_post.call_count == 2


@patch("src.news.ai_analyst.requests.post")
def test_analyze_articles_skips_already_analyzed_articles(mock_post, storage, monkeypatch):
    monkeypatch.setenv(OPENAI_API_KEY_ENV_VAR, "test-key")
    mock_post.return_value = _mock_openai_response(VALID_ANALYSIS_PAYLOAD)
    already_analyzed = Article(
        title="Already analyzed",
        url="https://example.com/already",
        source="Test",
        published_at=datetime(2025, 11, 10, tzinfo=timezone.utc),
    )
    storage.save_articles([already_analyzed])
    analyze_article(already_analyzed, storage)
    assert mock_post.call_count == 1

    new_article = Article(
        title="New",
        url="https://example.com/new",
        source="Test",
        published_at=datetime(2025, 11, 10, tzinfo=timezone.utc),
    )

    results, errors = analyze_articles([already_analyzed, new_article], storage, limit=5)

    # Only the new article should trigger a second API call.
    assert mock_post.call_count == 2
    assert len(results) == 1
    assert results[0].source_url == new_article.url
