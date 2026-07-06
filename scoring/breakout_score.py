"""
MarketHunter

scoring/breakout_score.py
"""

from __future__ import annotations

from models.market_snapshot import MarketSnapshot


class BreakoutScore:

    def calculate(
        self,
        snapshot: MarketSnapshot,
    ) -> tuple[int, list[str]]:

        last = snapshot.candles[-1]

        score = 0
        reasons: list[str] = []

        if snapshot.ema50 > snapshot.ema200:
            score += 25
            reasons.append("EMA50 > EMA200")

        if last.close > snapshot.highest20:
            score += 35
            reasons.append("20-day breakout")

        if last.volume > snapshot.avg_volume20 * 1.5:
            score += 20
            reasons.append("Volume x1.5")

        if last.body > snapshot.atr14:
            score += 20
            reasons.append("ATR impulse")

        return score, reasons