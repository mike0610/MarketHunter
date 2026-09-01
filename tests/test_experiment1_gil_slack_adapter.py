"""
MarketHunter

Tests for experiment1/gil_slack_adapter.py - the final transport-origin
adapter that reads only #global-investment-lab for an explicit
"GIL DECISION ENVELOPE v1" marker block and forwards ONLY a validated
envelope into the existing durable GIL Decision Inbox
(Experiment1Engine.receive_gil_decision) - no second execution path.
"""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from experiment1.engine import Experiment1Engine
from experiment1.gil_decision import decision_to_json
from experiment1.gil_slack_adapter import (
    ENV_SLACK_BOT_TOKEN,
    SlackMessage,
    SlackWebApiChannelReader,
    build_gil_slack_reader,
    run_gil_slack_ingest_cycle,
)
from experiment1.models import AccountKind, DecisionAction, GilDecision, GilInboxStatus

CHANNEL_ID = "C0BNACTF4E4"
OTHER_CHANNEL_ID = "C0OTHERCHANNEL"
NOW = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)


def _envelope_text(decision: GilDecision, *, wrapper: str = "```json\n{body}\n```") -> str:
    body = decision_to_json(decision)
    return f"GIL DECISION ENVELOPE v1\n{wrapper.format(body=body)}"


def _decision(**overrides) -> GilDecision:
    data = dict(
        decision_id="gil-slack-001",
        decided_at=NOW,
        account=AccountKind.FUTURES,
        action=DecisionAction.LONG,
        symbol="BTCUSDT",
        thesis="breakout confirmed above resistance",
        quantity=Decimal("0.05"),
        leverage=Decimal("2"),
    )
    data.update(overrides)
    return GilDecision(**data)


def _msg(ts: str, text: str, *, channel_id: str = CHANNEL_ID, edited: bool = False) -> SlackMessage:
    return SlackMessage(ts=ts, text=text, channel_id=channel_id, edited=edited)


class FakeReader:
    def __init__(self, messages: tuple[SlackMessage, ...]):
        self._messages = messages
        self.calls: list[tuple[str, str | None]] = []

    async def fetch_new_messages(self, channel_id, after_ts):
        self.calls.append((channel_id, after_ts))
        return self._messages


