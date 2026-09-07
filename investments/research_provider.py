from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

import httpx

from investments.research_agent_contract import GILResearchRequest


class GILResearchProviderError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class LocalGILResearchProvider:
    base_url: str = "http://127.0.0.1:8081"
    model: str = "qwen2.5-1.5b-q4"
    timeout_seconds: float = 120.0

    def health(self) -> bool:
        try:
            response = httpx.get(
                f"{self.base_url}/health",
                timeout=min(self.timeout_seconds, 5.0),
            )
            response.raise_for_status()
            return response.json().get("status") == "ok"
        except (httpx.HTTPError, ValueError):
            return False

    def analyze(
        self,
        request: GILResearchRequest,
        *,
        evidence_bundle: dict[str, Any],
    ) -> dict[str, Any]:
        """Reason over supplied evidence only.

        This provider deliberately has no web-fetch authority. Evidence
        acquisition remains a separate trusted step; the local model may
        summarize/judge supplied evidence but cannot invent sources.
        """
        if not evidence_bundle.get("sources"):
            raise GILResearchProviderError("evidence bundle requires sources")

        prompt = {
            "task": "GIL investment deep-research reasoning",
            "rules": [
                "Use only the supplied evidence.",
                "Never invent a source, price, filing, fact, or executability.",
                "If evidence is insufficient or ambiguous return BLOCKED_EVIDENCE.",
                "Historical CANDIDATE status is not BUY authority.",
                "WAIT requires revisit_condition.",
            ],
            "request": {
                "candidate_id": request.candidate_id,
                "symbol": request.symbol,
                "evidence_reference": request.evidence_reference,
                "priority": request.priority,
                "claimed_at": request.claimed_at.isoformat(),
            },
            "evidence_bundle": evidence_bundle,
            "output": "Return one JSON object only.",
        }
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are the bounded GIL investment research reasoner. "
                        "Evidence is authoritative; your prior knowledge is not."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(prompt, separators=(",", ":")),
                },
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        try:
            response = httpx.post(
                f"{self.base_url}/v1/chat/completions",
                json=payload,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            result = json.loads(content)
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise GILResearchProviderError(
                "local GIL research provider unavailable or malformed"
            ) from exc
        if not isinstance(result, dict):
            raise GILResearchProviderError("research provider result must be object")
        return result
