from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.services.job_scheduler import JobSchedulerService


class TestJobSchedulerService:
    def test_compute_next_run_daily_rollover(self):
        after = datetime(2026, 1, 1, 10, 30, tzinfo=UTC)
        next_run = JobSchedulerService.compute_next_run(
            frequency="daily",
            run_hour=9,
            run_day=None,
            after=after,
        )
        assert next_run == datetime(2026, 1, 2, 9, 0, tzinfo=UTC)

    def test_compute_next_run_daily_same_day_when_still_before_hour(self):
        after = datetime(2026, 1, 1, 8, 30, tzinfo=UTC)
        next_run = JobSchedulerService.compute_next_run(
            frequency="daily",
            run_hour=9,
            run_day=None,
            after=after,
        )
        assert next_run == datetime(2026, 1, 1, 9, 0, tzinfo=UTC)

    def test_compute_next_run_weekly_wraps_across_boundary(self):
        after = datetime(2026, 1, 7, 10, 0, tzinfo=UTC)  # Wednesday
        next_run = JobSchedulerService.compute_next_run(
            frequency="weekly",
            run_hour=9,
            run_day=0,  # Monday
            after=after,
        )
        assert next_run == datetime(2026, 1, 12, 9, 0, tzinfo=UTC)

    def test_compute_next_run_monthly_clamps_31_to_30_day_month(self):
        after = datetime(2026, 4, 10, 10, 0, tzinfo=UTC)
        next_run = JobSchedulerService.compute_next_run(
            frequency="monthly",
            run_hour=9,
            run_day=31,
            after=after,
        )
        assert next_run == datetime(2026, 4, 30, 9, 0, tzinfo=UTC)

    def test_compute_next_run_monthly_clamps_31_to_28_day_month(self):
        after = datetime(2026, 2, 27, 10, 0, tzinfo=UTC)
        next_run = JobSchedulerService.compute_next_run(
            frequency="monthly",
            run_hour=9,
            run_day=31,
            after=after,
        )
        assert next_run == datetime(2026, 2, 28, 9, 0, tzinfo=UTC)

    def test_is_due(self):
        now = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
        assert JobSchedulerService.is_due(next_run_at=datetime(2026, 1, 1, 9, 59, tzinfo=UTC), now=now) is True
        assert JobSchedulerService.is_due(next_run_at=datetime(2026, 1, 1, 10, 1, tzinfo=UTC), now=now) is False
        assert JobSchedulerService.is_due(next_run_at=None, now=now) is False

    def test_next_status_transitions(self):
        assert JobSchedulerService.next_status("pending", success=True, attempt_count=0, max_attempts=3) == "succeeded"
        assert JobSchedulerService.next_status("running", success=False, attempt_count=1, max_attempts=3) == "failed_retry"
        assert JobSchedulerService.next_status("running", success=False, attempt_count=3, max_attempts=3) == "dead"

    def test_next_status_rejects_terminal_states(self):
        for current_status in ["succeeded", "dead"]:
            with pytest.raises(ValueError):
                JobSchedulerService.next_status(current_status, success=False, attempt_count=1, max_attempts=3)

    def test_order_queue_sorts_by_priority_then_time(self):
        items = [
            SimpleNamespace(name="late", priority=20, scheduled_for=datetime(2026, 1, 1, 9, 0, tzinfo=UTC), created_at=datetime(2026, 1, 1, 8, 0, tzinfo=UTC)),
            SimpleNamespace(name="first", priority=10, scheduled_for=datetime(2026, 1, 1, 9, 0, tzinfo=UTC), created_at=datetime(2026, 1, 1, 7, 0, tzinfo=UTC)),
            SimpleNamespace(name="second", priority=10, scheduled_for=datetime(2026, 1, 1, 9, 0, tzinfo=UTC), created_at=datetime(2026, 1, 1, 8, 0, tzinfo=UTC)),
            SimpleNamespace(name="earlier_time", priority=10, scheduled_for=datetime(2026, 1, 1, 8, 0, tzinfo=UTC), created_at=datetime(2026, 1, 1, 9, 0, tzinfo=UTC)),
        ]
        ordered = JobSchedulerService.order_queue(items)
        assert [item.name for item in ordered] == ["earlier_time", "first", "second", "late"]

    def test_can_claim_predicate(self):
        assert JobSchedulerService.can_claim(0) is True
        assert JobSchedulerService.can_claim(1) is False

    def test_select_due_jobs_filters_inactive_and_future(self):
        now = datetime(2026, 6, 30, 10, 0, tzinfo=UTC)
        jobs = [
            SimpleNamespace(name="due_low", priority=50, is_active=True, next_run_at=datetime(2026, 6, 30, 9, 0, tzinfo=UTC)),
            SimpleNamespace(name="due_high", priority=10, is_active=True, next_run_at=datetime(2026, 6, 30, 8, 0, tzinfo=UTC)),
            SimpleNamespace(name="future", priority=1, is_active=True, next_run_at=datetime(2026, 6, 30, 23, 0, tzinfo=UTC)),
            SimpleNamespace(name="inactive", priority=1, is_active=False, next_run_at=datetime(2026, 6, 30, 1, 0, tzinfo=UTC)),
            SimpleNamespace(name="unscheduled", priority=1, is_active=True, next_run_at=None),
        ]
        due = JobSchedulerService.select_due_jobs(jobs, now=now)
        assert [job.name for job in due] == ["due_high", "due_low"]
