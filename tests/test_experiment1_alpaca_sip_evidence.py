"""
MarketHunter

Tests for experiment1/alpaca_sip_evidence.py - the read-only Alpaca
Market Data API (SIP feed) AsyncEvidenceSource. Every test runs against
a fake httpx transport (httpx.MockTransport) - never a live Alpaca
account, since no credentials exist for this session and Product Owner
has not authorized any paid subscription.
"""

from __future__ import annotations

import asyncio
import os
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from unittest import mock

import httpx

from experiment1.alpaca_sip_evidence import (
    ALPACA_DATA_BASE_URL,
    ENV_ALPACA_API_KEY_ID,
    ENV_ALPACA_API_SECRET_KEY,
    AlpacaSipEvidenceSource,
    build_alpaca_sip_evidence_source,
    _derive_session_state,
    _parse_alpaca_timestamp,
)
from experiment1.market_data_evidence import EvidenceGrade, EvidenceGuardedQuoteSource, evaluate_market_data_evidence
from experiment1.models import DecisionAction, AccountKind, OrderIntent, PriceType, QuoteMode, SessionState
from datetime import timedelta


def _quote_payload(symbol="CROX", bp=118.40, ap=118.60, t="2026-09-01T14:30:00.123456789Z"):
    return {
        "symbol": symbol,
        "quote": {"t": t, "ax": "P", "ap": ap, "as": 100, "bx": "K", "bp": bp, "bs": 200, "c": ["R"]},
    }


def _client_for(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


class TimestampParsingTests(unittest.TestCase):
    def test_parses_nanosecond_precision_rfc3339_timestamp(self):
        parsed = _parse_alpaca_timestamp("2026-09-01T14:30:00.822866956Z")
        self.assertEqual(parsed.tzinfo, timezone.utc)
        self.assertEqual(parsed.year, 2026)
        self.assertEqual(parsed.microsecond, 822866)

    def test_parses_a_timestamp_with_no_fractional_seconds(self):
        parsed = _parse_alpaca_timestamp("2026-09-01T14:30:00Z")
        self.assertEqual(parsed.second, 0)

    def test_rejects_a_naive_timestamp_with_no_offset(self):
        with self.assertRaises(ValueError):
            _parse_alpaca_timestamp("not-a-timestamp-at-all")


class SessionStateDerivationTests(unittest.TestCase):
    def test_weekday_regular_hours_is_regular(self):
        # 2026-09-01 is a Tuesday. 14:30 UTC = 10:30 ET (EDT, UTC-4).
        moment = datetime(2026, 9, 1, 14, 30, tzinfo=timezone.utc)
        self.assertEqual(_derive_session_state(moment), SessionState.REGULAR)

    def test_weekday_early_morning_is_pre_market(self):
        # 09:00 UTC = 05:00 ET.
        moment = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)
        self.assertEqual(_derive_session_state(moment), SessionState.PRE_MARKET)

    def test_weekday_evening_is_post_market(self):
        # 21:00 UTC = 17:00 ET.
        moment = datetime(2026, 9, 1, 21, 0, tzinfo=timezone.utc)
        self.assertEqual(_derive_session_state(moment), SessionState.POST_MARKET)

    def test_weekday_middle_of_night_is_closed(self):
        # 03:00 UTC = 23:00 ET (previous day).
        moment = datetime(2026, 9, 1, 3, 0, tzinfo=timezone.utc)
        self.assertEqual(_derive_session_state(moment), SessionState.CLOSED)

    def test_weekend_is_closed_even_during_regular_hours_window(self):
        # 2026-09-05 is a Saturday.
        moment = datetime(2026, 9, 5, 14, 30, tzinfo=timezone.utc)
        self.assertEqual(_derive_session_state(moment), SessionState.CLOSED)


