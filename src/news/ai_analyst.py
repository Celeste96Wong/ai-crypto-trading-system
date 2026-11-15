"""OpenAI-powered news analyst: turns a news article into a structured,
schema-validated market-impact analysis.

Cost-control measures (the project's OpenAI budget is ~$5 total):
- Uses a small, cheap model (OPENAI_MODEL).
- Prompts are kept short: only the title, a truncated summary, source
  and URL are sent - no raw HTML, no full article body.
- Analysis is only ever triggered by an explicit user action (the
  dashboard's "Analyze with AI" button) - never a background loop or
  timer.
- Every result is cached in NewsStorage, keyed by article id, and is
  never re-requested for an article that already has one.
- Batches are capped by `limit`, itself bounded by
  MAX_ANALYSIS_BATCH_LIMIT.

No API key is ever hardcoded: it is read from the OPENAI_API_KEY
environment variable at call time. News collection and classification
both work without it; only this module needs it, and it degrades
gracefully when the key is missing or the API fails/is rate-limited.
"""

from __future__ import annotations

import json
import os

import requests

from src.news.config import (
    DEFAULT_ANALYSIS_BATCH_LIMIT,
    IMPACT_HORIZON_VALUES,
    IMPACT_LEVEL_VALUES,
    MAX_ANALYSIS_BATCH_LIMIT,
    MAX_SUMMARY_CHARS_FOR_PROMPT,
    OPENAI_API_KEY_ENV_VAR,
    OPENAI_API_URL,
    OPENAI_MODEL,
    OPENAI_REQUEST_TIMEOUT_SECONDS,
    SENTIMENT_VALUES,
    SUPPORTED_NEWS_ASSETS,
)
from src.news.models import Article, NewsAnalysis
from src.news.storage import NewsStorage


class OpenAINotConfiguredError(Exception):
    """Raised when OPENAI_API_KEY is not set in the environment."""


class OpenAIAnalysisError(Exception):
    """Raised when the OpenAI API call fails or returns an unusable result.

    Messages are deliberately plain and never include the raw API key,
    raw response bodies, or other request/response internals.
    """


class OpenAIQuotaExceededError(OpenAIAnalysisError):
    """Raised specifically when the OpenAI API reports quota/rate limits."""


REQUIRED_ANALYSIS_FIELDS = [
    "headline",
    "affected_assets",
    "sentiment",
    "impact_level",
    "confidence",
    "event_category",
    "short_summary",
    "potential_market_impact",
    "impact_horizon",
    "reasoning",
]


def get_api_key() -> str | None:
    """Read the OpenAI API key from the environment. Never hardcoded."""
    return os.environ.get(OPENAI_API_KEY_ENV_VAR)


def is_configured() -> bool:
    """Whether AI analysis is currently usable (an API key is set)."""
    return bool(get_api_key())


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "..."


def _build_prompt(article: Article) -> str:
    summary = _truncate(article.summary, MAX_SUMMARY_CHARS_FOR_PROMPT)
    return (
        "Analyze this cryptocurrency news article strictly for its "
        f"potential market impact on these assets only: "
        f"{', '.join(SUPPORTED_NEWS_ASSETS)}.\n\n"
        f"Title: {article.title}\n"
        f"Source: {article.source}\n"
        f"Published (UTC): {article.published_at.isoformat()}\n"
        f"Summary: {summary or '(no summary available)'}\n"
        f"URL: {article.url}\n"
    )


_SYSTEM_PROMPT = (
    "You are a cautious crypto market news analyst. You only use "
    "information actually present in the article given to you - you "
    "never invent facts, prices, or outcomes that are not stated. You "
    "clearly separate confirmed facts from speculation, and you never "
    "claim that a news event guarantees any price movement. If the "
    "article does not contain enough information to assess impact, say "
    "so explicitly and give a low confidence score. "
    "Respond with ONLY a single JSON object with exactly these keys: "
    'headline (string), affected_assets (array of strings, a subset of '
    '["BTC", "ETH", "SOL", "XRP"], possibly empty), '
    'sentiment (one of "bullish", "bearish", "neutral", "mixed"), '
    'impact_level (one of "low", "medium", "high"), '
    "confidence (integer 0-100), "
    "event_category (short string), "
    "short_summary (string, 1-2 sentences), "
    "potential_market_impact (string, phrased as a possibility, never a "
    "guarantee), "
    'impact_horizon (one of "short-term", "medium-term", "long-term", '
    '"uncertain"), '
    "reasoning (string, briefly explains the assessment and notes "
    "whether it rests on confirmed facts or speculation)."
)


