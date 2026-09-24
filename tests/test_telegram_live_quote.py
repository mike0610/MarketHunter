from datetime import datetime, timezone

from models.signal import Signal
from telegram.live_quote import observe_futures_quote
from telegram.entry_readiness import assess_alert
from telegram.message_builder import MessageBuilder


NOW = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)


def signal():
    return Signal(
        symbol="ENAUSDT", market="futures", timeframe="1h",
        strategy="OrderBlock", direction="LONG", score=90,
        metadata={
            "risk": {"entry": 0.20, "stop_loss": 0.19,
                     "take_profit": 0.23, "risk_reward": 3.0},
            "risk_geometry_valid": True, "target_clear": True,
            "reaction_confirmed": True, "research_trade_id": "test-trade",
        },
    )


def quote(**overrides):
    result = {
        "symbol": "ENAUSDT", "bidPrice": "0.1999", "askPrice": "0.2001",
        "bidQty": "100", "askQty": "100", "time": int(NOW.timestamp() * 1000),
    }
    result.update(overrides)
    return result


def test_fresh_quote_is_observation_not_executable_liquidity():
    s = signal()
    observe_futures_quote(s, now=NOW, fetch=lambda _: quote())
    assert s.metadata["market_data_fresh"] is True
    assert s.metadata["execution_liquidity_verified"] is False
    assert assess_alert(s)[0] == "WATCH"
    message = MessageBuilder().build(s)
    assert "Observed bid / ask" in message
    assert "liquidity limitation" in message.lower()


def test_stale_and_future_quote_fail_closed():
    for offset in (-11000, 1000):
        s = signal()
        observe_futures_quote(
            s, now=NOW,
            fetch=lambda _, offset=offset: quote(
                time=int(NOW.timestamp() * 1000) + offset,
            ),
        )
        assert s.metadata["market_data_fresh"] is False
        assert s.metadata["execution_liquidity_verified"] is False


def test_mismatch_and_invalid_book_fail_closed():
    for payload in (quote(symbol="BTCUSDT"), quote(bidPrice="0"),
                    quote(askPrice="0.19")):
        s = signal()
        observe_futures_quote(s, now=NOW, fetch=lambda _, p=payload: p)
        assert s.metadata["market_data_fresh"] is False


def test_failed_fetch_clears_previous_evidence():
    s = signal()
    observe_futures_quote(s, now=NOW, fetch=lambda _: quote())
    def offline(_):
        raise OSError("offline")
    observe_futures_quote(s, now=NOW, fetch=offline)
    assert s.metadata["market_data_fresh"] is False
    assert "live_quote" not in s.metadata
    assert assess_alert(s)[0] == "WATCH"
