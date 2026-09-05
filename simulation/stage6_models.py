from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

class ExitReason(str,Enum):
 STOP_LOSS="STOP_LOSS";TAKE_PROFIT="TAKE_PROFIT";PARTIAL_TAKE_PROFIT="PARTIAL_TAKE_PROFIT";STRUCTURAL_INVALIDATION="STRUCTURAL_INVALIDATION";TIME_EXIT="TIME_EXIT"

class ExitVerdict(str,Enum):
 HOLD="HOLD";EXIT="EXIT";BLOCKED="BLOCKED";AMBIGUOUS="AMBIGUOUS"

@dataclass(frozen=True,slots=True)
class PositionExitPolicy:
 strategy_id:str;strategy_version:str;stop_loss:Decimal|None;take_profit:Decimal|None
 partial_take_profit:Decimal|None=None;partial_fraction:Decimal|None=None
 structural_invalidation:Decimal|None=None;expires_at:datetime|None=None
 def __post_init__(self):
  for x in (self.stop_loss,self.take_profit,self.partial_take_profit,self.structural_invalidation):
   if x is not None and x<=0:raise ValueError("exit levels must be positive")
  if (self.partial_take_profit is None)!=(self.partial_fraction is None):raise ValueError("partial target and fraction must be paired")
  if self.partial_fraction is not None and not (Decimal("0")<self.partial_fraction<Decimal("1")):raise ValueError("partial_fraction must be in (0,1)")
  if self.expires_at is not None and self.expires_at.tzinfo is None:raise ValueError("expires_at must be timezone-aware")

@dataclass(frozen=True,slots=True)
class PositionBarEvidence:
 symbol:str;open:Decimal;high:Decimal;low:Decimal;close:Decimal;observed_at:datetime;provider:str;source_reference:str;fresh:bool=True
 def __post_init__(self):
  if self.observed_at.tzinfo is None:raise ValueError("observed_at must be timezone-aware")
  if min(self.open,self.high,self.low,self.close)<=0:raise ValueError("OHLC must be positive")
  if self.high<max(self.open,self.close,self.low) or self.low>min(self.open,self.close,self.high):raise ValueError("invalid OHLC")

@dataclass(frozen=True,slots=True)
class ManagedPosition:
 position_id:str;order_id:str;symbol:str;direction:str;quantity:Decimal;average_price:Decimal;entry_fees:Decimal;opened_at:datetime
 strategy_decision_id:str;candidate_dedupe_key:str;strategy_id:str;strategy_version:str
 def __post_init__(self):
  if self.direction not in ("LONG","SHORT"):raise ValueError("direction must be LONG/SHORT")
  if self.quantity<=0 or self.average_price<=0:raise ValueError("position quantity/price must be positive")

@dataclass(frozen=True,slots=True)
class ExitEvaluation:
 verdict:ExitVerdict;reason:ExitReason|None;raw_exit_price:Decimal|None;quantity:Decimal;detail:str

@dataclass(frozen=True,slots=True)
class SimulatedExitFill:
 exit_fill_id:str;position_id:str;reason:ExitReason;quantity:Decimal;reference_price:Decimal;fill_price:Decimal
 fee_amount:Decimal;slippage_amount:Decimal;observed_at:datetime;provider:str;source_reference:str

@dataclass(frozen=True,slots=True)
class ClosedTradeRecord:
 closed_trade_id:str;position_id:str;symbol:str;direction:str;entry_price:Decimal;exit_price:Decimal;quantity:Decimal
 gross_pnl:Decimal;entry_fees:Decimal;exit_fees:Decimal;realized_pnl:Decimal;opened_at:datetime;closed_at:datetime
 exit_reason:ExitReason;strategy_id:str;strategy_version:str;strategy_decision_id:str;candidate_dedupe_key:str