def validate_analysis_schema(data) -> list[str]:
    """Validate a parsed AI response against the required schema.

    Returns a list of human-readable problems; an empty list means the
    data is well-formed enough to build a NewsAnalysis from.
    """
    if not isinstance(data, dict):
        return ["Response is not a JSON object."]

    errors = [f"Missing field: {name}" for name in REQUIRED_ANALYSIS_FIELDS if name not in data]
    if errors:
        return errors

    if not isinstance(data["affected_assets"], list) or not all(
        isinstance(item, str) for item in data["affected_assets"]
    ):
        errors.append("affected_assets must be a list of strings.")
    elif not set(data["affected_assets"]).issubset(set(SUPPORTED_NEWS_ASSETS)):
        errors.append("affected_assets contains an unsupported asset.")

    if data["sentiment"] not in SENTIMENT_VALUES:
        errors.append("sentiment has an invalid value.")

    if data["impact_level"] not in IMPACT_LEVEL_VALUES:
        errors.append("impact_level has an invalid value.")

    if data["impact_horizon"] not in IMPACT_HORIZON_VALUES:
        errors.append("impact_horizon has an invalid value.")

    confidence = data["confidence"]
    if (
        not isinstance(confidence, int)
        or isinstance(confidence, bool)
        or not (0 <= confidence <= 100)
    ):
        errors.append("confidence must be an integer between 0 and 100.")

    for field_name in (
        "headline",
        "event_category",
        "short_summary",
        "potential_market_impact",
        "reasoning",
    ):
        if not isinstance(data[field_name], str):
            errors.append(f"{field_name} must be a string.")

    return errors


def _call_openai(prompt: str, api_key: str) -> dict:
    """Call the OpenAI Chat Completions API and return the parsed JSON body.

    Raises OpenAIAnalysisError / OpenAIQuotaExceededError on any
    failure, with a sanitized message - never the raw response body,
    headers, or the API key.
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0,
    }

    try:
        response = requests.post(
            OPENAI_API_URL,
            headers=headers,
            json=payload,
            timeout=OPENAI_REQUEST_TIMEOUT_SECONDS,
        )
    except requests.exceptions.RequestException as exc:
        raise OpenAIAnalysisError("Could not reach the OpenAI API.") from exc

    if response.status_code == 429:
        raise OpenAIQuotaExceededError(
            "OpenAI API quota or rate limit exceeded. Try again later."
        )
    if response.status_code == 401:
        raise OpenAIAnalysisError("OpenAI API rejected the API key.")
    if response.status_code >= 400:
        raise OpenAIAnalysisError(
            f"OpenAI API request failed (HTTP {response.status_code})."
        )

    try:
        body = response.json()
        content = body["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise OpenAIAnalysisError("OpenAI API returned an unexpected response.") from exc

    try:
        return json.loads(content)
    except (ValueError, TypeError) as exc:
        raise OpenAIAnalysisError("OpenAI API did not return valid JSON.") from exc


def analyze_article(article: Article, storage: NewsStorage, force: bool = False) -> NewsAnalysis:
    """Return a structured AI analysis for one article.

    Returns a cached result if one already exists (unless `force` is
    set), so the same article is never billed twice unnecessarily.

    Raises:
        OpenAINotConfiguredError: if OPENAI_API_KEY is not set.
        OpenAIQuotaExceededError: if the API reports quota exhaustion.
        OpenAIAnalysisError: for any other API or validation failure.
    """
    if not force:
        cached = storage.get_analysis(article.article_id)
        if cached is not None:
            return cached

    api_key = get_api_key()
    if not api_key:
        raise OpenAINotConfiguredError(
            "OPENAI_API_KEY is not set; AI analysis is unavailable."
        )

    prompt = _build_prompt(article)
    data = _call_openai(prompt, api_key)

    errors = validate_analysis_schema(data)
    if errors:
        raise OpenAIAnalysisError(
            "OpenAI API response did not match the expected analysis format."
        )

    analysis = NewsAnalysis(
        headline=data["headline"],
        affected_assets=data["affected_assets"],
        sentiment=data["sentiment"],
        impact_level=data["impact_level"],
        confidence=data["confidence"],
        event_category=data["event_category"],
        short_summary=data["short_summary"],
        potential_market_impact=data["potential_market_impact"],
        impact_horizon=data["impact_horizon"],
        reasoning=data["reasoning"],
        source_url=article.url,
        model=OPENAI_MODEL,
    )
    storage.save_analysis(article.article_id, analysis)
    return analysis


def analyze_articles(
    articles: list[Article],
    storage: NewsStorage,
    limit: int = DEFAULT_ANALYSIS_BATCH_LIMIT,
) -> tuple[list[NewsAnalysis], list[str]]:
    """Analyze up to `limit` articles that have no cached analysis yet.

    This is the entry point the dashboard's manual "Analyze with AI"
    button calls - AI analysis is never run from a background loop or
    timer. Articles that already have a cached analysis are skipped
    for free (no API call) rather than re-analyzed.

    Returns (results, errors): successful analyses, and short error
    messages for anything that failed. Stops early (without raising)
    if the API key is missing or quota is exhausted, since further
    attempts in the same batch would just fail the same way.
    """
    limit = max(0, min(limit, MAX_ANALYSIS_BATCH_LIMIT))
    results: list[NewsAnalysis] = []
    errors: list[str] = []

    to_analyze = [a for a in articles if not storage.has_analysis(a.article_id)][:limit]

    for article in to_analyze:
        try:
            results.append(analyze_article(article, storage))
        except OpenAINotConfiguredError as exc:
            errors.append(str(exc))
            break
        except OpenAIQuotaExceededError as exc:
            errors.append(str(exc))
            break
        except OpenAIAnalysisError as exc:
            errors.append(f"{article.title[:60]}: {exc}")

    return results, errors
