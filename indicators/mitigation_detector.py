"""
MarketHunter

indicators/mitigation_detector.py
"""

from __future__ import annotations

from indicators.order_block_detector import (
    OrderBlockDetector,
)
from models.candle import Candle
from models.mitigation_block import MitigationBlock
from structure.market_structure_engine import (
    MarketStructureEngine,
)


class MitigationDetector:
    """
    Detect mitigated Order Blocks.
    """

    def __init__(self) -> None:

        self.structure = MarketStructureEngine()
        self.order_blocks = OrderBlockDetector()

    def bullish(
        self,
        candles: list[Candle],
    ) -> list[MitigationBlock]:

        market = self.structure.analyze(candles)

        if not market.bullish:
            return []

        blocks = self.order_blocks.bullish(candles)

        mitigated: list[MitigationBlock] = []

        for block in blocks:

            for index in range(
                block.candle_index + 1,
                len(candles),
            ):

                candle = candles[index]

                #
                # Price returned into block
                #

                if candle.low <= block.high:

                    mitigated.append(

                        MitigationBlock(
                            bullish=True,
                            high=block.high,
                            low=block.low,
                            created_index=block.candle_index,
                            mitigation_index=index,
                            touched=True,
                        )

                    )

                    break

        return mitigated

    def bearish(
        self,
        candles: list[Candle],
    ) -> list[MitigationBlock]:

        market = self.structure.analyze(candles)

        if not market.bearish:
            return []

        blocks = self.order_blocks.bearish(candles)

        mitigated: list[MitigationBlock] = []

        for block in blocks:

            for index in range(
                block.candle_index + 1,
                len(candles),
            ):

                candle = candles[index]

                if candle.high >= block.low:

                    mitigated.append(

                        MitigationBlock(
                            bullish=False,
                            high=block.high,
                            low=block.low,
                            created_index=block.candle_index,
                            mitigation_index=index,
                            touched=True,
                        )

                    )

                    break

        return mitigated

    def latest_bullish(
        self,
        candles: list[Candle],
    ) -> MitigationBlock | None:

        blocks = self.bullish(candles)

        return blocks[-1] if blocks else None

    def latest_bearish(
        self,
        candles: list[Candle],
    ) -> MitigationBlock | None:

        blocks = self.bearish(candles)

        return blocks[-1] if blocks else None