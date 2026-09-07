from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable


class SECEvidenceError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class SECFundamentalsEvidence:
    cik: str
    entity_name: str
    observed_at: datetime
    source_reference: str
    facts: dict[str, object]

    def as_source(self) -> dict[str, object]:
        return {
            "reference": self.source_reference,
            "authority": "SEC",
            "observed_at": self.observed_at.isoformat(),
            "content": {
                "cik": self.cik,
                "entity_name": self.entity_name,
                "facts": self.facts,
            },
        }


class SECCompanyFactsProvider:
    """Read-only primary-source fundamentals evidence from SEC companyfacts."""

    BASE_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

    def __init__(
        self,
        *,
        user_agent: str,
        fetch_text: Callable[[str], str] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not user_agent.strip():
            raise ValueError("SEC user_agent is required")
        self._user_agent = user_agent.strip()
        self._fetch_text = fetch_text or self._http_get_text
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def fetch(self, cik: str) -> SECFundamentalsEvidence:
        digits = "".join(ch for ch in str(cik) if ch.isdigit()).zfill(10)
        if len(digits) != 10:
            raise SECEvidenceError("invalid CIK")
        url = self.BASE_URL.format(cik=digits)
        try:
            payload = json.loads(self._fetch_text(url))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise SECEvidenceError("SEC companyfacts unavailable") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("facts"), dict):
            raise SECEvidenceError("malformed SEC companyfacts")
        name = str(payload.get("entityName") or "").strip()
        if not name:
            raise SECEvidenceError("SEC companyfacts missing entity name")
        return SECFundamentalsEvidence(
            cik=digits,
            entity_name=name,
            observed_at=self._clock(),
            source_reference=f"sec:companyfacts:CIK{digits}",
            facts=payload["facts"],
        )

    def _http_get_text(self, url: str) -> str:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": self._user_agent,
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=20) as response:
            return response.read().decode("utf-8")
