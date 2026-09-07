from datetime import datetime, timezone

import pytest

from investments.sec_evidence import SECCompanyFactsProvider, SECEvidenceError


NOW = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)


def test_sec_companyfacts_becomes_primary_source_bundle():
    raw = '{"cik":320193,"entityName":"Apple Inc.","facts":{"us-gaap":{"Assets":{"units":{"USD":[]}}}}}'
    provider = SECCompanyFactsProvider(
        user_agent="MarketHunter research contact@example.invalid",
        fetch_text=lambda url: raw,
        clock=lambda: NOW,
    )
    evidence = provider.fetch("320193")
    source = evidence.as_source()
    assert evidence.cik == "0000320193"
    assert source["authority"] == "SEC"
    assert source["reference"] == "sec:companyfacts:CIK0000320193"
    assert source["observed_at"] == NOW.isoformat()
    assert source["content"]["entity_name"] == "Apple Inc."


def test_sec_provider_fails_closed_on_missing_facts():
    provider = SECCompanyFactsProvider(
        user_agent="MarketHunter research contact@example.invalid",
        fetch_text=lambda url: '{"entityName":"Example"}',
    )
    with pytest.raises(SECEvidenceError, match="malformed"):
        provider.fetch("1")


def test_sec_provider_requires_identity_user_agent():
    with pytest.raises(ValueError, match="user_agent"):
        SECCompanyFactsProvider(user_agent="  ")
