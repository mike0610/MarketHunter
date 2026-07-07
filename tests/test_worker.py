"""
MarketHunter

Tests for continuous research worker behavior.
"""

from __future__ import annotations

import asyncio
import unittest

from app.worker import run_forever


class ResearchWorkerTests(
    unittest.IsolatedAsyncioTestCase,
):
    """
    Test worker scheduling and failure recovery.
    """

    async def test_runs_cycle_immediately_then_waits(
        self,
    ) -> None:
        """
        Worker runs one cycle before the first interval wait.
        """

        calls: list[str] = []
        sleep_delays: list[float] = []

        async def cycle_runner() -> None:
            calls.append("cycle")

        async def stop_after_first_wait(
            seconds: float,
        ) -> None:
            sleep_delays.append(seconds)
            raise asyncio.CancelledError

        with self.assertRaises(
            asyncio.CancelledError,
        ):
            await run_forever(
                cycle_runner=cycle_runner,
                interval_seconds=3600,
                retry_delay_seconds=60,
                sleep=stop_after_first_wait,
            )

        self.assertEqual(
            calls,
            ["cycle"],
        )

        self.assertEqual(
            len(sleep_delays),
            1,
        )

        self.assertGreater(
            sleep_delays[0],
            0,
        )

        self.assertLessEqual(
            sleep_delays[0],
            3600,
        )

    async def test_failed_cycle_uses_retry_delay(
        self,
    ) -> None:
        """
        Worker waits for retry delay after a failed cycle.
        """

        calls: list[str] = []
        sleep_delays: list[float] = []

        async def failing_cycle() -> None:
            calls.append("cycle")
            raise RuntimeError(
                "Test cycle failure."
            )

        async def stop_after_retry_wait(
            seconds: float,
        ) -> None:
            sleep_delays.append(seconds)
            raise asyncio.CancelledError

        with self.assertRaises(
            asyncio.CancelledError,
        ):
            await run_forever(
                cycle_runner=failing_cycle,
                interval_seconds=3600,
                retry_delay_seconds=45,
                sleep=stop_after_retry_wait,
            )

        self.assertEqual(
            calls,
            ["cycle"],
        )

        self.assertEqual(
            sleep_delays,
            [45],
        )

    async def test_rejects_invalid_intervals(
        self,
    ) -> None:
        """
        Worker validates scheduling configuration.
        """

        async def cycle_runner() -> None:
            return None

        with self.assertRaises(ValueError):
            await run_forever(
                cycle_runner=cycle_runner,
                interval_seconds=0,
            )

        with self.assertRaises(ValueError):
            await run_forever(
                cycle_runner=cycle_runner,
                retry_delay_seconds=0,
            )


if __name__ == "__main__":
    unittest.main()