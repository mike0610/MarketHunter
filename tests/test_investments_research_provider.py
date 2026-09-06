from datetime import datetime, timezone

import httpx
import pytest

from investments.research_agent_contract import GILResearchRequest
from investments.research_provider import (
    GILResearchProviderError,
    LocalGILResearchProvider,
)


REQ = GILResearchRequest(
    candidate_id="obj-1",
    symbol="VWCE",
    evidence_reference="seed:fresh",
    priority="90",
    claimed_at=datetime(2026, 9, 7, tzinfo=timezone.utc),
)


def test_provider_has_no_evidence_fetch_authority():
    provider = LocalGILResearchProvider()
    with pytest.raises(GILResearchProviderError, match="requires sources"):
        provider.analyze(REQ, evidence_bundle={})


def test_provider_sends_bounded_evidence_and_parses_json(monkeypatch):
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {"message": {"content": '{"outcome":"BLOCKED_EVIDENCE"}'}}
                ]
            }

    def fake_post(url, *, json, timeout):
        captured["url"] = url
        captured["payload"] = json
        return Response()

    monkeypatch.setattr(httpx, "post", fake_post)
    provider = LocalGILResearchProvider()
    result = provider.analyze(
        REQ,
        evidence_bundle={
            "sources": [
                {
                    "reference": "primary:test",
                    "observed_at": "2026-09-07T00:00:00+00:00",
                    "content": "bounded evidence",
                }
            ]
        },
    )
    assert result == {"outcome": "BLOCKED_EVIDENCE"}
    assert captured["url"].endswith("/v1/chat/completions")
    prompt = captured["payload"]["messages"][1]["content"]
    assert "Use only the supplied evidence" in prompt
    assert "primary:test" in prompt
    assert captured["payload"]["temperature"] == 0


def test_malformed_local_model_response_fails_closed(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "not-json"}}]}

    monkeypatch.setattr(httpx, "post", lambda *a, **k: Response())
    with pytest.raises(GILResearchProviderError, match="malformed"):
        LocalGILResearchProvider().analyze(
            REQ,
            evidence_bundle={"sources": [{"reference": "primary:test"}]},
        )


def test_health_is_fail_closed(monkeypatch):
    def boom(*args, **kwargs):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(httpx, "get", boom)
    assert LocalGILResearchProvider().health() is False
