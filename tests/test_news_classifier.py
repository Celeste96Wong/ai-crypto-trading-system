from src.news.classifier import categorize_event, classify_article, identify_assets
from src.news.config import UNCATEGORIZED_EVENT_CATEGORY


def test_identify_assets_matches_bitcoin():
    assert identify_assets("Bitcoin price surges past $100,000") == ["BTC"]


def test_identify_assets_matches_multiple_assets():
    result = identify_assets("Ethereum and Solana both rally while Bitcoin consolidates")
    assert set(result) == {"BTC", "ETH", "SOL"}


def test_identify_assets_does_not_false_positive_on_substrings():
    # "solution" contains "sol" and "method" contains "eth" as raw
    # substrings; neither should be matched as the asset.
    result = identify_assets("The company announced a new solution and a method for scaling.")
    assert result == []


def test_identify_assets_returns_empty_for_unrelated_text():
    assert identify_assets("The weather today is sunny with a light breeze.") == []


def test_identify_assets_matches_ripple_for_xrp():
    assert identify_assets("Ripple wins a key court ruling") == ["XRP"]


def test_categorize_event_matches_security_incident():
    result = categorize_event("Exchange suffers a major hack, millions stolen")
    assert "security_incident" in result


def test_categorize_event_matches_regulation_policy():
    result = categorize_event("SEC regulation tightens around crypto exchanges")
    assert "regulation_policy" in result


def test_categorize_event_matches_multiple_categories():
    result = categorize_event(
        "SEC regulation forces exchange delisting after a security breach"
    )
    assert "regulation_policy" in result
    assert "exchange_market" in result
    assert "security_incident" in result


def test_categorize_event_returns_uncategorized_for_unrelated_text():
    assert categorize_event("A cat sat on a mat.") == [UNCATEGORIZED_EVENT_CATEGORY]


def test_classify_article_combines_title_and_summary():
    assets, categories = classify_article(
        title="Bitcoin ETF sees record inflows",
        summary="Institutional investors pour billions into the new fund.",
    )
    assert assets == ["BTC"]
    assert "etf_institutional" in categories


def test_classify_article_does_not_assume_every_article_affects_every_asset():
    assets, _ = classify_article(
        title="Local bakery wins award for best croissant",
        summary="The bakery has been open for ten years.",
    )
    assert assets == []
