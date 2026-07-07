"""
MarketHunter

Module:
Research Worker

Responsibilities:
- Run the complete MarketHunter research cycle continuously.
- Start one cycle immediately after worker startup.
- Repeat cycles at a configured interval.
- Retry after a short delay when one cycle fails.
- Never send real orders to any exchange.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from time import monotonic

from loguru import logger

from app.main import main as run_research_cycle


CycleRunner = Callable[[], Awaitable[None]]
SleepFunction = Callable[[float], Awaitable[None]]


RUN_INTERVAL_SECONDS = 60 * 60
RETRY_DELAY_SECONDS = 60


async def run_forever(
    cycle_runner: CycleRunner = run_research_cycle,
    interval_seconds: float = RUN_INTERVAL_SECONDS,
    retry_delay_seconds: float = RETRY_DELAY_SECONDS,
    sleep: SleepFunction = asyncio.sleep,
) -> None:
    """
    Run MarketHunter cycles continuously.

    The first cycle runs immediately. Successful cycles repeat after the
    configured interval measured from the start of the previous cycle.

    When a cycle fails, the worker waits for retry_delay_seconds and
    tries again without terminating the process.
    """

    if interval_seconds <= 0:
        raise ValueError(
            "Worker interval must be greater than zero."
        )

    if retry_delay_seconds <= 0:
        raise ValueError(
            "Worker retry delay must be greater than zero."
        )

    cycle_number = 0

    logger.info("=" * 60)
    logger.info(
        "MarketHunter worker started | Interval: {} seconds",
        int(interval_seconds),
    )
    logger.info(
        "Press Ctrl+C to stop the worker."
    )
    logger.info("=" * 60)

    while True:
        cycle_number += 1
        cycle_started_at = monotonic()

        logger.info(
            "Worker cycle {} started.",
            cycle_number,
        )

        try:
            await cycle_runner()

        except asyncio.CancelledError:
            logger.info(
                "MarketHunter worker cancelled."
            )
            raise

        except Exception:
            logger.exception(
                "Worker cycle {} failed.",
                cycle_number,
            )

            logger.info(
                "Worker will retry in {} seconds.",
                int(retry_delay_seconds),
            )

            await sleep(retry_delay_seconds)
            continue

        elapsed_seconds = monotonic() - cycle_started_at

        wait_seconds = max(
            0.0,
            interval_seconds - elapsed_seconds,
        )

        logger.info(
            "Worker cycle {} finished. "
            "Next cycle in {:.0f} seconds.",
            cycle_number,
            wait_seconds,
        )

        await sleep(wait_seconds)


async def main() -> None:
    """
    Start the continuous MarketHunter research worker.
    """

    await run_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())

    except KeyboardInterrupt:
        logger.info(
            "MarketHunter worker stopped by user."
        )