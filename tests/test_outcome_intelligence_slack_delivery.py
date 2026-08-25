"""
MarketHunter

Tests for Outcome Intelligence Slack delivery
(tools/outcome_intelligence/slack_delivery.py).
"""

from __future__ import annotations

import unittest

import httpx

from tools.outcome_intelligence.slack_delivery import (
    SlackDeliveryError,
    send_slack_report,
)


def _client_for(handler) -> httpx.Client:
    transport = httpx.MockTransport(handler)
    return httpx.Client(transport=transport)


class SendSlackReportTests(unittest.TestCase):
    def test_success_on_200(self) -> None:
        captured: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            captured["body"] = request.content
            return httpx.Response(200, content=b"ok")

        client = _client_for(handler)

        send_slack_report(
            webhook_url="https://hooks.slack.com/services/T/B/X",
            text="hello outcome intelligence",
            client=client,
        )

        self.assertEqual(captured["url"], "https://hooks.slack.com/services/T/B/X")
        self.assertIn(b"hello outcome intelligence", captured["body"])

    def test_success_on_other_2xx(self) -> None:
        client = _client_for(lambda request: httpx.Response(204))

        send_slack_report(
            webhook_url="https://hooks.slack.com/services/T/B/X",
            text="hello",
            client=client,
        )

    def test_non_2xx_raises(self) -> None:
        client = _client_for(
            lambda request: httpx.Response(500, text="internal_error")
        )

        with self.assertRaises(SlackDeliveryError):
            send_slack_report(
                webhook_url="https://hooks.slack.com/services/T/B/X",
                text="hello",
                client=client,
            )

    def test_404_raises(self) -> None:
        client = _client_for(
            lambda request: httpx.Response(404, text="invalid_payload")
        )

        with self.assertRaises(SlackDeliveryError):
            send_slack_report(
                webhook_url="https://hooks.slack.com/services/T/B/X",
                text="hello",
                client=client,
            )

    def test_transport_failure_raises(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        client = _client_for(handler)

        with self.assertRaises(SlackDeliveryError):
            send_slack_report(
                webhook_url="https://hooks.slack.com/services/T/B/X",
                text="hello",
                client=client,
            )

    def test_error_message_does_not_include_webhook_url(self) -> None:
        # The webhook URL itself is a secret - a delivery-failure error
        # message must not echo it back verbatim.
        webhook_url = "https://hooks.slack.com/services/SECRET/PATH/HERE"
        client = _client_for(lambda request: httpx.Response(500, text="err"))

        with self.assertRaises(SlackDeliveryError) as ctx:
            send_slack_report(webhook_url=webhook_url, text="hello", client=client)

        self.assertNotIn(webhook_url, str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
