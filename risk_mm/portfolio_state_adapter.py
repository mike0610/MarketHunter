from __future__ import annotations

from decimal import Decimal

from experiment1.models import AccountKind, AccountState
from risk_mm.models import PortfolioRiskState, TradingAccount
from risk_mm.open_risk_ledger import OpenRiskLedger


def build_portfolio_risk_state(
    *,
    account_state: AccountState,
    open_risk_ledger: OpenRiskLedger,
    account: TradingAccount,
    cluster_key: str,
    requested_leverage: Decimal,
) -> PortfolioRiskState:
    """Adapt durable Experiment1 state plus durable open-risk exposure.

    Account selection, cluster classification and leverage are explicit caller
    inputs. This adapter only validates their consistency and never invents
    missing trading context.
    """
    if account_state.account not in (AccountKind.SPOT, AccountKind.FUTURES):
        raise ValueError("active-trading risk state requires SPOT or FUTURES account")
    if account_state.account.value != account.value:
        raise ValueError("explicit risk account does not match Experiment1 account state")
    if not isinstance(cluster_key, str) or not cluster_key.strip():
        raise ValueError("cluster_key must be explicit and non-blank")
    if requested_leverage is None or requested_leverage <= 0:
        raise ValueError("requested_leverage must be explicit and positive")

    aggregate_open_risk, cluster_open_risk = open_risk_ledger.aggregate(
        account, cluster_key
    )
    return PortfolioRiskState(
        account=account,
        equity=account_state.last_equity,
        available_cash=account_state.available_cash,
        aggregate_open_risk=aggregate_open_risk,
        cluster_open_risk=cluster_open_risk,
        cluster_key=cluster_key,
        requested_leverage=requested_leverage,
    )
