from datetime import datetime, timezone

import pytest

from investments.sec_identity import SECCompanyTickerResolver, SECIdentityError


NOW = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)


def test_resolves_ticker_to_authoritative_cik():
    raw = '{"0":{"cik_str":320193,"ticker":"AAPL","title":"Apple Inc."}}'
    x = SECCompanyTickerResolver(
        user_agent="MarketHunter contact@example.invalid",
        fetch_text=lambda url: raw,
        clock=lambda: NOW,
    ).resolve("aapl")
    assert x.symbol == "AAPL"
    assert x.cik == "0000320193"
    assert x.title == "Apple Inc."
    assert x.source_reference == "sec:company_tickers"


def test_unknown_ticker_fails_closed():
    resolver = SECCompanyTickerResolver(
        user_agent="MarketHunter contact@example.invalid",
        fetch_text=lambda url: '{"0":{"cik_str":320193,"ticker":"AAPL","title":"Apple Inc."}}',
    )
    with pytest.raises(SECIdentityError, match="unresolved"):
        resolver.resolve("VWCE")


def test_duplicate_ticker_fails_closed():
    raw = '{"0":{"cik_str":1,"ticker":"ABC","title":"A"},"1":{"cik_str":2,"ticker":"ABC","title":"B"}}'
    resolver = SECCompanyTickerResolver(
        user_agent="MarketHunter contact@example.invalid", fetch_text=lambda url: raw
    )
    with pytest.raises(SECIdentityError, match="ambiguous"):
        resolver.resolve("ABC")
