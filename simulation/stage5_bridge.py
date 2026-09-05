from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from hashlib import sha256

from risk_mm.models import RiskDecision, SizedExecutionPlan
from simulation.foundation import (
    CandidateSnapshot,
    DispositionRecord,
    MarketObservationEvidence,
    SimulationCampaignReference,
    SimulationCandidateReference,
    SimulationDisposition,
    SimulationEvent,
    SimulationEventReference,
    SimulationEventType,
    SimulationMechanicsPolicyReference,
    SimulationPolicyReference,
    SimulationStrategyReference,
)
from simulation.runtime.contracts import (
    CandidateSourceRead,
    ForwardObservationRead,
    MechanicsEvaluation,
    MechanicsEvaluationStatus,
    RuntimeCandidateEnvelope,
    RuntimePlanKind,
    RuntimeSourceState,
    RuntimeTransitionPlan,
)
from strategy_engine.models import StrategyDecisionRecord
from time_semantics.foundation import (
    TemporalDisposition,
    TemporalFact,
    TemporalReference,
    TemporalRole,
)
from trading_scanner.models import TradingCandidate


class Stage5EntryMode(str, Enum):
    MARKET = "MARKET"
    PRICE_AT_OR_ABOVE = "PRICE_AT_OR_ABOVE"
    PRICE_AT_OR_BELOW = "PRICE_AT_OR_BELOW"


@dataclass(frozen=True, slots=True)
class Stage5MechanicsPolicy:
    policy_id: str
    version: str
    fee_bps: Decimal
    slippage_bps: Decimal
    max_volume_participation: Decimal = Decimal("0.01")
    allow_partial_fill: bool = True

    def __post_init__(self) -> None:
        if self.fee_bps < 0 or self.slippage_bps < 0:
            raise ValueError("fee/slippage bps must be non-negative")
        if self.max_volume_participation <= 0 or self.max_volume_participation > 1:
            raise ValueError("max_volume_participation must be in (0,1]")


@dataclass(frozen=True, slots=True)
class Stage5EntryInstruction:
    mode: Stage5EntryMode
    trigger_price: Decimal | None
    invalidation_price: Decimal | None
    expires_at: datetime | None

    def __post_init__(self) -> None:
        if self.mode is Stage5EntryMode.MARKET and self.trigger_price is not None:
            raise ValueError("MARKET must not carry trigger_price")
        if self.mode is not Stage5EntryMode.MARKET and (
            self.trigger_price is None or self.trigger_price <= 0
        ):
            raise ValueError("conditional entry requires positive trigger_price")
        if self.invalidation_price is not None and self.invalidation_price <= 0:
            raise ValueError("invalidation_price must be positive")
        if self.expires_at is not None and self.expires_at.tzinfo is None:
            raise ValueError("expires_at must be timezone-aware")


@dataclass(frozen=True, slots=True)
class Stage5MarketObservation:
    evidence: MarketObservationEvidence
    price: Decimal
    observed_volume: Decimal | None
    provider: str
    source_reference: str

    def __post_init__(self) -> None:
        if self.price <= 0:
            raise ValueError("price must be positive")
        if self.observed_volume is not None and self.observed_volume < 0:
            raise ValueError("observed_volume must be non-negative")


@dataclass(frozen=True, slots=True)
class Stage5FillDetails:
    fill_id: str
    order_id: str
    quantity: Decimal
    market_price: Decimal
    fill_price: Decimal
    fee_amount: Decimal
    slippage_amount: Decimal
    observed_at: datetime
    provider: str
    source_reference: str
    partial: bool
    unfilled_quantity: Decimal


@dataclass(frozen=True, slots=True)
class Stage5OrderBinding:
    order_id: str
    plan: SizedExecutionPlan
    candidate: TradingCandidate
    strategy_decision: StrategyDecisionRecord
    instruction: Stage5EntryInstruction


def build_order_binding(
    plan: SizedExecutionPlan,
    candidate: TradingCandidate,
    strategy_decision: StrategyDecisionRecord,
    instruction: Stage5EntryInstruction,
) -> Stage5OrderBinding:
    if plan.decision is not RiskDecision.APPROVED:
        raise ValueError("Stage 5 accepts APPROVED risk plans only")
    if plan.trading_decision_id != strategy_decision.decision_id:
        raise ValueError("risk plan / strategy decision mismatch")
    if strategy_decision.candidate_dedupe_key != candidate.dedupe_key:
        raise ValueError("strategy decision / candidate mismatch")
    if plan.quantity is None or plan.quantity <= 0:
        raise ValueError("approved plan requires positive quantity")
    raw=f"{plan.plan_id}|{strategy_decision.decision_id}|{candidate.dedupe_key}"
    return Stage5OrderBinding("sim-order:"+sha256(raw.encode()).hexdigest(),plan,candidate,strategy_decision,instruction)


