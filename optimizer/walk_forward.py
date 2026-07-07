"""
MarketHunter

optimizer/walk_forward.py
"""

from __future__ import annotations


class WalkForward:

    def split(

        self,

        candles,

        train_size: int,

        test_size: int,

    ):

        index = 0

        while (

            index

            + train_size

            + test_size

            <= len(candles)

        ):

            train = candles[

                index:

                index + train_size

            ]

            test = candles[

                index + train_size:

                index + train_size + test_size

            ]

            yield train, test

            index += test_size