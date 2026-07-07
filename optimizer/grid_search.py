"""
MarketHunter

optimizer/grid_search.py
"""

from __future__ import annotations

from models.optimizer_result import (
    OptimizerResult,
)


class GridSearch:

    def search(
        self,
        grid: list[dict],
        evaluator,
    ) -> OptimizerResult:

        best = None

        best_score = -1.0

        for params in grid:

            result = evaluator(params)

            if result.score > best_score:

                best_score = result.score

                best = result

        return best