def binding_to_envelope(
    binding: Stage5OrderBinding,
    *,
    campaign: SimulationCampaignReference,
    recorded_at: datetime,
) -> RuntimeCandidateEnvelope:
    if recorded_at.tzinfo is None:
        raise ValueError("recorded_at must be timezone-aware")
    c=binding.candidate; d=binding.strategy_decision; p=binding.plan
    candidate_ref=SimulationCandidateReference(
        "trading_scanner","TradingCandidate",c.dedupe_key,c.scan_cycle_id
    )
    detection_ref=TemporalReference("trading_candidate",c.dedupe_key,c.scan_cycle_id)
    snapshot=CandidateSnapshot(
        candidate=candidate_ref,
        strategy=SimulationStrategyReference(d.strategy_id,d.strategy_version),
        instrument=c.symbol,
        venue=c.exchange,
        market=p.account.value,
        timeframe="1d",
        direction=d.outcome.value,
        entry_trigger=binding.instruction.mode.value,
        entry=binding.instruction.trigger_price if binding.instruction.trigger_price is not None else p.reference_price,
        invalidation=binding.instruction.invalidation_price,
        targets=(),
        detection=TemporalFact(detection_ref,TemporalRole.OBSERVED_TIME,c.discovered_at,TemporalDisposition.KNOWN),
        policy_references=(
            SimulationPolicyReference("strategy_decision",d.decision_id,d.strategy_version),
            SimulationPolicyReference("risk_plan",p.plan_id,p.policy_version),
        ),
    )
    rec_ref=TemporalReference("stage5_admission",binding.order_id,p.policy_version)
    disposition=DispositionRecord(
        campaign=campaign,
        snapshot=snapshot,
        disposition=SimulationDisposition.ADMITTED_FOR_SIMULATION,
        reason_references=(),
        recorded_fact=TemporalFact(rec_ref,TemporalRole.RECORDED_TIME,recorded_at,TemporalDisposition.KNOWN),
    )
    return RuntimeCandidateEnvelope(campaign,snapshot,disposition)


class Stage5CandidateSource:
    def __init__(self, envelopes: tuple[RuntimeCandidateEnvelope,...]) -> None:
        self._envelopes=envelopes

    def read_candidates(self) -> CandidateSourceRead:
        return CandidateSourceRead(RuntimeSourceState.AVAILABLE,self._envelopes)


class Stage5ObservationSource:
    def __init__(
        self,
        observations: dict[str, Stage5MarketObservation],
        *,
        state: RuntimeSourceState = RuntimeSourceState.AVAILABLE,
    ) -> None:
        self._observations=observations
        self._state=state

    def read_observation(self,envelope:RuntimeCandidateEnvelope)->ForwardObservationRead:
        if self._state is not RuntimeSourceState.AVAILABLE:
            return ForwardObservationRead(self._state,None)
        obs=self._observations.get(envelope.snapshot.candidate.source_id)
        if obs is None:
            return ForwardObservationRead(RuntimeSourceState.UNAVAILABLE,None)
        return ForwardObservationRead(RuntimeSourceState.AVAILABLE,obs.evidence)


