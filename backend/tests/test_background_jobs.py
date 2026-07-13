import asyncio

import pytest

from app.services.background_jobs import (
    PeriodicJob,
    run_job_forever,
    start_background_jobs,
    stop_background_jobs,
)


class TestPeriodicJob:
    def test_rejects_non_positive_interval(self):
        async def noop():
            pass

        with pytest.raises(ValueError):
            PeriodicJob(name="bad", interval_seconds=0, func=noop)


class TestRunJobForever:
    async def test_runs_repeatedly(self):
        calls = 0

        async def job_func():
            nonlocal calls
            calls += 1

        job = PeriodicJob(name="counter", interval_seconds=0.01, func=job_func)
        task = asyncio.create_task(run_job_forever(job))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert calls >= 2

    async def test_error_does_not_stop_loop(self):
        calls = 0

        async def failing_func():
            nonlocal calls
            calls += 1
            raise RuntimeError("boom")

        job = PeriodicJob(name="failing", interval_seconds=0.01, func=failing_func)
        task = asyncio.create_task(run_job_forever(job))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert calls >= 2


class TestStartStop:
    async def test_start_and_stop(self):
        started = asyncio.Event()

        async def job_func():
            started.set()

        jobs = [PeriodicJob(name="j1", interval_seconds=0.01, func=job_func)]
        tasks = start_background_jobs(jobs)
        assert len(tasks) == 1
        await asyncio.wait_for(started.wait(), timeout=1)
        await stop_background_jobs(tasks)
        assert all(t.done() for t in tasks)