class Experiment1GilSlackAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.engine = Experiment1Engine(Path(self.temp_dir.name) / "experiment1.db")

    def _run(self, messages, channel_id=CHANNEL_ID):
        reader = FakeReader(messages)
        results = asyncio.run(run_gil_slack_ingest_cycle(self.engine, reader, channel_id))
        return results, reader

    # --- strict marker/schema ------------------------------------------------

    def test_valid_envelope_is_forwarded_to_the_durable_inbox(self):
        decision = _decision()
        results, _ = self._run((_msg("100.001", _envelope_text(decision)),))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, "RECEIVED")
        self.assertEqual(results[0].decision_id, decision.decision_id)

        record = self.engine.gil_decision_inbox_status(decision.decision_id)
        self.assertIsNotNone(record)
        self.assertEqual(record.status, GilInboxStatus.PENDING_DRAIN)

    def test_envelope_forwarded_via_canonical_serialization_matches_http_path_payload(self):
        # decision_to_json is reused for the stored raw_payload, so a
        # decision delivered via Slack idempotency-compares identically
        # to the same decision delivered via POST /experiment1/gil-decisions.
        decision = _decision(decision_id="gil-slack-canon")
        self._run((_msg("100.001", _envelope_text(decision)),))

        # A second submission via the same canonical serialization (as
        # the HTTP endpoint would produce) is treated as identical, not
        # a conflict.
        record = self.engine.receive_gil_decision(decision.decision_id, decision_to_json(decision))
        self.assertEqual(record.status, GilInboxStatus.PENDING_DRAIN)

    def test_valid_range_and_max_notional_sizing_envelope_is_forwarded(self):
        from experiment1.models import ExecutionTrigger, SizingIntent, SizingMode, TriggerType

        decision = GilDecision(
            decision_id="gil-slack-croix",
            decided_at=NOW,
            account=AccountKind.INVESTMENTS_GROWTH,
            action=DecisionAction.BUY,
            symbol="CROXUSDT",
            thesis="first Growth tranche in the CROX buy zone",
            trigger=ExecutionTrigger(
                trigger_type=TriggerType.PRICE_IN_RANGE,
                trigger_price_low=Decimal("115"),
                trigger_price_high=Decimal("120"),
            ),
            sizing=SizingIntent(mode=SizingMode.MAX_NOTIONAL, max_notional=Decimal("500")),
        )
        results, _ = self._run((_msg("100.001", _envelope_text(decision)),))
        self.assertEqual(results[0].status, "RECEIVED")

    # --- ignore ordinary GIL prose -------------------------------------------

    def test_ordinary_prose_without_the_marker_is_ignored_not_parsed(self):
        text = (
            "GIL EVIDENCE PACKET\nID: GIL-FIRST-CAPITAL-RADAR-REFRESH-112\n"
            "STATUS: PROPOSED REFINED\n{\"decision_id\": \"looks-like-json-but-isnt-an-envelope\"}"
        )
        results, _ = self._run((_msg("100.001", text),))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, "IGNORED_NO_MARKER")
        self.assertIsNone(results[0].decision_id)
        self.assertIsNone(self.engine.gil_decision_inbox_status("looks-like-json-but-isnt-an-envelope"))

    def test_candidate_watch_research_state_prose_is_never_coerced_into_a_decision(self):
        text = "*CONTROL TOWER -> GIL | CANONICAL DECISION DELIVERY CONTRACT v1*\naction: CANDIDATE or WATCH text only"
        results, _ = self._run((_msg("100.001", text),))
        self.assertEqual(results[0].status, "IGNORED_NO_MARKER")

    # --- channel allowlist -----------------------------------------------------

    def test_a_message_reported_under_a_different_channel_id_is_never_processed(self):
        decision = _decision(decision_id="gil-slack-wrong-channel")
        results, _ = self._run(
            (_msg("100.001", _envelope_text(decision), channel_id=OTHER_CHANNEL_ID),),
            channel_id=CHANNEL_ID,
        )
        self.assertEqual(results, ())
        self.assertIsNone(self.engine.gil_decision_inbox_status(decision.decision_id))

    # --- malformed/research-state rejection -------------------------------------

    def test_marker_present_but_no_fenced_json_block_is_malformed_shape(self):
        results, _ = self._run((_msg("100.001", "GIL DECISION ENVELOPE v1\nno code block here at all"),))
        self.assertEqual(results[0].status, "MALFORMED_SHAPE")
        self.assertIsNone(results[0].decision_id)

    def test_unclosed_fence_is_malformed_shape_not_a_best_effort_parse(self):
        text = 'GIL DECISION ENVELOPE v1\n```json\n{"decision_id": "gil-unclosed"'
        results, _ = self._run((_msg("100.001", text),))
        self.assertEqual(results[0].status, "MALFORMED_SHAPE")
        self.assertIsNone(self.engine.gil_decision_inbox_status("gil-unclosed"))

    def test_invalid_json_inside_the_fence_is_malformed_and_never_persisted_without_a_decision_id(self):
        text = "GIL DECISION ENVELOPE v1\n```json\n{not valid json at all}\n```"
        results, _ = self._run((_msg("100.001", text),))
        self.assertEqual(results[0].status, "MALFORMED")
        self.assertIsNone(results[0].decision_id)

    def test_a_naive_decided_at_fails_domain_validation_and_is_persisted_malformed_with_decision_id(self):
        body = (
            '{"decision_id": "gil-slack-naive", "decided_at": "2026-09-01T12:00:00", '
            '"account": "FUTURES", "action": "LONG", "symbol": "BTCUSDT", '
            '"thesis": "t", "quantity": "1", "leverage": "1", "stop_loss": null, '
            '"take_profit": null, "execution_condition": null, "trigger": null, "sizing": null}'
        )
        text = f"GIL DECISION ENVELOPE v1\n```json\n{body}\n```"
        results, _ = self._run((_msg("100.001", text),))

        self.assertEqual(results[0].status, "MALFORMED")
        self.assertEqual(results[0].decision_id, "gil-slack-naive")

        record = self.engine.gil_decision_inbox_status("gil-slack-naive")
        self.assertIsNotNone(record)
        self.assertEqual(record.status, GilInboxStatus.MALFORMED)
        self.assertIn("timezone-aware", record.outcome_reason)

    def test_a_free_text_candidate_action_inside_a_marked_envelope_is_rejected_not_coerced(self):
        body = (
            '{"decision_id": "gil-slack-candidate", "decided_at": "2026-09-01T12:00:00+00:00", '
            '"account": "FUTURES", "action": "CANDIDATE", "symbol": "BTCUSDT", '
            '"thesis": "t", "quantity": "1", "leverage": "1", "stop_loss": null, '
            '"take_profit": null, "execution_condition": null, "trigger": null, "sizing": null}'
        )
        text = f"GIL DECISION ENVELOPE v1\n```json\n{body}\n```"
        results, _ = self._run((_msg("100.001", text),))
        self.assertEqual(results[0].status, "MALFORMED")

    # --- duplicate/replay --------------------------------------------------

    def test_the_same_message_delivered_twice_across_two_cycles_does_not_duplicate(self):
        decision = _decision(decision_id="gil-slack-replay")
        message = _msg("100.001", _envelope_text(decision))

        first, _ = self._run((message,))
        # Simulate a naive re-poll that (incorrectly) returns the same
        # message again despite the cursor - decision_id idempotency in
        # receive_gil_decision is the final guard.
        second, _ = self._run((message,))

        self.assertEqual(first[0].status, "RECEIVED")
        self.assertEqual(second[0].status, "RECEIVED")

        record = self.engine.gil_decision_inbox_status(decision.decision_id)
        self.assertEqual(record.status, GilInboxStatus.PENDING_DRAIN)

    # --- restart/cursor ------------------------------------------------------

    def test_cursor_advances_past_every_message_handled_this_pass(self):
        decision = _decision(decision_id="gil-slack-cursor")
        self._run((_msg("100.001", _envelope_text(decision)),))
        self.assertEqual(self.engine.get_slack_ingest_cursor(CHANNEL_ID), "100.001")

    def test_a_restart_reads_only_strictly_after_the_persisted_cursor(self):
        decision = _decision(decision_id="gil-slack-cursor-2")
        self._run((_msg("100.001", _envelope_text(decision)),))

        # A fresh reader/cycle (simulating a process restart) must be
        # asked for messages after the persisted cursor, not from the
        # beginning again.
        reader = FakeReader(())
        asyncio.run(run_gil_slack_ingest_cycle(self.engine, reader, CHANNEL_ID))
        self.assertEqual(reader.calls, [(CHANNEL_ID, "100.001")])

    def test_a_fresh_engine_instance_over_the_same_db_resumes_from_the_persisted_cursor(self):
        decision = _decision(decision_id="gil-slack-cursor-restart")
        self._run((_msg("100.001", _envelope_text(decision)),))

        second_engine = Experiment1Engine(self.engine.db_path)
        self.assertEqual(second_engine.get_slack_ingest_cursor(CHANNEL_ID), "100.001")

    # --- edit-ambiguity fail-closed -------------------------------------------

    def test_an_edited_message_is_never_processed(self):
        decision = _decision(decision_id="gil-slack-edited")
        results, _ = self._run((_msg("100.001", _envelope_text(decision), edited=True),))

        self.assertEqual(results[0].status, "EDITED_AMBIGUOUS")
        self.assertIsNone(self.engine.gil_decision_inbox_status(decision.decision_id))
        # Cursor still advances - GIL must post a fresh envelope under a
        # new decision_id rather than relying on the edit being retried.
        self.assertEqual(self.engine.get_slack_ingest_cursor(CHANNEL_ID), "100.001")

    # --- forwarding to existing inbox / no second execution path -------------

    def test_forwarding_uses_the_exact_same_engine_method_the_http_endpoint_uses(self):
        decision = _decision(decision_id="gil-slack-single-path")
        self._run((_msg("100.001", _envelope_text(decision)),))

        # No OrderIntent/fill exists yet - only the existing, unmodified
        # drain_gil_decision_inbox cycle (already wired into
        # tools/experiment1_runtime/runtime.py) ever creates one.
        state_positions = self.engine.positions(AccountKind.FUTURES)
        self.assertEqual(state_positions, ())

    # --- WAIT/HOLD never create an executable order ---------------------------

    def test_a_wait_decision_is_received_but_creates_no_position_once_drained(self):
        decision = _decision(decision_id="gil-slack-wait", action=DecisionAction.WAIT, quantity=Decimal("0"))
        results, _ = self._run((_msg("100.001", _envelope_text(decision)),))
        self.assertEqual(results[0].status, "RECEIVED")

        from experiment1.gil_decision import drain_gil_decision_inbox

        class NeverCalledQuoteSource:
            async def quote_for(self, intent):
                raise AssertionError("WAIT/immediate/exact-quantity decisions must never fetch a quote")

        drain_results = asyncio.run(drain_gil_decision_inbox(self.engine, NeverCalledQuoteSource()))
        self.assertEqual(drain_results[0].outcome, "NO_ACTION")
        self.assertEqual(self.engine.positions(AccountKind.FUTURES), ())

    # --- multiple messages processed in one pass, ordering preserved ---------

    def test_multiple_messages_in_one_pass_are_each_handled_and_cursor_ends_at_the_latest(self):
        d1 = _decision(decision_id="gil-slack-multi-1")
        d2 = _decision(decision_id="gil-slack-multi-2")
        results, _ = self._run(
            (
                _msg("100.001", "just ordinary GIL research prose, no marker"),
                _msg("100.002", _envelope_text(d1)),
                _msg("100.003", _envelope_text(d2)),
            )
        )
        self.assertEqual([r.status for r in results], ["IGNORED_NO_MARKER", "RECEIVED", "RECEIVED"])
        self.assertEqual(self.engine.get_slack_ingest_cursor(CHANNEL_ID), "100.003")


