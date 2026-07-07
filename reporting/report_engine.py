"""
MarketHunter

reporting/report_engine.py
"""

from __future__ import annotations

from pathlib import Path

from reporting.pdf_report import PDFReport
from reporting.excel_report import ExcelReport
from reporting.statistics_report import StatisticsReport
from reporting.equity_report import EquityReport


class ReportEngine:
    """
    Central reporting engine.
    """

    def __init__(self) -> None:

        self.pdf = PDFReport()

        self.excel = ExcelReport()

        self.statistics = StatisticsReport()

        self.equity = EquityReport()

    def create_all(
        self,
        result,
        directory: str = "reports",
    ) -> None:

        Path(directory).mkdir(
            exist_ok=True,
        )

        self.statistics.save(
            result,
            f"{directory}/statistics.txt",
        )

        self.pdf.save(
            result,
            f"{directory}/backtest.pdf",
        )

        self.excel.save(
            result,
            f"{directory}/backtest.xlsx",
        )

        self.equity.save(
            result,
            f"{directory}/equity.png",
        )