class Stage5MechanicsEvaluator:
    def __init__(
        self,
        bindings: dict[str, Stage5OrderBinding],
        observations: dict[str, Stage5MarketObservation],
        policy: Stage5MechanicsPolicy,
    ) -> None:
        self._bindings=bindings
        self._observations=observations
        self._policy=policy
        self._fill_details: dict[str,Stage5FillDetails]={}
        self._terminal_reason: dict[str,str]={}

    @property
    def mechanics_policy(self)->SimulationMechanicsPolicyReference:
        return SimulationMechanicsPolicyReference(self._policy.policy_id,self._policy.version)

    def fill_details_for(self,candidate_id:str)->Stage5FillDetails|None:
        return self._fill_details.get(candidate_id)

    def terminal_reason_for(self,candidate_id:str)->str|None:
        return self._terminal_reason.get(candidate_id)

    def _event(self,envelope,seq,event_type,observation,*,mechanics:bool):
        cref=envelope.snapshot.candidate
        ref=SimulationEventReference("stage5:"+cref.source_id,"attempt-1",seq)
        rec_ref=TemporalReference("stage5_event",f"{cref.source_id}:{seq}",self._policy.version)
        rec=TemporalFact(rec_ref,TemporalRole.RECORDED_TIME,observation.evidence.recorded_time.timestamp,TemporalDisposition.KNOWN)
        return SimulationEvent(
            reference=ref,campaign=envelope.campaign,candidate=cref,event_type=event_type,
            mechanics=self.mechanics_policy if mechanics else None,
            observation=observation.evidence if mechanics else None,recorded_fact=rec,
        )

    def _triggered(self,binding:Stage5OrderBinding,price:Decimal)->bool:
        ins=binding.instruction
        if ins.mode is Stage5EntryMode.MARKET: return True
        if ins.mode is Stage5EntryMode.PRICE_AT_OR_ABOVE: return price >= ins.trigger_price
        return price <= ins.trigger_price

    def _invalidated(self,binding:Stage5OrderBinding,price:Decimal)->bool:
        inv=binding.instruction.invalidation_price
        if inv is None: return False
        if binding.strategy_decision.outcome.value=="LONG": return price <= inv
        if binding.strategy_decision.outcome.value=="SHORT": return price >= inv
        return True

    def _make_fill(self,binding:Stage5OrderBinding,obs:Stage5MarketObservation)->Stage5FillDetails|None:
        requested=binding.plan.quantity
        if obs.observed_volume is None:
            return None
        capacity=obs.observed_volume*self._policy.max_volume_participation
        qty=min(requested,capacity)
        if qty <= 0 or (qty < requested and not self._policy.allow_partial_fill):
            return None
        sign=Decimal("1") if binding.strategy_decision.outcome.value=="LONG" else Decimal("-1")
        slip=obs.price*self._policy.slippage_bps/Decimal("10000")*sign
        fill_price=obs.price+slip
        slippage_amount=abs(fill_price-obs.price)*qty
        fee_amount=fill_price*qty*self._policy.fee_bps/Decimal("10000")
        fid="sim-fill:"+sha256(f"{binding.order_id}|{obs.source_reference}".encode()).hexdigest()
        return Stage5FillDetails(
            fid,binding.order_id,qty,obs.price,fill_price,fee_amount,slippage_amount,
            obs.evidence.observed_time.timestamp,obs.provider,obs.source_reference,
            qty<requested,requested-qty,
        )

    def evaluate(self,envelope,persisted_events,observation)->MechanicsEvaluation:
        cid=envelope.snapshot.candidate.source_id
        binding=self._bindings.get(cid); obs=self._observations.get(cid)
        if binding is None or obs is None or obs.evidence != observation:
            return MechanicsEvaluation(MechanicsEvaluationStatus.BLOCKED,None)
        final=persisted_events[-1].event_type if persisted_events else None
        if final in (SimulationEventType.ACTIVE,SimulationEventType.CENSORED,SimulationEventType.UNKNOWN,SimulationEventType.TERMINAL_OUTCOME):
            return MechanicsEvaluation(MechanicsEvaluationStatus.READY,RuntimeTransitionPlan(RuntimePlanKind.NO_CHANGE))

        ts=obs.evidence.observed_time.timestamp
        invalid=self._invalidated(binding,obs.price)
        expired=binding.instruction.expires_at is not None and ts > binding.instruction.expires_at
        triggered=self._triggered(binding,obs.price)

        start_seq=2 if final is SimulationEventType.WAITING_ENTRY else 1
        prefix=() if final is SimulationEventType.WAITING_ENTRY else (
            self._event(envelope,1,SimulationEventType.WAITING_ENTRY,obs,mechanics=False),
        )

        if invalid or expired:
            self._terminal_reason[cid]="INVALIDATED_BEFORE_FILL" if invalid else "EXPIRED_BEFORE_FILL"
            event=self._event(envelope,start_seq,SimulationEventType.CENSORED,obs,mechanics=False)
            return MechanicsEvaluation(MechanicsEvaluationStatus.READY,RuntimeTransitionPlan(RuntimePlanKind.EVENTS,prefix+(event,)))

        if not triggered:
            if prefix:
                return MechanicsEvaluation(MechanicsEvaluationStatus.READY,RuntimeTransitionPlan(RuntimePlanKind.EVENTS,prefix))
            return MechanicsEvaluation(MechanicsEvaluationStatus.READY,RuntimeTransitionPlan(RuntimePlanKind.NO_CHANGE))

        fill=self._make_fill(binding,obs)
        if fill is None:
            self._terminal_reason[cid]="INSUFFICIENT_LIQUIDITY_EVIDENCE"
            if prefix:
                return MechanicsEvaluation(MechanicsEvaluationStatus.READY,RuntimeTransitionPlan(RuntimePlanKind.EVENTS,prefix))
            return MechanicsEvaluation(MechanicsEvaluationStatus.READY,RuntimeTransitionPlan(RuntimePlanKind.NO_CHANGE))

        self._fill_details[cid]=fill
        fill_event=self._event(envelope,start_seq,SimulationEventType.SIMULATED_FILL,obs,mechanics=True)
        active_event=self._event(envelope,start_seq+1,SimulationEventType.ACTIVE,obs,mechanics=True)
        return MechanicsEvaluation(MechanicsEvaluationStatus.READY,RuntimeTransitionPlan(RuntimePlanKind.EVENTS,prefix+(fill_event,active_event)))