class SlackWebApiChannelReaderTests(unittest.TestCase):
    """
    The real, network-calling reader implementation - tested against a
    fake httpx transport, never a live Slack connection.
    """

    def test_rejects_a_blank_bot_token(self):
        import httpx

        with self.assertRaises(ValueError):
            SlackWebApiChannelReader("   ", httpx.AsyncClient())

    def test_filters_out_the_cursor_message_itself_and_sorts_oldest_first(self):
        import httpx

        payload = {
            "ok": True,
            "messages": [
                {"ts": "100.003", "text": "third"},
                {"ts": "100.001", "text": "cursor - already handled"},
                {"ts": "100.002", "text": "second", "edited": {"user": "U1", "ts": "100.0025"}},
            ],
        }

        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.params["oldest"], "100.001")
            self.assertEqual(request.headers["Authorization"], "Bearer xoxb-fake-token")
            return httpx.Response(200, json=payload)

        transport = httpx.MockTransport(handler)
        client = httpx.AsyncClient(transport=transport)
        reader = SlackWebApiChannelReader("xoxb-fake-token", client)

        messages = asyncio.run(reader.fetch_new_messages(CHANNEL_ID, after_ts="100.001"))

        self.assertEqual([m.ts for m in messages], ["100.002", "100.003"])
        self.assertTrue(messages[0].edited)
        self.assertFalse(messages[1].edited)

    def test_raises_on_a_slack_api_level_error(self):
        import httpx

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"ok": False, "error": "not_in_channel"})

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        reader = SlackWebApiChannelReader("xoxb-fake-token", client)

        with self.assertRaises(RuntimeError):
            asyncio.run(reader.fetch_new_messages(CHANNEL_ID, after_ts=None))


class BuildGilSlackReaderTests(unittest.TestCase):
    def test_returns_none_when_no_bot_token_is_configured(self):
        import os
        from unittest import mock

        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(ENV_SLACK_BOT_TOKEN, None)
            self.assertIsNone(build_gil_slack_reader())

    def test_returns_a_real_reader_only_when_a_bot_token_is_configured(self):
        import os
        from unittest import mock

        with mock.patch.dict(os.environ, {ENV_SLACK_BOT_TOKEN: "xoxb-real-token"}):
            reader = build_gil_slack_reader()
            self.assertIsInstance(reader, SlackWebApiChannelReader)


if __name__ == "__main__":
    unittest.main()
