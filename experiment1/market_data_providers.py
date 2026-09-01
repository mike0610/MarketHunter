from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Callable

from experiment1.models import MarketQuote, OrderIntent
from experiment1.runtime import AsyncQuoteSource


class AssetClass(str, Enum):
    """
    The non-crypto asset classes already surfaced as UI categories on
    the Active Trading dashboard (dashboard/src/pages/ActiveTrading.jsx:
    stocks, etf, metals, indices), plus CRYPTO for the existing verified
    Binance path. This module never derives a symbol's asset class on
    its own - see MultiAssetQuoteSource - since no evidence-backed
    ticker taxonomy exists anywhere in this repository.
    """

    CRYPTO = "CRYPTO"
    STOCK = "STOCK"
    ETF = "ETF"
    METAL = "METAL"
    US_INDEX = "US_INDEX"


class UnavailableQuoteProvider:
    """
    Read-only, fail-closed placeholder for an asset class with no
    verified, evidence-backed live quote provider configured in this
    environment - no credentials, subscription, or Product Owner-
    approved integration exists in this repository for it.

    Implements the same AsyncQuoteSource contract as every other
    provider (quote_for(intent) -> MarketQuote | None), so it composes
    directly with run_market_cycle today: quote_for() always returns
    None, which run_market_cycle already treats as the existing
    WAITING_EVIDENCE outcome. It NEVER fabricates a price. A real
    provider for this asset class can later replace it in
    MultiAssetQuoteSource's provider mapping with no caller-side change.
    """

    def __init__(self, asset_class: AssetClass, reason: str | None = None) -> None:
        self.asset_class = asset_class
        self.reason = reason or (
            f"no verified read-only quote provider is configured for "
            f"{asset_class.value} in this environment"
        )

    async def quote_for(self, intent: OrderIntent) -> MarketQuote | None:
        return None


class FreshnessGuardedQuoteSource:
    """
    Wraps any AsyncQuoteSource and fails closed (returns None - the
    existing WAITING_EVIDENCE contract) if the wrapped quote's
    observed_at is older than max_age, so stale evidence is never
    passed through to a fill. A None from the wrapped provider passes
    through unchanged. A fresh quote's provenance (source,
    source_reference, observed_at, price) is returned exactly as given
    - never modified, never re-stamped.
    """

    def __init__(self, inner: AsyncQuoteSource, max_age: timedelta) -> None:
        if max_age <= timedelta(0):
            raise ValueError("max_age must be positive")
        self.inner = inner
        self.max_age = max_age

    async def quote_for(self, intent: OrderIntent) -> MarketQuote | None:
        quote = await self.inner.quote_for(intent)
        if quote is None:
            return None
        age = datetime.now(timezone.utc) - quote.observed_at
        if age > self.max_age:
            return None
        return quote


class MultiAssetQuoteSource:
    """
    Routes each intent to the AsyncQuoteSource registered for its asset
    class - the read-only quote-provider abstraction/path that can
    serve every target asset class today: crypto through the existing
    verified Binance path (untouched, passed in as-is), and every
    non-crypto class through whatever is registered for it (an
    UnavailableQuoteProvider until a real evidence-backed provider is
    substituted in - a config-time change, never a runtime guess).

    classify is supplied by the caller: this class never decides on its
    own what asset class a symbol belongs to, since no evidence-backed
    ticker taxonomy exists in this repository. An unclassifiable symbol
    (classify returns None) and a recognized class with no registered
    provider both fail closed the same way - quote_for() returns None.
    """

    def __init__(
        self,
        providers: dict[AssetClass, AsyncQuoteSource],
        classify: Callable[[OrderIntent], AssetClass | None],
    ) -> None:
        self.providers = providers
        self.classify = classify

    async def quote_for(self, intent: OrderIntent) -> MarketQuote | None:
        asset_class = self.classify(intent)
        if asset_class is None:
            return None
        provider = self.providers.get(asset_class)
        if provider is None:
            return None
        return await provider.quote_for(intent)
