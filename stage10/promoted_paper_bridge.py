from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime,timedelta
from decimal import Decimal

from experiment1.models import AccountState
from research.autonomous_loop.models import ResearchTrack
from research.autonomous_loop.repository import AutonomousResearchRepository
from risk_mm.models import RiskPolicy,TradingAccount
from risk_mm.open_risk_ledger import OpenRiskLedger
from risk_mm.store import RiskPlanStore
from simulation.stage5_bridge import Stage5EntryInstruction,Stage5EntryMode,Stage5OrderBinding,build_order_binding
from stage10.candidate_risk_pipeline import CandidateRiskResult,process_candidate_to_risk
from strategies.registry_foundation import StrategyUsability,StrategyVersionAssessment
from strategy_engine.models import StrategyDecisionOutcome
from strategy_engine.store import StrategyDecisionStore
from trading_scanner.models import SetupFamily,TradingCandidate

class PaperAdmissionError(Exception): pass

@dataclass(frozen=True,slots=True)
class PaperStrategyContract:
    strategy_id:str
    version:str
    setup_family:SetupFamily
    direction:StrategyDecisionOutcome
    account:TradingAccount
    requested_leverage:Decimal
    cluster_key:str
    entry_trigger_source:str
    expiry_seconds:int|None

    def __post_init__(self):
        if self.direction not in (StrategyDecisionOutcome.LONG,StrategyDecisionOutcome.SHORT):
            raise ValueError("paper direction must be LONG or SHORT")
        if self.requested_leverage<=0: raise ValueError("requested_leverage must be positive")
        if self.account is TradingAccount.SPOT and self.requested_leverage!=Decimal("1"):
            raise ValueError("SPOT paper contract must use 1x")
        if self.account is TradingAccount.FUTURES and self.requested_leverage>Decimal("3"):
            raise ValueError("FUTURES paper contract exceeds 3x")
        expected="SIGNAL_BAR_HIGH" if self.direction is StrategyDecisionOutcome.LONG else "SIGNAL_BAR_LOW"
        if self.entry_trigger_source!=expected:
            raise ValueError(f"{self.direction.value} requires {expected}")
        if self.expiry_seconds is not None and self.expiry_seconds<=0:
            raise ValueError("expiry_seconds must be positive")

@dataclass(frozen=True,slots=True)
class PromotedPaperAdmission:
    object_id:str
    research_track:ResearchTrack
    hypothesis_id:str
    promoted_at:datetime
    contract:PaperStrategyContract

@dataclass(frozen=True,slots=True)
class PaperBindingResult:
    admission:PromotedPaperAdmission
    risk:CandidateRiskResult
    binding:Stage5OrderBinding|None

def _contract(raw:dict)->PaperStrategyContract:
    required=("strategy_id","version","setup_family","direction","account","requested_leverage","cluster_key","entry_trigger_source")
    missing=[k for k in required if k not in raw]
    if missing: raise PaperAdmissionError("paper_contract missing: "+",".join(missing))
    return PaperStrategyContract(
        strategy_id=str(raw["strategy_id"]),version=str(raw["version"]),
        setup_family=SetupFamily(raw["setup_family"]),direction=StrategyDecisionOutcome(raw["direction"]),
        account=TradingAccount(raw["account"]),requested_leverage=Decimal(str(raw["requested_leverage"])),
        cluster_key=str(raw["cluster_key"]),entry_trigger_source=str(raw["entry_trigger_source"]),
        expiry_seconds=None if raw.get("expiry_seconds") is None else int(raw["expiry_seconds"]),
    )

def load_paper_admission(repo:AutonomousResearchRepository,object_id:str)->PromotedPaperAdmission:
    row=repo.release_candidate(object_id)
    if row is None: raise PaperAdmissionError("object is not PROMOTION-ELIGIBLE")
    evidence=json.loads(row["evidence_json"])
    raw=evidence.get("paper_contract")
    if not isinstance(raw,dict): raise PaperAdmissionError("PROMOTION-ELIGIBLE evidence has no runtime-compatible paper_contract")
    return PromotedPaperAdmission(object_id,ResearchTrack(row["research_track"]),row["hypothesis_id"],datetime.fromisoformat(row["created_at"]),_contract(raw))

def build_promoted_paper_binding(
    *,
    repo:AutonomousResearchRepository,
    object_id:str,
    candidate:TradingCandidate,
    strategy_store:StrategyDecisionStore,
    risk_store:RiskPlanStore,
    account_state:AccountState,
    open_risk_ledger:OpenRiskLedger,
    risk_policy:RiskPolicy,
)->PaperBindingResult:
    admission=load_paper_admission(repo,object_id)
    c=admission.contract
    if candidate.discovered_at<=admission.promoted_at:
        raise PaperAdmissionError("paper simulation accepts forward candidates only after promotion")
    if candidate.setup_family is not c.setup_family:
        raise PaperAdmissionError("candidate setup family does not match promoted contract")
    trigger=candidate.signal_bar_high if c.direction is StrategyDecisionOutcome.LONG else candidate.signal_bar_low
    if trigger is None: raise PaperAdmissionError("candidate is missing frozen signal-bar trigger evidence")

    risk=process_candidate_to_risk(
        candidate=candidate,
        strategy_assessment=StrategyVersionAssessment(StrategyUsability.USABLE,()),
        strategy_store=strategy_store,risk_store=risk_store,account_state=account_state,
        open_risk_ledger=open_risk_ledger,account=c.account,cluster_key=c.cluster_key,
        requested_leverage=c.requested_leverage,risk_policy=risk_policy,
        strategy_id=c.strategy_id,strategy_version=c.version,approved_direction=c.direction,
        reference_price_override=trigger,
    )
    if risk.risk_plan is None or risk.risk_plan.decision.value!="APPROVED":
        return PaperBindingResult(admission,risk,None)

    expires_at=None if c.expiry_seconds is None else candidate.discovered_at+timedelta(seconds=c.expiry_seconds)
    mode=Stage5EntryMode.PRICE_AT_OR_ABOVE if c.direction is StrategyDecisionOutcome.LONG else Stage5EntryMode.PRICE_AT_OR_BELOW
    instruction=Stage5EntryInstruction(mode,trigger,risk.strategy_decision.structural_stop_price,expires_at)
    return PaperBindingResult(admission,risk,build_order_binding(risk.risk_plan,candidate,risk.strategy_decision,instruction))
