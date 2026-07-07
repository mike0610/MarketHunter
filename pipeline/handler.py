"""
MarketHunter

Base interface for signal pipeline handlers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from pipeline.context import SignalContext


class SignalHandler(ABC):
    """
    One processing step in the signal pipeline.
    """

    @property
    def name(self) -> str:
        """
        Handler name used for diagnostics.
        """

        return self.__class__.__name__

    @abstractmethod
    async def handle(
        self,
        context: SignalContext,
    ) -> None:
        """
        Process one signal context.
        """