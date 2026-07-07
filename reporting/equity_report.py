"""
MarketHunter

reporting/equity_report.py
"""

from __future__ import annotations

import matplotlib.pyplot as plt


class EquityReport:

    def save(
        self,
        result,
        filename: str,
    ) -> None:

        plt.figure(
            figsize=(10, 5),
        )

        plt.plot(
            result.equity_curve,
        )

        plt.title(
            "Equity Curve",
        )

        plt.xlabel(
            "Trades",
        )

        plt.ylabel(
            "Balance",
        )

        plt.grid(
            True,
        )

        plt.tight_layout()

        plt.savefig(
            filename,
        )

        plt.close()