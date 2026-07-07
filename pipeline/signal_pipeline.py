"""
MarketHunter

Central signal processing pipeline.
"""

from __future__ import annotations

from collections.abc import Iterable

from pipeline.context import SignalContext
from pipeline.handler import SignalHandler


class SignalPipeline:
    """
    Runs signal handlers in a deterministic order.

    Scanner remains independent:
    it finds signals and does not know who consumes them.
    """

    def __init__(
        self,
        handlers: Iterable[SignalHandler] | None = None,
    ) -> None:

        self.handlers: list[SignalHandler] = list(
            handlers or []
        )

    def add_handler(
        self,
        handler: SignalHandler,
    ) -> "SignalPipeline":
        """
        Add one handler and return pipeline for chaining.
        """

        self.handlers.append(handler)

        return self

    async def process(
        self,
        context: SignalContext,
    ) -> SignalContext:
        """
        Run all handlers until context is rejected.
        """

        for handler in self.handlers:

            if not context.accepted:
                break

            await handler.handle(context)

            context.handled_by.append(
                handler.name
            )

        return context