from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable


class SECIdentityError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class SECInstrumentIdentity:
    symbol: str
    cik: str
    title: str
    observed_at: datetime
    source_reference: str


class SECCompanyTickerResolver:
    """Resolve US equity ticker -> CIK from the SEC's authoritative ticker map."""

    URL = "https://www.sec.gov/files/company_tickers.json"

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

    def resolve(self, symbol: str) -> SECInstrumentIdentity:
        wanted = symbol.strip().upper()
        if not wanted:
            raise SECIdentityError("symbol required")
        try:
            payload = json.loads(self._fetch_text(self.URL))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise SECIdentityError("SEC ticker map unavailable") from exc
        if not isinstance(payload, dict):
            raise SECIdentityError("malformed SEC ticker map")
        matches = []
        for row in payload.values():
            if not isinstance(row, dict):
                continue
            if str(row.get("ticker") or "").strip().upper() == wanted:
                matches.append(row)
        if len(matches) != 1:
            raise SECIdentityError(
                "SEC ticker identity unresolved" if not matches
                else "SEC ticker identity ambiguous"
            )
        row = matches[0]
        try:
            cik = str(int(row["cik_str"])).zfill(10)
        except (KeyError, TypeError, ValueError) as exc:
            raise SECIdentityError("SEC ticker identity missing CIK") from exc
        title = str(row.get("title") or "").strip()
        if not title:
            raise SECIdentityError("SEC ticker identity missing title")
        return SECInstrumentIdentity(
            symbol=wanted,
            cik=cik,
            title=title,
            observed_at=self._clock(),
            source_reference="sec:company_tickers",
        )

    def _http_get_text(self, url: str) -> str:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": self._user_agent, "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=20) as response:
            return response.read().decode("utf-8")
