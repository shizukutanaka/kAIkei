from datetime import date

from app.services.office_task import (
    DEFAULT_MONTHLY_CLOSE_TEMPLATES,
    TaskTemplate,
    compute_due_date,
    generate_monthly_tasks,
    period_label,
    progress_summary,
)


class TestComputeDueDate:
    def test_normal_day(self):
        assert compute_due_date(2026, 7, 10) == date(2026, 7, 10)

    def test_clamps_to_month_end(self):
        # 2月は28日まで（2026は平年）
        assert compute_due_date(2026, 2, 31) == date(2026, 2, 28)

    def test_leap_year_february(self):
        assert compute_due_date(2028, 2, 31) == date(2028, 2, 29)

    def test_min_day_one(self):
        assert compute_due_date(2026, 7, 0) == date(2026, 7, 1)


class TestPeriodLabel:
    def test_zero_padded(self):
        assert period_label(2026, 7) == "2026-07"
        assert period_label(2026, 12) == "2026-12"


class TestGenerateMonthlyTasks:
    def test_generates_one_per_template(self):
        tasks = generate_monthly_tasks(DEFAULT_MONTHLY_CLOSE_TEMPLATES, 2026, 7)
        assert len(tasks) == len(DEFAULT_MONTHLY_CLOSE_TEMPLATES)
        assert all(t["period"] == "2026-07" for t in tasks)
        assert all(t["status"] == "todo" for t in tasks)

    def test_due_dates_within_month(self):
        tasks = generate_monthly_tasks(DEFAULT_MONTHLY_CLOSE_TEMPLATES, 2026, 7)
        assert all(t["due_date"].month == 7 for t in tasks)

    def test_custom_templates_clamp(self):
        templates = [TaskTemplate("月末処理", "monthly_close", 31)]
        tasks = generate_monthly_tasks(templates, 2026, 2)
        assert tasks[0]["due_date"] == date(2026, 2, 28)


class TestProgressSummary:
    def test_empty(self):
        s = progress_summary([])
        assert s["total"] == 0
        assert s["completion_rate"] == 0.0

    def test_counts_and_rate(self):
        s = progress_summary(["done", "done", "in_progress", "todo"])
        assert s["total"] == 4
        assert s["done"] == 2
        assert s["in_progress"] == 1
        assert s["todo"] == 1
        assert s["completion_rate"] == 0.5

    def test_all_done(self):
        s = progress_summary(["done", "done"])
        assert s["completion_rate"] == 1.0
