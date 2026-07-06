"""
MarketHunter

services/worker_pool.py
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


class WorkerPool:
    """
    Limits the number of concurrent async tasks.
    """

    def __init__(self, workers: int = 10) -> None:
        self._semaphore = asyncio.Semaphore(workers)

    async def run(
        self,
        func: Callable[..., Awaitable[T]],
        *args,
        **kwargs,
    ) -> T:
        async with self._semaphore:
            return await func(*args, **kwargs)