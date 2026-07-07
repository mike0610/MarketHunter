"""
MarketHunter

Tests for continuous research worker behavior.
"""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from app.worker import run_forever
from research.storage.repository import ResearchRepository


class ResearchWorkerTests(
    unittest.IsolatedAsyncioTestCase,
):
    """
    Test worker scheduling, status persistence and error recovery.
    """

    async def test_runs_cycle_immediately_then_waits(
        self,
    ) -> None:
        """
        Worker runs one cycle before waiting for interval.
        """

        calls: list[str] = []
        sleep_delays: list[float] = []
        states_seen_during_sleep: list[str] = []

        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "research.db"

            def repository_factory() -> ResearchRepository:
                return ResearchRepository(
                    path=str(database_path),
                )

            async def cycle_runner() -> None:
                calls.append("cycle")

            async def stop_after_first_wait(
                seconds: float,
            ) -> None:
                sleep_delays.append(seconds)

                repository = ResearchRepository(
                    path=str(database_path),
                )

                try:
                    status = repository.get_worker_status()

                    self.assertIsNotNone(status)

                    states_seen_during_sleep.append(
                        status.state,
                    )
                finally:
                    repository.close()

                raise asyncio.CancelledError

            with self.assertRaises(
                asyncio.CancelledError,
            ):
                await run_forever(
                    cycle_runner=cycle_runner,
                    interval_seconds=3600,
                    retry_delay_seconds=60,
                    sleep=stop_after_first_wait,
                    repository_factory=repository_factory,
                )

        self.assertEqual(
            calls,
            ["cycle"],
        )

        self.assertEqual(
            states_seen_during_sleep,
            ["waiting"],
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
        Worker persists error state and waits for retry delay.
        """

        calls: list[str] = []
        sleep_delays: list[float] = []
        errors_seen_during_sleep: list[str | None] = []

        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "research.db"

            def repository_factory() -> ResearchRepository:
                return ResearchRepository(
                    path=str(database_path),
                )

            async def failing_cycle() -> None:
                calls.append("cycle")

                raise RuntimeError(
                    "Test cycle failure."
                )

            async def stop_after_retry_wait(
                seconds: float,
            ) -> None:
                sleep_delays.append(seconds)

                repository = ResearchRepository(
                    path=str(database_path),
                )

                try:
                    status = repository.get_worker_status()

                    self.assertIsNotNone(status)
                    self.assertEqual(
                        status.state,
                        "error",
                    )

                    errors_seen_during_sleep.append(
                        status.last_error,
                    )
                finally:
                    repository.close()

                raise asyncio.CancelledError

            with self.assertRaises(
                asyncio.CancelledError,
            ):
                await run_forever(
                    cycle_runner=failing_cycle,
                    interval_seconds=3600,
                    retry_delay_seconds=45,
                    sleep=stop_after_retry_wait,
                    repository_factory=repository_factory,
                )

        self.assertEqual(
            calls,
            ["cycle"],
        )

        self.assertEqual(
            sleep_delays,
            [45],
        )

        self.assertEqual(
            len(errors_seen_during_sleep),
            1,
        )

        self.assertIn(
            "RuntimeError: Test cycle failure.",
            errors_seen_during_sleep[0],
        )

    async def test_status_is_running_during_cycle(
        self,
    ) -> None:
        """
        Worker writes running status before calling cycle runner.
        """

        states_seen_during_cycle: list[str] = []

        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "research.db"

            def repository_factory() -> ResearchRepository:
                return ResearchRepository(
                    path=str(database_path),
                )

            async def cycle_runner() -> None:
                repository = ResearchRepository(
                    path=str(database_path),
                )

                try:
                    status = repository.get_worker_status()

                    self.assertIsNotNone(status)

                    states_seen_during_cycle.append(
                        status.state,
                    )
                finally:
                    repository.close()

            async def stop_after_first_wait(
                seconds: float,
            ) -> None:
                _ = seconds

                raise asyncio.CancelledError

            with self.assertRaises(
                asyncio.CancelledError,
            ):
                await run_forever(
                    cycle_runner=cycle_runner,
                    interval_seconds=3600,
                    retry_delay_seconds=60,
                    sleep=stop_after_first_wait,
                    repository_factory=repository_factory,
                )

        self.assertEqual(
            states_seen_during_cycle,
            ["running"],
        )

    async def test_cancellation_marks_worker_stopped(
        self,
    ) -> None:
        """
        Worker persists stopped state after cancellation.
        """

        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "research.db"

            def repository_factory() -> ResearchRepository:
                return ResearchRepository(
                    path=str(database_path),
                )

            async def cycle_runner() -> None:
                return None

            async def stop_after_first_wait(
                seconds: float,
            ) -> None:
                _ = seconds

                raise asyncio.CancelledError

            with self.assertRaises(
                asyncio.CancelledError,
            ):
                await run_forever(
                    cycle_runner=cycle_runner,
                    interval_seconds=3600,
                    retry_delay_seconds=60,
                    sleep=stop_after_first_wait,
                    repository_factory=repository_factory,
                )

            repository = ResearchRepository(
                path=str(database_path),
            )

            try:
                status = repository.get_worker_status()

                self.assertIsNotNone(status)
                self.assertEqual(
                    status.state,
                    "stopped",
                )
                self.assertEqual(
                    status.cycle_number,
                    1,
                )
                self.assertIsNone(
                    status.next_cycle_at,
                )
            finally:
                repository.close()

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