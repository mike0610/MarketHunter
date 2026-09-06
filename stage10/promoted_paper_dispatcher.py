from __future__ import annotations
import sqlite3
from dataclasses import dataclass
from datetime import datetime,timezone
from decimal import Decimal
from pathlib import Path

from experiment1.engine import Experiment1Engine
from experiment1.models import AccountKind,DecisionAction,ExecutionTrigger,TriggerType
from experiment1.trading_decision import TradingDecision,decision_to_json
from research.autonomous_loop.models import ResearchTrack
from research.autonomous_loop.repository import AutonomousResearchRepository
from risk_mm.models import RiskPolicy,TradingAccount
from risk_mm.open_risk_ledger import OpenRiskLedger
from risk_mm.store import RiskPlanStore
from stage10.promoted_paper_bridge import PaperAdmissionError,build_promoted_paper_binding,load_paper_admission
from strategy_engine.store import StrategyDecisionStore
from trading_scanner.models import QueueState
from trading_scanner.store import TradingScannerStore

@dataclass(frozen=True,slots=True)
class DispatchResult:
    object_id:str
    candidate_dedupe_key:str
    decision_id:str|None
    status:str
    detail:str|None=None

class PromotedPaperDispatchStore:
    def __init__(self,path:str|Path):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        with sqlite3.connect(self.path) as c:
            c.execute("""CREATE TABLE IF NOT EXISTS promoted_paper_dispatches(
              object_id TEXT NOT NULL,candidate_dedupe_key TEXT NOT NULL,
              decision_id TEXT NOT NULL,strategy_id TEXT NOT NULL,strategy_version TEXT NOT NULL,
              hypothesis_id TEXT NOT NULL,created_at TEXT NOT NULL,
              research_track TEXT,strategy_decision_id TEXT,risk_plan_id TEXT,risk_amount TEXT,
              PRIMARY KEY(object_id,candidate_dedupe_key),UNIQUE(decision_id))""")
            columns={row[1] for row in c.execute("PRAGMA table_info(promoted_paper_dispatches)")}
            for name in ("research_track","strategy_decision_id","risk_plan_id","risk_amount"):
                if name not in columns:
                    c.execute(f"ALTER TABLE promoted_paper_dispatches ADD COLUMN {name} TEXT")
    def exists(self,object_id:str,dedupe:str)->bool:
        with sqlite3.connect(self.path) as c:
            return c.execute("select 1 from promoted_paper_dispatches where object_id=? and candidate_dedupe_key=?",(object_id,dedupe)).fetchone() is not None
    def record(self,*,object_id,dedupe,decision_id,strategy_id,version,hypothesis_id,
               research_track=None,strategy_decision_id=None,risk_plan_id=None,risk_amount=None)->None:
        with sqlite3.connect(self.path) as c:
            c.execute("""INSERT OR IGNORE INTO promoted_paper_dispatches
              (object_id,candidate_dedupe_key,decision_id,strategy_id,strategy_version,hypothesis_id,created_at,
               research_track,strategy_decision_id,risk_plan_id,risk_amount)
              VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
              (object_id,dedupe,decision_id,strategy_id,version,hypothesis_id,datetime.now(timezone.utc).isoformat(),
               research_track,strategy_decision_id,risk_plan_id,None if risk_amount is None else str(risk_amount)))
    def list_rows(self):
        with sqlite3.connect(self.path) as c:
            c.row_factory=sqlite3.Row
            return tuple(c.execute("SELECT * FROM promoted_paper_dispatches ORDER BY created_at,decision_id").fetchall())

def _account(kind:TradingAccount)->AccountKind:
    return AccountKind.SPOT if kind is TradingAccount.SPOT else AccountKind.FUTURES

def _action(account:TradingAccount,direction:str)->DecisionAction:
    if account is TradingAccount.SPOT:
        if direction!="LONG": raise PaperAdmissionError("SPOT paper runtime does not support short exposure")
        return DecisionAction.BUY
    return DecisionAction.LONG if direction=="LONG" else DecisionAction.SHORT

def _take_profit(trigger:Decimal,stop:Decimal|None,direction:str,r_multiple:Decimal|None)->Decimal|None:
    if r_multiple is None:return None
    if stop is None: raise PaperAdmissionError("R-multiple take profit requires structural stop")
    if r_multiple<=0: raise PaperAdmissionError("take_profit_r must be positive")
    risk=trigger-stop if direction=="LONG" else stop-trigger
    if risk<=0: raise PaperAdmissionError("invalid trigger/stop geometry")
    target=trigger+r_multiple*risk if direction=="LONG" else trigger-r_multiple*risk
    if target<=0: raise PaperAdmissionError("computed take profit is not positive")
    return target

def dispatch_promoted_candidates(
    *,
    research_repo:AutonomousResearchRepository,
    scanner_store:TradingScannerStore,
    engine:Experiment1Engine,
    dispatch_store:PromotedPaperDispatchStore,
    strategy_store:StrategyDecisionStore,
    risk_store:RiskPlanStore,
    open_risk_ledger:OpenRiskLedger,
    risk_policy:RiskPolicy,
    research_track:ResearchTrack|None=None,
    review_store=None,
)->tuple[DispatchResult,...]:
    out=[]
    candidates=scanner_store.list_candidates(queue_state=QueueState.CANDIDATE)
    for release in research_repo.release_candidates():
        oid=release["object_id"]
        release_track=ResearchTrack(release["research_track"])
        if research_track is not None and release_track is not research_track:
            continue
        try: admission=load_paper_admission(research_repo,oid)
        except PaperAdmissionError as exc:
            detail=str(exc)
            status="BLOCKED_STRATEGY_CONTRACT" if "no runtime-compatible paper_contract" in detail else "BLOCKED-PAPER-ADMISSION"
            out.append(DispatchResult(oid,"",None,status,detail));continue
        contract=admission.contract
        if admission.research_track is not release_track:
            out.append(DispatchResult(oid,"",None,"BLOCKED-PAPER-ADMISSION","release/admission research_track mismatch"));continue
        if review_store is not None and review_store.is_paused(oid,contract.strategy_id,contract.version):
            out.append(DispatchResult(oid,"",None,"PAUSED","paper review status=PAUSE"));continue
        evidence=__import__("json").loads(release["evidence_json"])
        pc=evidence.get("paper_contract") or {}
        r_multiple=None if pc.get("take_profit_r") is None else Decimal(str(pc["take_profit_r"]))
        for candidate in candidates:
            is_crypto = candidate.sec_type in ("CRYPTO","CRYPTO_SPOT","CRYPTO_FUTURES")
            if release_track is ResearchTrack.SL and (not is_crypto or not candidate.symbol.upper().endswith("USDT")):
                continue
            if release_track is ResearchTrack.GIL and is_crypto:
                continue
            if release_track is ResearchTrack.SL:
                if contract.account is TradingAccount.SPOT and candidate.sec_type not in ("CRYPTO","CRYPTO_SPOT"):
                    continue
                if contract.account is TradingAccount.FUTURES and candidate.sec_type not in ("CRYPTO","CRYPTO_FUTURES"):
                    continue
            if candidate.setup_family is not contract.setup_family or candidate.discovered_at<=admission.promoted_at:continue
            if dispatch_store.exists(oid,candidate.dedupe_key):continue
            try:
                built=build_promoted_paper_binding(
                    repo=research_repo,object_id=oid,candidate=candidate,
                    strategy_store=strategy_store,risk_store=risk_store,
                    account_state=engine.account_state(_account(contract.account)),
                    open_risk_ledger=open_risk_ledger,risk_policy=risk_policy)
            except Exception as exc:
                out.append(DispatchResult(oid,candidate.dedupe_key,None,"BLOCKED",str(exc)));continue
            plan=built.risk.risk_plan
            if built.binding is None or plan is None or plan.quantity is None:
                out.append(DispatchResult(oid,candidate.dedupe_key,None,"RISK-REJECTED",";".join(() if plan is None else plan.reasons)));continue
            trigger=built.binding.instruction.trigger_price
            if trigger is None:
                out.append(DispatchResult(oid,candidate.dedupe_key,None,"BLOCKED","conditional trigger missing"));continue
            decision_id=f"promoted-paper:{oid}:{candidate.dedupe_key}"
            trigger_type=TriggerType.PRICE_AT_OR_ABOVE if contract.direction.value=="LONG" else TriggerType.PRICE_AT_OR_BELOW
            decision=TradingDecision(
                decision_id=decision_id,decided_at=candidate.discovered_at,account=_account(contract.account),
                action=_action(contract.account,contract.direction.value),symbol=candidate.symbol,
                thesis=f"{release_track.value} PROMOTION-ELIGIBLE {contract.strategy_id}@{contract.version} object={oid} hypothesis={admission.hypothesis_id}",
                quantity=plan.quantity,leverage=contract.requested_leverage,
                stop_loss=plan.stop_price,
                take_profit=_take_profit(trigger,plan.stop_price,contract.direction.value,r_multiple),
                trigger=ExecutionTrigger(trigger_type=trigger_type,trigger_price=trigger,note="frozen promoted paper trigger"),
            )
            raw=decision_to_json(decision)
            engine.receive_trading_decision(decision_id,raw)
            dispatch_store.record(object_id=oid,dedupe=candidate.dedupe_key,decision_id=decision_id,
                                  strategy_id=contract.strategy_id,version=contract.version,hypothesis_id=admission.hypothesis_id,
                                  research_track=release_track.value,
                                  strategy_decision_id=built.risk.strategy_decision.decision_id,
                                  risk_plan_id=plan.plan_id,risk_amount=plan.risk_amount)
            out.append(DispatchResult(oid,candidate.dedupe_key,decision_id,"QUEUED"))
    return tuple(out)
