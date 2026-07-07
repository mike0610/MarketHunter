"""
MarketHunter

optimizer/optimizer.py
"""

from __future__ import annotations

from optimizer.grid_search import (
    GridSearch,
)

from optimizer.parameter_grid import (
    ParameterGrid,
)

from optimizer.walk_forward import (
    WalkForward,
)


class Optimizer:
    """
    Walk Forward Optimizer.
    """

    def __init__(self):

        self.grid = ParameterGrid()

        self.search = GridSearch()

        self.walk = WalkForward()

    def optimize(

        self,

        candles,

        parameters,

        evaluator,

        train=500,

        test=100,

    ):

        combinations = self.grid.build(
            parameters,
        )

        best = None

        for train_set, test_set in self.walk.split(

            candles,

            train,

            test,

        ):

            result = self.search.search(

                combinations,

                lambda params: evaluator(

                    train_set,

                    test_set,

                    params,

                ),

            )

            if best is None:

                best = result

                continue

            if result.score > best.score:

                best = result

        return best