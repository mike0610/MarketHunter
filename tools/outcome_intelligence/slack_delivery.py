"""
MarketHunter

tools/outcome_intelligence/slack_delivery.py

Module:
Outcome Intelligence Slack delivery - a small, directly-testable
abstraction for posting a plain-text report to a Slack incoming
webhook. This module never reads the webhook URL itself (the caller
supplies it, sourced from environment/secret configuration in
tools/outcome_intelligence/runtime.py) and never logs the URL.

Fail-closed: any non-2xx response or transport failure raises
SlackDeliveryError. There is no retry/swallow-and-continue path -
callers must treat a raised error as a hard failure, never a
fabricated success.
"""

from __future__ import annotations

import httpx


class SlackDeliveryError(Exception):
    """Slack delivery failed - fail closed, never a silent no-op."""


def send_slack_report(webhook_url: str, text: str, client: httpx.Client) -> None:
    """
    POST `text` to a Slack incoming webhook as `{"text": text}`.

    Raises SlackDeliveryError on any transport failure or non-2xx
    response. Never mutates canonical MarketHunter state - this is a
    one-way, best-effort-but-verified notification only.
    """

    try:
        response = client.post(webhook_url, json={"text": text})
    except httpx.HTTPError as error:
        raise SlackDeliveryError(
            f"Slack webhook request failed: {error}"
        ) from error

    if not (200 <= response.status_code < 300):
        raise SlackDeliveryError(
            f"Slack webhook returned HTTP {response.status_code}: "
            f"{response.text[:500]!r}"
        )
