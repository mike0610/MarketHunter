"""
MarketHunter

optimizer/parameter_grid.py
"""

from __future__ import annotations

from itertools import product


class ParameterGrid:
    """
    Parameter combinations.
    """

    def build(
        self,
        parameters: dict,
    ) -> list[dict]:

        keys = list(parameters.keys())

        values = list(parameters.values())

        result = []

        for combination in product(*values):

            result.append(

                dict(
                    zip(
                        keys,
                        combination,
                    )
                )

            )

        return result