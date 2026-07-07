"""
MarketHunter

Module:
Research Worker

Responsibilities:
- Run the complete MarketHunter research cycle continuously.
- Persist current worker state in SQLite.
- Start one cycle immediately after worker startup.
- Repeat cycles at a configured interval.
- Retry after a short delay when one cycle fails.
- Never send real orders to any exchange.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from time import monotonic

from loguru import logger

from app.main import DATABASE_PATH
from app.main import main as run_research_cycle
from research.storage.repository import ResearchRepository


CycleRunner = Callable[[], Awaitable[None]]
SleepFunction = Callable[[float], Awaitable[None]]
StatusRepositoryFactory = Callable[[], ResearchRepository]
WallClock = Callable[[], datetime]
MonotonicClock = Callable[[], float]


RUN_INTERVAL_SECONDS = 60 * 60
RETRY_DELAY_SECONDS = 60


def utc_now() -> datetime:
    """
    Return current timezone-aware UTC time.
    """

    return datetime.now(
        UTC,
    )


def create_status_repository() -> ResearchRepository:
    """
    Create the SQLite repository used for worker-state persistence.
    """

    return ResearchRepository(
        path=DATABASE_PATH,
    )


async def run_forever(
    cycle_runner: CycleRunner = run_research_cycle,
    interval_seconds: float = RUN_INTERVAL_SECONDS,
    retry_delay_seconds: float = RETRY_DELAY_SECONDS,
    sleep: SleepFunction = asyncio.sleep,
    repository_factory: StatusRepositoryFactory = (
        create_status_repository
    ),
    now: WallClock = utc_now,
    monotonic_clock: MonotonicClock = monotonic,
) -> None:
    """
    Run MarketHunter cycles continuously.

    The first cycle starts immediately.

    A successful cycle waits until the configured interval has elapsed
    from the beginning of that cycle. A failed cycle waits only for the
    configured retry delay.

    Status is written to SQLite before, during and after each cycle so
    FastAPI and Dashboard can display actual worker state.
    """

    if interval_seconds <= 0:
        raise ValueError(
            "Worker interval must be greater than zero."
        )

    if retry_delay_seconds <= 0:
        raise ValueError(
            "Worker retry delay must be greater than zero."
        )

    repository = repository_factory()

    cycle_number = 0
    last_cycle_started_at: datetime | None = None
    last_cycle_finished_at: datetime | None = None
    next_cycle_at: datetime | None = None
    last_error: str | None = None

    started_at = now()

    repository.save_worker_status(
        state="starting",
        cycle_number=cycle_number,
        last_cycle_started_at=None,
        last_cycle_finished_at=None,
        next_cycle_at=None,
        last_error=None,
        updated_at=started_at,
    )

    logger.info("=" * 60)
    logger.info(
        "MarketHunter worker started | Interval: {} seconds",
        int(interval_seconds),
    )
    logger.info(
        "Press Ctrl+C to stop the worker."
    )
    logger.info("=" * 60)

    try:
        while True:
            cycle_number += 1

            last_cycle_started_at = now()
            next_cycle_at = None
            last_error = None

            repository.save_worker_status(
                state="running",
                cycle_number=cycle_number,
                last_cycle_started_at=last_cycle_started_at,
                last_cycle_finished_at=(
                    last_cycle_finished_at
                ),
                next_cycle_at=None,
                last_error=None,
                updated_at=last_cycle_started_at,
            )

            cycle_started_monotonic = monotonic_clock()

            logger.info(
                "Worker cycle {} started.",
                cycle_number,
            )

            try:
                await cycle_runner()

            except Exception as error:
                last_cycle_finished_at = now()
                next_cycle_at = (
                    last_cycle_finished_at
                    + timedelta(
                        seconds=retry_delay_seconds
                    )
                )

                last_error = (
                    f"{type(error).__name__}: {error}"
                )

                repository.save_worker_status(
                    state="error",
                    cycle_number=cycle_number,
                    last_cycle_started_at=(
                        last_cycle_started_at
                    ),
                    last_cycle_finished_at=(
                        last_cycle_finished_at
                    ),
                    next_cycle_at=next_cycle_at,
                    last_error=last_error,
                    updated_at=last_cycle_finished_at,
                )

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

            elapsed_seconds = (
                monotonic_clock()
                - cycle_started_monotonic
            )

            wait_seconds = max(
                0.0,
                interval_seconds - elapsed_seconds,
            )

            last_cycle_finished_at = now()

            next_cycle_at = (
                last_cycle_finished_at
                + timedelta(seconds=wait_seconds)
            )

            repository.save_worker_status(
                state="waiting",
                cycle_number=cycle_number,
                last_cycle_started_at=(
                    last_cycle_started_at
                ),
                last_cycle_finished_at=(
                    last_cycle_finished_at
                ),
                next_cycle_at=next_cycle_at,
                last_error=None,
                updated_at=last_cycle_finished_at,
            )

            logger.info(
                "Worker cycle {} finished. "
                "Next cycle in {:.0f} seconds.",
                cycle_number,
                wait_seconds,
            )

            await sleep(wait_seconds)

    except asyncio.CancelledError:
        stopped_at = now()

        repository.save_worker_status(
            state="stopped",
            cycle_number=cycle_number,
            last_cycle_started_at=(
                last_cycle_started_at
            ),
            last_cycle_finished_at=(
                last_cycle_finished_at
            ),
            next_cycle_at=None,
            last_error=last_error,
            updated_at=stopped_at,
        )

        logger.info(
            "MarketHunter worker cancelled."
        )

        raise

    finally:
        repository.close()


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