"""
MarketHunter

Tests for exchange/bybit_client.py - a narrow, free, public, read-only
price connector (Bybit V5 linear kline data) for the Quiet-RV
cross-venue PRICE portability research object. All tests use an
injectable fake client double (mirroring
tests/test_experiment1_market_source.py's own established pattern) -
no live network call is ever made.
"""

from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timezone
from decimal import Decimal

from exchange.bybit_client import (
    BybitAPIError,
    BybitPerpetualCandle,
    BybitPerpetualCandleLoader,
    detect_gaps_and_duplicates,
)


class FakeClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    async def get(self, endpoint, params=None):
        self.calls.append((endpoint, params))
        return self.payload


def _row(ts_ms, o, h, l, c, v, turnover):
    return [str(ts_ms), str(o), str(h), str(l), str(c), str(v), str(turnover)]


def _ok_payload(rows, symbol="BTCUSDT", category="linear"):
    return {
        "retCode": 0,
        "retMsg": "OK",
        "result": {"symbol": symbol, "category": category, "list": rows},
        "time": 1672025956592,
    }


HOUR_MS = 60 * 60 * 1000
FOUR_HOURS_MS = 4 * HOUR_MS


class BybitPerpetualCandleFromRowTests(unittest.TestCase):
    def test_normalizes_a_raw_row_with_utc_timestamp_and_provenance(self):
        row = _row(1672027200000, "17071", "17073", "17027", "17055.5", "268611.9", "4571230.02566")
        candle = BybitPerpetualCandle.from_bybit_row("linear", "BTCUSDT", row)

        self.assertEqual(candle.venue, "BYBIT")
        self.assertEqual(candle.category, "linear")
        self.assertEqual(candle.symbol, "BTCUSDT")
        self.assertEqual(candle.open_time.tzinfo, timezone.utc)
        self.assertEqual(candle.open, Decimal("17071"))
        self.assertEqual(candle.close, Decimal("17055.5"))
        self.assertEqual(candle.volume, Decimal("268611.9"))
        self.assertEqual(candle.turnover, Decimal("4571230.02566"))


class DetectGapsAndDuplicatesTests(unittest.TestCase):
    def _candles(self, timestamps_ms):
        return [
            BybitPerpetualCandle.from_bybit_row("linear", "BTCUSDT", _row(ts, 1, 2, 0.5, 1.5, 10, 15))
            for ts in timestamps_ms
        ]

    def test_a_contiguous_series_is_clean(self):
        candles = self._candles([0, FOUR_HOURS_MS, 2 * FOUR_HOURS_MS, 3 * FOUR_HOURS_MS])
        report = detect_gaps_and_duplicates(candles, interval_minutes=240)
        self.assertTrue(report.is_clean)
        self.assertEqual(report.gaps, ())
        self.assertEqual(report.duplicate_open_times, ())

    def test_a_missing_candle_is_reported_as_a_gap_not_silently_dropped(self):
        # Missing the candle at 2*FOUR_HOURS_MS.
        candles = self._candles([0, FOUR_HOURS_MS, 3 * FOUR_HOURS_MS])
        report = detect_gaps_and_duplicates(candles, interval_minutes=240)
        self.assertFalse(report.is_clean)
        self.assertEqual(len(report.gaps), 1)
        gap_start, gap_end = report.gaps[0]
        self.assertEqual(gap_start, candles[1].open_time)
        self.assertEqual(gap_end, candles[2].open_time)

    def test_a_duplicate_open_time_is_reported_not_silently_deduplicated(self):
        candles = self._candles([0, FOUR_HOURS_MS, FOUR_HOURS_MS, 2 * FOUR_HOURS_MS])
        report = detect_gaps_and_duplicates(candles, interval_minutes=240)
        self.assertFalse(report.is_clean)
        self.assertEqual(len(report.duplicate_open_times), 1)
        self.assertEqual(report.duplicate_open_times[0], candles[1].open_time)

    def test_a_single_candle_batch_is_trivially_clean(self):
        report = detect_gaps_and_duplicates(self._candles([0]), interval_minutes=240)
        self.assertTrue(report.is_clean)

    def test_an_empty_batch_is_trivially_clean(self):
        report = detect_gaps_and_duplicates([], interval_minutes=240)
        self.assertTrue(report.is_clean)

    def test_rejects_a_non_positive_interval(self):
        with self.assertRaises(ValueError):
            detect_gaps_and_duplicates(self._candles([0]), interval_minutes=0)

    def test_raises_on_a_batch_that_is_not_sorted_ascending(self):
        candles = self._candles([FOUR_HOURS_MS, 0])
        with self.assertRaises(ValueError):
            detect_gaps_and_duplicates(candles, interval_minutes=240)