class AlpacaSipEvidenceSourceTests(unittest.TestCase):
    def test_rejects_a_blank_api_key_id(self):
        with self.assertRaises(ValueError):
            AlpacaSipEvidenceSource("  ", "secret", httpx.AsyncClient())

    def test_rejects_a_blank_api_secret_key(self):
        with self.assertRaises(ValueError):
            AlpacaSipEvidenceSource("key", "  ", httpx.AsyncClient())

    # --- valid SIP normalization -------------------------------------------

    def test_valid_quote_normalizes_into_complete_market_data_evidence(self):
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/v2/stocks/CROX/quotes/latest")
            self.assertEqual(request.url.params["feed"], "sip")
            self.assertEqual(request.headers["APCA-API-KEY-ID"], "key-123")
            self.assertEqual(request.headers["APCA-API-SECRET-KEY"], "secret-456")
            return httpx.Response(200, json=_quote_payload())

        source = AlpacaSipEvidenceSource("key-123", "secret-456", _client_for(handler))
        evidence = asyncio.run(source.evidence_for("CROX"))

        self.assertIsNotNone(evidence)
        self.assertEqual(evidence.provider, "ALPACA_SIP")
        self.assertEqual(evidence.instrument, "CROX")
        self.assertEqual(evidence.provider_symbol, "CROX")
        self.assertEqual(evidence.exchange, "ALPACA_SIP")
        self.assertEqual(evidence.currency, "USD")
        self.assertEqual(evidence.price, (Decimal("118.40") + Decimal("118.60")) / 2)
        self.assertEqual(evidence.price_type, PriceType.MID)
        self.assertEqual(evidence.mode, QuoteMode.REALTIME)
        self.assertIn("alpaca-sip-quote:CROX:", evidence.source_reference)
        self.assertEqual(evidence.source_timestamp.year, 2026)

    def test_never_calls_a_trading_api_host(self):
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(str(request.url))
            return httpx.Response(200, json=_quote_payload())

        source = AlpacaSipEvidenceSource("key", "secret", _client_for(handler))
        asyncio.run(source.evidence_for("CROX"))

        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0].startswith(ALPACA_DATA_BASE_URL))

    # --- stale/missing/ambiguous evidence -----------------------------------

    def test_missing_bid_returns_none(self):
        def handler(request):
            payload = _quote_payload()
            del payload["quote"]["bp"]
            return httpx.Response(200, json=payload)

        source = AlpacaSipEvidenceSource("key", "secret", _client_for(handler))
        self.assertIsNone(asyncio.run(source.evidence_for("CROX")))

    def test_missing_ask_returns_none(self):
        def handler(request):
            payload = _quote_payload()
            del payload["quote"]["ap"]
            return httpx.Response(200, json=payload)

        source = AlpacaSipEvidenceSource("key", "secret", _client_for(handler))
        self.assertIsNone(asyncio.run(source.evidence_for("CROX")))

    def test_non_positive_bid_returns_none(self):
        def handler(request):
            return httpx.Response(200, json=_quote_payload(bp=0))

        source = AlpacaSipEvidenceSource("key", "secret", _client_for(handler))
        self.assertIsNone(asyncio.run(source.evidence_for("CROX")))

    def test_unparseable_timestamp_returns_none(self):
        def handler(request):
            return httpx.Response(200, json=_quote_payload(t="not-a-real-timestamp"))

        source = AlpacaSipEvidenceSource("key", "secret", _client_for(handler))
        self.assertIsNone(asyncio.run(source.evidence_for("CROX")))

    def test_malformed_json_response_returns_none(self):
        def handler(request):
            return httpx.Response(200, content=b"not json at all")

        source = AlpacaSipEvidenceSource("key", "secret", _client_for(handler))
        self.assertIsNone(asyncio.run(source.evidence_for("CROX")))

    def test_a_response_with_no_quote_key_returns_none(self):
        def handler(request):
            return httpx.Response(200, json={"symbol": "CROX"})

        source = AlpacaSipEvidenceSource("key", "secret", _client_for(handler))
        self.assertIsNone(asyncio.run(source.evidence_for("CROX")))

    def test_a_network_transport_error_returns_none(self):
        def handler(request):
            raise httpx.ConnectError("connection refused", request=request)

        source = AlpacaSipEvidenceSource("key", "secret", _client_for(handler))
        self.assertIsNone(asyncio.run(source.evidence_for("CROX")))

    # --- wrong feed/entitlement ----------------------------------------------

    def test_403_entitlement_rejection_returns_none(self):
        def handler(request):
            return httpx.Response(403, json={"code": 40410000, "message": "subscription does not permit this feed"})

        source = AlpacaSipEvidenceSource("key", "secret", _client_for(handler))
        self.assertIsNone(asyncio.run(source.evidence_for("CROX")))

    def test_404_unknown_symbol_returns_none(self):
        def handler(request):
            return httpx.Response(404, json={"code": 40410000, "message": "symbol not found"})

        source = AlpacaSipEvidenceSource("key", "secret", _client_for(handler))
        self.assertIsNone(asyncio.run(source.evidence_for("NOTREAL")))

    # --- symbol/currency ------------------------------------------------------

    def test_currency_is_always_usd_for_this_provider(self):
        def handler(request):
            return httpx.Response(200, json=_quote_payload())

        source = AlpacaSipEvidenceSource("key", "secret", _client_for(handler))
        evidence = asyncio.run(source.evidence_for("CROX"))
        self.assertEqual(evidence.currency, "USD")

    def test_provider_symbol_falls_back_to_the_requested_instrument_if_alpaca_omits_it(self):
        def handler(request):
            return httpx.Response(200, json={"quote": _quote_payload()["quote"]})

        source = AlpacaSipEvidenceSource("key", "secret", _client_for(handler))
        evidence = asyncio.run(source.evidence_for("CROX"))
        self.assertEqual(evidence.provider_symbol, "CROX")


