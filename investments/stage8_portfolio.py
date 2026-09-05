from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from experiment1.engine import Experiment1Engine
from experiment1.models import DecisionAction,OrderIntent
from investments.stage8_boundary import assert_investment_account
from investments.stage8_decision_bridge import Stage8InvestmentDecision

@dataclass(frozen=True,slots=True)
class PortfolioGateResult:
 approved:bool
 reason:str
 intent:OrderIntent|None

def portfolio_gate(engine:Experiment1Engine,decision:Stage8InvestmentDecision,*,execution_price:Decimal,max_position_fraction:Decimal)->PortfolioGateResult:
 assert_investment_account(decision.account)
 if execution_price<=0:return PortfolioGateResult(False,"invalid execution price",None)
 if not Decimal("0")<max_position_fraction<=Decimal("1"):raise ValueError("max_position_fraction must be in (0,1]")
 if decision.action in (DecisionAction.WAIT,DecisionAction.HOLD):
  return PortfolioGateResult(False,decision.action.value,None)
 state=engine.account_state(decision.account)
 position=engine.position(decision.account,decision.symbol)
 held_notional=Decimal("0") if position is None else position.notional
 requested_notional=execution_price*decision.quantity
 if decision.action is DecisionAction.BUY:
  equity=state.last_equity
  if requested_notional>state.available_cash:return PortfolioGateResult(False,"insufficient investment cash",None)
  if equity>0 and held_notional+requested_notional>equity*max_position_fraction:
   return PortfolioGateResult(False,"investment concentration limit",None)
 intent=OrderIntent("stage8-investment:"+decision.decision_id,decision.decided_at,decision.account,decision.action,decision.symbol,decision.quantity,
  "Stage 8 investment decision "+decision.decision_id+"; "+decision.thesis)
 return PortfolioGateResult(True,"APPROVED",intent)