class BybitPerpetualCandleLoaderTests(unittest.TestCase):
    def test_fetches_and_normalizes_a_batch_of_candles(self):
        rows = [
            _row(2 * FOUR_HOURS_MS, 3, 3.1, 2.9, 3.05, 5, 15),
            _row(0, 1, 1.1, 0.9, 1.05, 5, 5),  # deliberately out of order in the raw response
            _row(FOUR_HOURS_MS, 2, 2.1, 1.9, 2.05, 5, 10),
        ]
        client = FakeClient(_ok_payload(rows))
        loader = BybitPerpetualCandleLoader(client)

        candles = asyncio.run(loader.get_perpetual_klines("BTCUSDT"))

        self.assertEqual(len(candles), 3)
        # Sorted ascending regardless of Bybit's own (newest-first) raw order.
        self.assertEqual([c.open_time.timestamp() * 1000 for c in candles], [0, FOUR_HOURS_MS, 2 * FOUR_HOURS_MS])

    def test_sends_the_expected_request_shape(self):
        client = FakeClient(_ok_payload([]))
        loader = BybitPerpetualCandleLoader(client)

        asyncio.run(loader.get_perpetual_klines("ETHUSDT", interval="240", limit=500))

        endpoint, params = client.calls[0]
        self.assertEqual(endpoint, "/v5/market/kline")
        self.assertEqual(params["category"], "linear")
        self.assertEqual(params["symbol"], "ETHUSDT")
        self.assertEqual(params["interval"], "240")
        self.assertEqual(params["limit"], 500)
        self.assertNotIn("start", params)
        self.assertNotIn("end", params)

    def test_includes_start_and_end_only_when_given(self):
        client = FakeClient(_ok_payload([]))
        loader = BybitPerpetualCandleLoader(client)

        asyncio.run(loader.get_perpetual_klines("BTCUSDT", start_ms=1000, end_ms=2000))

        _, params = client.calls[0]
        self.assertEqual(params["start"], 1000)
        self.assertEqual(params["end"], 2000)

    def test_a_non_zero_ret_code_raises_bybit_api_error_never_a_guessed_result(self):
        client = FakeClient({"retCode": 10001, "retMsg": "params error", "result": {}})
        loader = BybitPerpetualCandleLoader(client)

        with self.assertRaises(BybitAPIError):
            asyncio.run(loader.get_perpetual_klines("NOTREAL"))

    def test_an_empty_result_list_returns_an_empty_batch_not_an_error(self):
        client = FakeClient(_ok_payload([]))
        loader = BybitPerpetualCandleLoader(client)

        candles = asyncio.run(loader.get_perpetual_klines("BTCUSDT"))
        self.assertEqual(candles, [])

    def test_rejects_a_limit_above_the_documented_cap(self):
        loader = BybitPerpetualCandleLoader(FakeClient(_ok_payload([])))
        with self.assertRaises(ValueError):
            asyncio.run(loader.get_perpetual_klines("BTCUSDT", limit=1001))

    def test_rejects_a_non_positive_limit(self):
        loader = BybitPerpetualCandleLoader(FakeClient(_ok_payload([])))
        with self.assertRaises(ValueError):
            asyncio.run(loader.get_perpetual_klines("BTCUSDT", limit=0))

    def test_defaults_to_a_real_bybit_client_when_none_injected(self):
        from exchange.bybit_client import BybitClient

        loader = BybitPerpetualCandleLoader()
        self.assertIsInstance(loader.client, BybitClient)
        self.assertEqual(loader.client.base_url, "https://api.bybit.com")

    def test_end_to_end_batch_is_gap_and_duplicate_clean_when_fetched_from_a_contiguous_response(self):
        rows = [
            _row(0, 1, 1.1, 0.9, 1.05, 5, 5),
            _row(FOUR_HOURS_MS, 2, 2.1, 1.9, 2.05, 5, 10),
            _row(2 * FOUR_HOURS_MS, 3, 3.1, 2.9, 3.05, 5, 15),
        ]
        loader = BybitPerpetualCandleLoader(FakeClient(_ok_payload(rows)))
        candles = asyncio.run(loader.get_perpetual_klines("BTCUSDT", interval="240"))
        report = detect_gaps_and_duplicates(candles, interval_minutes=240)
        self.assertTrue(report.is_clean)


if __name__ == "__main__":
    unittest.main()