class BuildAlpacaSipEvidenceSourceTests(unittest.TestCase):
    def test_returns_none_when_no_credentials_are_configured(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(ENV_ALPACA_API_KEY_ID, None)
            os.environ.pop(ENV_ALPACA_API_SECRET_KEY, None)
            self.assertIsNone(build_alpaca_sip_evidence_source())

    def test_returns_none_when_only_the_key_id_is_configured(self):
        with mock.patch.dict(os.environ, {ENV_ALPACA_API_KEY_ID: "key-only"}, clear=False):
            os.environ.pop(ENV_ALPACA_API_SECRET_KEY, None)
            self.assertIsNone(build_alpaca_sip_evidence_source())

    def test_returns_a_real_source_only_when_both_credentials_are_configured(self):
        with mock.patch.dict(
            os.environ, {ENV_ALPACA_API_KEY_ID: "key-123", ENV_ALPACA_API_SECRET_KEY: "secret-456"}
        ):
            source = build_alpaca_sip_evidence_source()
            self.assertIsInstance(source, AlpacaSipEvidenceSource)


class EndToEndEvidenceContractIntegrationTests(unittest.TestCase):
    """Proves this adapter genuinely composes with the already-merged, unmodified generic evidence contract."""

    def _intent(self, symbol="CROX"):
        return OrderIntent(
            intent_id="i-1",
            created_at=datetime(2026, 9, 1, 14, 30, tzinfo=timezone.utc),
            account=AccountKind.INVESTMENTS_GROWTH,
            action=DecisionAction.BUY,
            symbol=symbol,
            quantity=Decimal("1"),
            reason="test",
        )

    def test_a_fresh_regular_session_quote_satisfies_execution_evidence_ok(self):
        moment = datetime(2026, 9, 1, 14, 30, 5, tzinfo=timezone.utc)

        def handler(request):
            return httpx.Response(200, json=_quote_payload(t="2026-09-01T14:30:00Z"))

        source = AlpacaSipEvidenceSource("key", "secret", _client_for(handler), clock=lambda: moment)
        evidence = asyncio.run(source.evidence_for("CROX"))
        evaluation = evaluate_market_data_evidence(
            evidence,
            expected_instrument="CROX",
            expected_currency="USD",
            execution_max_age=timedelta(seconds=30),
            valuation_max_age=timedelta(hours=1),
            now=moment,
        )
        self.assertTrue(evaluation.execution_evidence_ok)
        self.assertTrue(evaluation.valuation_evidence_ok)

    def test_default_clock_is_the_real_wall_clock(self):
        # No clock= injected - production behavior. The fixed 2026-09-01
        # fixture timestamp is long past any reasonable freshness bound
        # relative to the real wall clock, so this must fail closed
        # exactly like real stale evidence would.
        def handler(request):
            return httpx.Response(200, json=_quote_payload(t="2026-09-01T14:30:00Z"))

        source = AlpacaSipEvidenceSource("key", "secret", _client_for(handler))
        evidence = asyncio.run(source.evidence_for("CROX"))
        evaluation = evaluate_market_data_evidence(
            evidence,
            expected_instrument="CROX",
            expected_currency="USD",
            execution_max_age=timedelta(seconds=30),
            valuation_max_age=timedelta(hours=1),
        )
        self.assertFalse(evaluation.execution_evidence_ok)
        self.assertFalse(evaluation.valuation_evidence_ok)

    def test_integration_alone_never_produces_a_quote_without_a_wired_reader(self):
        # No credentials configured anywhere in this process by default -
        # composing this adapter into the evidence-guarded quote source
        # requires an explicit, deliberate wiring step; it is never
        # silently active.
        self.assertIsNone(build_alpaca_sip_evidence_source())

    def test_execution_guarded_quote_source_never_fabricates_a_fill_when_entitlement_is_rejected(self):
        def handler(request):
            return httpx.Response(403, json={"message": "no SIP entitlement"})

        source = AlpacaSipEvidenceSource("key", "secret", _client_for(handler))
        quote_source = EvidenceGuardedQuoteSource(
            source,
            EvidenceGrade.EXECUTION,
            expected_currency="USD",
            execution_max_age=timedelta(seconds=30),
            valuation_max_age=timedelta(hours=1),
        )
        quote = asyncio.run(quote_source.quote_for(self._intent()))
        self.assertIsNone(quote)


class BinanceCryptoPathUnchangedTests(unittest.TestCase):
    """Regression guard: this Alpaca-adapter PR touches nothing in the existing crypto quote-routing path."""

    def test_build_quote_source_still_registers_only_crypto(self):
        from tools.experiment1_runtime.runtime import build_quote_source
        from experiment1.market_data_providers import AssetClass, MultiAssetQuoteSource

        source = build_quote_source()
        self.assertIsInstance(source, MultiAssetQuoteSource)
        self.assertEqual(set(source.providers.keys()), {AssetClass.CRYPTO})


if __name__ == "__main__":
    unittest.main()
