from models.signal import Signal
from telegram.entry_readiness import assess_alert
from telegram.message_builder import MessageBuilder


def signal(metadata=None):
    return Signal(
        symbol="ENAUSDT", market="futures", timeframe="1h",
        strategy="OrderBlock", direction="LONG", score=90,
        reasons=["Price inside Bullish Order Block"], metadata=metadata or {},
    )


def test_score_alone_is_not_entry_ready():
    status, reason = assess_alert(signal())
    assert status == "NO_TRADE"
    assert "unavailable" in reason
    message = MessageBuilder().build(signal())
    assert "NO_TRADE" in message
    assert "НЕ BUY" in message


def test_valid_geometry_without_confirmations_is_watch():
    s = signal({"risk": {"entry": 0.20, "stop_loss": 0.19,
                          "take_profit": 0.23, "risk_reward": 3.0}})
    assert assess_alert(s)[0] == "WATCH"


def test_failed_reaction_is_no_trade():
    s = signal({"risk": {"entry": 0.20, "stop_loss": 0.19,
                          "take_profit": 0.23, "risk_reward": 3.0},
                "risk_geometry_valid": True, "target_clear": True,
                "reaction_confirmed": False})
    assert assess_alert(s)[0] == "NO_TRADE"


def test_verified_research_without_live_execution_evidence_is_watch():
    s = signal({"risk": {"entry": 0.20, "stop_loss": 0.19,
                          "take_profit": 0.23, "risk_reward": 3.0},
                "risk_geometry_valid": True, "target_clear": True,
                "reaction_confirmed": True, "research_trade_id": "research-1"})
    assert assess_alert(s)[0] == "WATCH"


def test_entry_ready_requires_explicit_evidence():
    s = signal({"risk": {"entry": 0.20, "stop_loss": 0.19,
                          "take_profit": 0.23, "risk_reward": 3.0},
                "risk_geometry_valid": True, "target_clear": True,
                "reaction_confirmed": True, "research_trade_id": "research-1",
                "market_data_fresh": True, "execution_liquidity_verified": True})
    assert assess_alert(s)[0] == "ENTRY_READY"


def test_bad_rr_is_no_trade_even_with_flags():
    s = signal({"risk": {"entry": 0.20, "stop_loss": 0.19,
                          "take_profit": 0.23, "risk_reward": 9.0},
                "risk_geometry_valid": True, "target_clear": True,
                "reaction_confirmed": True, "research_trade_id": "research-1",
                "market_data_fresh": True, "execution_liquidity_verified": True})
    assert assess_alert(s)[0] == "NO_TRADE"
