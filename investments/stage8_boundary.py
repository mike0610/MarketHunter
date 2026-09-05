from __future__ import annotations
from experiment1.models import AccountKind,DecisionAction

INVESTMENT_ACCOUNTS=frozenset({
 AccountKind.INVESTMENTS_DEFENSIVE,
 AccountKind.INVESTMENTS_BALANCED,
 AccountKind.INVESTMENTS_GROWTH,
})
TRADING_ACCOUNTS=frozenset({AccountKind.SPOT,AccountKind.FUTURES})

def assert_investment_account(account:AccountKind)->None:
 if account not in INVESTMENT_ACCOUNTS:
  raise ValueError("Stage 8 investment flow cannot target Trading or legacy account")

def assert_investment_action(action:DecisionAction)->None:
 if action not in (DecisionAction.BUY,DecisionAction.SELL,DecisionAction.WAIT,DecisionAction.HOLD):
  raise ValueError("Stage 8 investment flow cannot emit LONG/SHORT")

def assert_not_trading_account(account:AccountKind)->None:
 if account in TRADING_ACCOUNTS:
  raise ValueError("Trading account is outside Stage 8 Investments boundary")
