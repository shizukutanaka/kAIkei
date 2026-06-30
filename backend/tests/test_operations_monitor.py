from app.services.operations_monitor import (
    LEVEL_CRITICAL,
    LEVEL_DEGRADED,
    LEVEL_HEALTHY,
    LEVEL_IDLE,
    OperationsMonitorService,
)


def test_empty_is_idle():
    summary = OperationsMonitorService.classify_statuses([])
    assert summary.level == LEVEL_IDLE
    assert summary.total == 0


def test_all_succeeded_is_healthy():
    summary = OperationsMonitorService.classify_statuses(["succeeded", "succeeded", "running", "pending"])
    assert summary.level == LEVEL_HEALTHY
    assert summary.failed == 0


def test_dead_forces_critical():
    summary = OperationsMonitorService.classify_statuses(["succeeded"] * 9 + ["dead"])
    assert summary.dead == 1
    assert summary.level == LEVEL_CRITICAL


def test_degraded_failure_rate():
    # 2 failed_retry of 8 = 0.25 -> degraded (>=0.2, <0.5, no dead)
    statuses = ["failed_retry", "failed_retry"] + ["succeeded"] * 6
    summary = OperationsMonitorService.classify_statuses(statuses)
    assert summary.failure_rate == 0.25
    assert summary.level == LEVEL_DEGRADED


def test_high_failure_rate_is_critical():
    statuses = ["failed_retry"] * 5 + ["succeeded"] * 5
    summary = OperationsMonitorService.classify_statuses(statuses)
    assert summary.level == LEVEL_CRITICAL


def test_overdue_task_levels():
    assert OperationsMonitorService.overdue_task_level(0) == LEVEL_HEALTHY
    assert OperationsMonitorService.overdue_task_level(3) == LEVEL_DEGRADED
    assert OperationsMonitorService.overdue_task_level(10) == LEVEL_CRITICAL


def test_aggregate_takes_worst():
    assert OperationsMonitorService.aggregate_levels([LEVEL_HEALTHY, LEVEL_DEGRADED, LEVEL_HEALTHY]) == LEVEL_DEGRADED
    assert OperationsMonitorService.aggregate_levels([LEVEL_HEALTHY, LEVEL_CRITICAL]) == LEVEL_CRITICAL
    assert OperationsMonitorService.aggregate_levels([]) == LEVEL_IDLE
