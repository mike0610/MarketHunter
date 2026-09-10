import logging

from experiment1.engine import Experiment1Engine
from experiment1.slack_transport import SlackTransportError
from tools.experiment1_runtime import runtime


def test_trading_slack_history_error_is_fail_closed(monkeypatch, tmp_path, caplog):
    engine = Experiment1Engine(tmp_path / "experiment1.db")
    monkeypatch.setattr(runtime, "trading_transport_enabled_from_env", lambda: True)
    monkeypatch.setenv("TRADING_SLACK_BOT_TOKEN", "test-token")
    monkeypatch.setattr(runtime, "trading_config_from_env", lambda: object())

    class FailingClient:
        def __init__(self, token):
            pass

        def history(self, *, channel, limit=100, oldest=None):
            raise SlackTransportError("Slack history API rejected request: not_in_channel")

    import experiment1.slack_transport as slack_transport
    monkeypatch.setattr(slack_transport, "SlackWebApiHistoryClient", FailingClient)

    with caplog.at_level(logging.WARNING):
        runtime._poll_optional_trading_slack_transport(engine)

    assert "Trading Slack transport unavailable" in caplog.text
    assert "not_in_channel" in caplog.text
