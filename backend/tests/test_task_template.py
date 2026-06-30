from datetime import date

import pytest

from app.services.task_template import (
    DAILY_TEMPLATES,
    MONTHLY_PHASE_CLOSING,
    MONTHLY_PHASE_OPENING,
    TaskTemplateService,
)


def test_generate_monthly_tasks_full_catalog():
    specs = TaskTemplateService.generate_monthly_tasks(target_year=2026, target_month=4)
    assert len(specs) == 6
    types = {s.task_type for s in specs}
    assert {"source_document_collection", "payroll_preparation", "monthly_close"} <= types


def test_monthly_close_due_date_is_last_day_of_month():
    # February in a non-leap year -> last day 28
    specs = TaskTemplateService.generate_monthly_tasks(target_year=2026, target_month=2)
    close = next(s for s in specs if s.task_type == "monthly_close")
    assert close.due_date == date(2026, 2, 28)


def test_monthly_close_due_date_clamped_for_30_day_month():
    specs = TaskTemplateService.generate_monthly_tasks(target_year=2026, target_month=4)
    close = next(s for s in specs if s.task_type == "monthly_close")
    assert close.due_date == date(2026, 4, 30)


def test_monthly_phase_filter():
    opening = TaskTemplateService.generate_monthly_tasks(
        target_year=2026, target_month=4, phase=MONTHLY_PHASE_OPENING
    )
    assert {s.task_type for s in opening} == {"source_document_collection", "payroll_preparation"}
    closing = TaskTemplateService.generate_monthly_tasks(
        target_year=2026, target_month=4, phase=MONTHLY_PHASE_CLOSING
    )
    assert all(s.due_date == date(2026, 4, 30) for s in closing)


def test_monthly_invalid_month_raises():
    with pytest.raises(ValueError):
        TaskTemplateService.generate_monthly_tasks(target_year=2026, target_month=13)


def test_monthly_invalid_phase_raises():
    with pytest.raises(ValueError):
        TaskTemplateService.generate_monthly_tasks(target_year=2026, target_month=4, phase="nope")


def test_generate_daily_tasks_due_today():
    target = date(2026, 6, 30)
    specs = TaskTemplateService.generate_daily_tasks(target_date=target)
    assert len(specs) == len(DAILY_TEMPLATES)
    assert all(s.due_date == target for s in specs)
    assert {s.task_type for s in specs} == {t[0] for t in DAILY_TEMPLATES}
