"""
MarketHunter

reporting/pdf_report.py
"""

from __future__ import annotations

from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
)

from reportlab.lib.styles import (
    getSampleStyleSheet,
)


class PDFReport:

    def save(
        self,
        result,
        filename: str,
    ) -> None:

        styles = getSampleStyleSheet()

        pdf = SimpleDocTemplate(
            filename,
        )

        items = [

            Paragraph(
                "<b>MarketHunter Report</b>",
                styles["Heading1"],
            ),

            Paragraph(
                f"Trades: {result.trades}",
                styles["BodyText"],
            ),

            Paragraph(
                f"Win Rate: {result.win_rate:.2f}%",
                styles["BodyText"],
            ),

            Paragraph(
                f"Profit Factor: {result.profit_factor:.2f}",
                styles["BodyText"],
            ),

            Paragraph(
                f"Drawdown: {result.max_drawdown:.2f}%",
                styles["BodyText"],
            ),

            Paragraph(
                f"Return: {result.total_return:.2f}%",
                styles["BodyText"],
            ),

        ]

        pdf.build(
            items,
        )