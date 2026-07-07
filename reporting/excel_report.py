"""
MarketHunter

reporting/excel_report.py
"""

from __future__ import annotations

from openpyxl import Workbook


class ExcelReport:

    def save(
        self,
        result,
        filename: str,
    ) -> None:

        workbook = Workbook()

        sheet = workbook.active

        sheet.append(
            [
                "Metric",
                "Value",
            ]
        )

        sheet.append(
            [
                "Trades",
                result.trades,
            ]
        )

        sheet.append(
            [
                "Wins",
                result.wins,
            ]
        )

        sheet.append(
            [
                "Losses",
                result.losses,
            ]
        )

        sheet.append(
            [
                "Win Rate",
                result.win_rate,
            ]
        )

        sheet.append(
            [
                "Profit Factor",
                result.profit_factor,
            ]
        )

        sheet.append(
            [
                "Drawdown",
                result.max_drawdown,
            ]
        )

        sheet.append(
            [
                "Return",
                result.total_return,
            ]
        )

        workbook.save(
            filename,
        )