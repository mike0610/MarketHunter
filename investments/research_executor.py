from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Any

from experiment1.models import AccountKind
from investments.autonomous_loop import (
    AutonomousInvestmentStore,
    InvestmentResearchDecision,
    InvestmentResearchRecord,
)
from investments.research_agent_contract import (
    GILResearchEvidence,
    GILResearchOutcome,
    GILResearchRequest,
    GILResearchResult,
    ingest_gil_research_result,
)
from investments.research_provider import LocalGILResearchProvider
from investments.research_worker import InvestmentResearchWorker
from investments.sec_evidence import SECCompanyFactsProvider
from investments.sec_identity import SECCompanyTickerResolver


class GILResearchExecutionError(RuntimeError):
    pass


@dataclass(slots=True)
class USInvestmentResearchExecutor:
    worker: InvestmentResearchWorker
    store: AutonomousInvestmentStore
    identity: SECCompanyTickerResolver
    fundamentals: SECCompanyFactsProvider
    reasoner: LocalGILResearchProvider
    max_evidence_age: timedelta = timedelta(days=7)

    def run_once(self) -> InvestmentResearchRecord | None:
        claim = self.worker.claim_next()
        if claim is None:
            return None
        request = GILResearchRequest.from_claim(claim)
        try:
            instrument = self.identity.resolve(claim.symbol)
            evidence = self.fundamentals.fetch(instrument.cik)
            source = evidence.as_source()
            raw = self.reasoner.analyze(request, evidence_bundle={"sources": [source]})
            result = self._parse(request, raw, source)
            return ingest_gil_research_result(
                worker=self.worker,
                store=self.store,
                claim=claim,
                result=result,
                max_evidence_age=self.max_evidence_age,
            )
        except Exception:
            # A claimed object must never turn an infrastructure/evidence failure
            # into an investment decision.
            self.worker.complete(claim.candidate_id, "BLOCKED_EVIDENCE")
            raise

    @staticmethod
    def _parse(
        request: GILResearchRequest,
        raw: dict[str, Any],
        source: dict[str, Any],
    ) -> GILResearchResult:
        observed_at = source["observed_at"]
        from datetime import datetime
        observed = datetime.fromisoformat(str(observed_at))
        evidence = (
            GILResearchEvidence(reference=str(source["reference"]), observed_at=observed),
        )
        completed = datetime.now(observed.tzinfo)
        outcome = str(raw.get("outcome") or "").upper()
        if outcome == GILResearchOutcome.BLOCKED_EVIDENCE.value:
            return GILResearchResult(
                candidate_id=request.candidate_id,
                symbol=request.symbol,
                outcome=GILResearchOutcome.BLOCKED_EVIDENCE,
                agent_reference="local-gil:qwen2.5-1.5b",
                completed_at=completed,
                evidence=evidence,
                blocker=str(raw.get("blocker") or "insufficient evidence"),
            )
        if outcome != GILResearchOutcome.DECISION.value:
            raise GILResearchExecutionError("unknown research outcome")
        try:
            decision = InvestmentResearchDecision(str(raw["decision"]).upper())
            account = AccountKind(str(raw["account"]).upper())
            attractiveness = Decimal(str(raw["investment_attractiveness"]))
            executability = Decimal(str(raw["executability"]))
        except (KeyError, ValueError) as exc:
            raise GILResearchExecutionError("malformed research decision") from exc
        return GILResearchResult(
            candidate_id=request.candidate_id,
            symbol=request.symbol,
            outcome=GILResearchOutcome.DECISION,
            agent_reference="local-gil:qwen2.5-1.5b",
            completed_at=completed,
            evidence=evidence,
            account=account,
            decision=decision,
            investment_attractiveness=attractiveness,
            executability=executability,
            thesis=str(raw.get("thesis") or "").strip() or None,
            counter_thesis=str(raw.get("counter_thesis") or "").strip() or None,
            revisit_condition=str(raw.get("revisit_condition") or "").strip() or None,
        )
