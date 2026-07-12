"""
MarketHunter

Research Engine

Performance statistics for virtual trades.
"""

from __future__ import annotations

from research.models.trade import ResearchTrade
from research.models.trade_status import TradeStatus


class ResearchStatistics:
    """
    Calculates transparent performance metrics from virtual trades.

    "Clean" statistics (win_rate, total_profit, average_profit,
    average_rr, profit_factor, wins/losses/breakeven) ignore trades
    manually classified as outcome_group = excluded (universe cleanup,
    invalid legacy data). `completed` stays a raw CLOSED+EXPIRED count
    for transparency; `excluded` reports how many of those were
    removed from the clean numbers.
    """

    def calculate(
        self,
        trades: list[ResearchTrade],
    ) -> dict[str, float | int]:
        """
        Return summary statistics for all available trades.
        """

        completed = [
            trade
            for trade in trades
            if trade.status in {
                TradeStatus.CLOSED,
                TradeStatus.EXPIRED,
            }
        ]

        clean = [
            trade
            for trade in completed
            if not trade.is_excluded
        ]

        excluded_count = len(completed) - len(clean)

        wins = [
            trade
            for trade in clean
            if trade.profit_percent > 0
        ]

        losses = [
            trade
            for trade in clean
            if trade.profit_percent < 0
        ]

        breakeven = [
            trade
            for trade in clean
            if trade.profit_percent == 0
        ]

        profitable_expired = [
            trade
            for trade in clean
            if trade.is_profitable_expired
        ]

        expired_at_loss = [
            trade
            for trade in clean
            if trade.status == TradeStatus.EXPIRED
            and trade.profit_percent < 0
        ]

        gross_profit = sum(
            trade.profit_amount
            for trade in wins
        )

        gross_loss = abs(
            sum(
                trade.profit_amount
                for trade in losses
            )
        )

        decisive_trades = len(wins) + len(losses)

        return {
            "total": len(trades),
            "waiting_entry": sum(
                1
                for trade in trades
                if trade.status == TradeStatus.WAITING_ENTRY
            ),
            "active": sum(
                1
                for trade in trades
                if trade.status == TradeStatus.ACTIVE
            ),
            "completed": len(completed),
            "clean_completed": len(clean),
            "excluded": excluded_count,
            "wins": len(wins),
            "losses": len(losses),
            "breakeven": len(breakeven),
            "profitable_expired": len(profitable_expired),
            "profitable_expired_profit": sum(
                trade.profit_amount
                for trade in profitable_expired
            ),
            "expired_at_loss": len(expired_at_loss),
            "win_rate": (
                len(wins)
                / decisive_trades
                * 100
                if decisive_trades > 0
                else 0.0
            ),
            "total_profit": sum(
                trade.profit_amount
                for trade in clean
            ),
            "average_profit": (
                sum(
                    trade.profit_percent
                    for trade in clean
                )
                / len(clean)
                if clean
                else 0.0
            ),
            "average_rr": (
                sum(
                    trade.rr
                    for trade in clean
                )
                / len(clean)
                if clean
                else 0.0
            ),
            "profit_factor": (
                gross_profit
                / gross_loss
                if gross_loss > 0
                else 0.0
            ),
        }

    def calculate_setup_reasons(
        self,
        trades: list[ResearchTrade],
    ) -> dict[str, object]:
        """
        Return performance grouped by strategy, setup reason and close reason.
        """

        return {
            "by_strategy": self._group_trades(
                trades=trades,
                key_func=lambda trade: trade.strategy,
            ),
            "by_setup_reason": self._group_trades(
                trades=trades,
                key_func=self._setup_reason_key,
            ),
            "by_close_reason": self._group_trades(
                trades=[
                    trade
                    for trade in trades
                    if trade.close_reason
                ],
                key_func=lambda trade: self._close_reason_key(
                    trade.close_reason,
                ),
            ),
            "by_status": self._group_trades(
                trades=trades,
                key_func=lambda trade: trade.status.value,
            ),
            "by_outcome": self._group_trades(
                trades=trades,
                key_func=lambda trade: trade.outcome_type,
            ),
            "by_outcome_group": self._group_trades(
                trades=trades,
                key_func=lambda trade: trade.outcome_group,
            ),
        }

    def _group_trades(
        self,
        *,
        trades: list[ResearchTrade],
        key_func,
    ) -> list[dict[str, object]]:
        groups: dict[str, list[ResearchTrade]] = {}

        for trade in trades:
            key = str(
                key_func(trade)
                or "Unknown"
            )

            groups.setdefault(
                key,
                [],
            ).append(trade)

        rows = [
            self._trade_group_payload(
                label=label,
                trades=items,
            )
            for label, items in groups.items()
        ]

        rows.sort(
            key=lambda item: (
                int(item["total"]),
                abs(float(item["total_profit"])),
            ),
            reverse=True,
        )

        return rows

    def _trade_group_payload(
        self,
        *,
        label: str,
        trades: list[ResearchTrade],
    ) -> dict[str, object]:
        completed = [
            trade
            for trade in trades
            if trade.status in {
                TradeStatus.CLOSED,
                TradeStatus.EXPIRED,
            }
        ]

        clean = [
            trade
            for trade in completed
            if not trade.is_excluded
        ]

        wins = [
            trade
            for trade in clean
            if trade.profit_percent > 0
        ]

        losses = [
            trade
            for trade in clean
            if trade.profit_percent < 0
        ]

        breakeven = [
            trade
            for trade in clean
            if trade.profit_percent == 0
        ]

        profitable_expired = [
            trade
            for trade in clean
            if trade.is_profitable_expired
        ]

        decisive = len(wins) + len(losses)

        return {
            "label": label,
            "total": len(trades),
            "completed": len(completed),
            "clean_completed": len(clean),
            "excluded": len(completed) - len(clean),
            "wins": len(wins),
            "losses": len(losses),
            "breakeven": len(breakeven),
            "profitable_expired": len(profitable_expired),
            "waiting_entry": sum(
                1
                for trade in trades
                if trade.status == TradeStatus.WAITING_ENTRY
            ),
            "active": sum(
                1
                for trade in trades
                if trade.status == TradeStatus.ACTIVE
            ),
            "candidate": sum(
                1
                for trade in trades
                if trade.status == TradeStatus.CANDIDATE
            ),
            "expired": sum(
                1
                for trade in trades
                if trade.status == TradeStatus.EXPIRED
            ),
            "win_rate": (
                len(wins)
                / decisive
                * 100
                if decisive > 0
                else 0.0
            ),
            "total_profit": sum(
                trade.profit_amount
                for trade in clean
            ),
            "average_rr": (
                sum(
                    trade.rr
                    for trade in clean
                )
                / len(clean)
                if clean
                else 0.0
            ),
            "symbols": sorted(
                {
                    trade.symbol
                    for trade in trades
                }
            ),
        }

    @staticmethod
    def _setup_reason_key(
        trade: ResearchTrade,
    ) -> str:
        haystack = " | ".join(
            [
                trade.strategy,
                *trade.reasons,
                trade.close_reason or "",
            ]
        ).lower()

        checks = [
            ("Liquidity Buildup Sweep", "liquidity buildup"),
            ("Liquidity Sweep", "liquidity sweep"),
            ("Bullish/Bearish Retest", "retest"),
            ("Double Top/Bottom", "double top"),
            ("Double Top/Bottom", "double bottom"),
            ("False Breakout", "false breakout"),
            ("Fair Value Gap", "fair value gap"),
            ("Order Block", "orderblock"),
            ("Order Block", "order block"),
            ("Compression", "compression"),
            ("Premium/Discount", "premium"),
            ("Premium/Discount", "discount"),
            ("Breakout", "breakout"),
            ("CHoCH", "choch"),
            ("BOS", "bos"),
        ]

        for label, needle in checks:
            if needle in haystack:
                return label

        return trade.strategy or "Unknown"

    @staticmethod
    def _close_reason_key(
        reason: str | None,
    ) -> str:
        normalized = str(
            reason
            or ""
        ).lower()

        if "risk geometry" in normalized:
            return "Risk geometry blocked"

        if "target" in normalized or "blocked by support" in normalized or "blocked by resistance" in normalized:
            return "Target blocked"

        if "reaction" in normalized:
            return "Reaction blocked"

        if "parabolic" in normalized:
            return "Parabolic blocked"

        if "duplicate" in normalized:
            return "Duplicate cleanup"

        if "candidate_promoted" in normalized:
            return "Candidate promoted"

        if "candidate_promotion_blocked" in normalized:
            return "Candidate promotion blocked"

        if normalized == "tp":
            return "TP"

        if normalized == "sl":
            return "SL"

        if normalized == "expired":
            return "Expired"

        if "manual" in normalized:
            return "Manual cleanup"

        return reason or "Unknown"

