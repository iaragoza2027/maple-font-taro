from __future__ import annotations

from concurrent.futures import Future
import unittest
from unittest.mock import MagicMock

from scripts.utils.process import run_jobs, run_process_jobs


class ProcessExecutorTest(unittest.TestCase):
    def test_run_process_jobs_uses_serial_execution_for_one_worker(self) -> None:
        calls: list[int] = []

        results = run_process_jobs(
            1,
            lambda value: calls.append(value) or value * 2,
            [1, 2, 3],
        )

        self.assertEqual(results, [2, 4, 6])
        self.assertEqual(calls, [1, 2, 3])

    def test_run_jobs_preserves_input_order(self) -> None:
        executor = MagicMock()
        futures: list[Future[int]] = []
        for result in (4, 2, 6):
            future: Future[int] = Future()
            future.set_result(result)
            futures.append(future)
        executor.submit.side_effect = futures

        results = run_jobs(executor, lambda value: value * 2, [2, 1, 3])

        self.assertEqual(results, [4, 2, 6])

    def test_run_jobs_cancels_pending_work_after_failure(self) -> None:
        executor = MagicMock()
        failed: Future[None] = Future()
        failed.set_exception(RuntimeError("failed"))
        pending: Future[None] = Future()
        executor.submit.side_effect = [failed, pending]

        with self.assertRaisesRegex(RuntimeError, "failed"):
            run_jobs(executor, lambda _: None, [1, 2])

        self.assertTrue(pending.cancelled())


if __name__ == "__main__":
    unittest.main()
