from __future__ import annotations

from calendar import monthrange
from datetime import UTC, datetime, timedelta
from typing import Any


class JobSchedulerService:
    @staticmethod
    def _utc(dt: datetime) -> datetime:
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)

    @staticmethod
    def _build_datetime(year: int, month: int, day: int, hour: int) -> datetime:
        return datetime(year, month, day, hour, 0, 0, tzinfo=UTC)

    @staticmethod
    def _add_month(year: int, month: int) -> tuple[int, int]:
        if month == 12:
            return year + 1, 1
        return year, month + 1

    @staticmethod
    def compute_next_run(
        *,
        frequency: str,
        run_hour: int,
        run_day: int | None,
        after: datetime,
    ) -> datetime:
        after_utc = JobSchedulerService._utc(after)
        if not 0 <= run_hour <= 23:
            raise ValueError(f"Invalid run_hour: {run_hour}")

        if frequency == "daily":
            candidate = JobSchedulerService._build_datetime(
                after_utc.year, after_utc.month, after_utc.day, run_hour
            )
            if candidate <= after_utc:
                candidate += timedelta(days=1)
            return candidate

        if frequency == "weekly":
            if run_day is None or not 0 <= run_day <= 6:
                raise ValueError(f"Invalid weekly run_day: {run_day}")
            days_ahead = (run_day - after_utc.weekday()) % 7
            candidate_date = after_utc.date() + timedelta(days=days_ahead)
            candidate = JobSchedulerService._build_datetime(
                candidate_date.year, candidate_date.month, candidate_date.day, run_hour
            )
            if candidate <= after_utc:
                candidate += timedelta(days=7)
            return candidate

        if frequency == "monthly":
            if run_day is None or run_day < 1:
                raise ValueError(f"Invalid monthly run_day: {run_day}")

            year = after_utc.year
            month = after_utc.month
            while True:
                day = min(run_day, monthrange(year, month)[1])
                candidate = JobSchedulerService._build_datetime(year, month, day, run_hour)
                if candidate > after_utc:
                    return candidate
                year, month = JobSchedulerService._add_month(year, month)

        raise ValueError(f"Unsupported frequency: {frequency}")

    @staticmethod
    def is_due(*, next_run_at: datetime | None, now: datetime) -> bool:
        if next_run_at is None:
            return False
        return JobSchedulerService._utc(next_run_at) <= JobSchedulerService._utc(now)

    @staticmethod
    def next_status(
        current_status: str,
        *,
        success: bool,
        attempt_count: int,
        max_attempts: int,
    ) -> str:
        if current_status in {"succeeded", "dead"}:
            raise ValueError("Cannot transition a terminal job execution status")
        if success:
            return "succeeded"
        if attempt_count >= max_attempts:
            return "dead"
        return "failed_retry"

    @staticmethod
    def order_queue(executions: list[Any]) -> list[Any]:
        def key(item: Any) -> tuple[Any, Any, Any]:
            scheduled_for = getattr(item, "scheduled_for", None)
            created_at = getattr(item, "created_at", None)
            return (
                getattr(item, "priority", 100),
                JobSchedulerService._utc(scheduled_for) if scheduled_for is not None else datetime.max.replace(tzinfo=UTC),
                JobSchedulerService._utc(created_at) if created_at is not None else datetime.max.replace(tzinfo=UTC),
            )

        return sorted(executions, key=key)

    @staticmethod
    def can_claim(job_type_running_count: int) -> bool:
        return job_type_running_count == 0
