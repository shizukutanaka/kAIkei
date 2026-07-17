"""運用管理コンソールのヘルス集計（純粋ロジック）。

ジョブ実行・Webhook配信のステータス分布や滞留タスク件数から、システムの健全性
レベル（healthy / degraded / critical / idle）を決定論的に判定する。DB/I/Oには
依存せず、エンドポイント側が集計したカウントを受け取って評価する。
"""
from __future__ import annotations

from dataclasses import dataclass

LEVEL_IDLE = "idle"
LEVEL_HEALTHY = "healthy"
LEVEL_DEGRADED = "degraded"
LEVEL_CRITICAL = "critical"

# 深刻度の順序（大きいほど深刻）。集約時に最悪値を採用する。
_LEVEL_RANK = {
    LEVEL_IDLE: 0,
    LEVEL_HEALTHY: 1,
    LEVEL_DEGRADED: 2,
    LEVEL_CRITICAL: 3,
}

# しきい値（失敗率）。
_DEGRADED_FAILURE_RATE = 0.2
_CRITICAL_FAILURE_RATE = 0.5

# 失敗扱いとするステータス（再試行待ち＋打切り）。
_FAILED_STATUSES = frozenset({"failed_retry", "dead"})
_DEAD_STATUS = "dead"


@dataclass(frozen=True)
class HealthSummary:
    total: int
    failed: int
    dead: int
    failure_rate: float
    level: str


class OperationsMonitorService:
    """実行ステータス分布からヘルスレベルを判定する純粋サービス。"""

    @staticmethod
    def classify_statuses(statuses: list[str]) -> HealthSummary:
        total = len(statuses)
        if total == 0:
            return HealthSummary(total=0, failed=0, dead=0, failure_rate=0.0, level=LEVEL_IDLE)

        failed = sum(1 for s in statuses if s in _FAILED_STATUSES)
        dead = sum(1 for s in statuses if s == _DEAD_STATUS)
        failure_rate = failed / total

        if dead > 0 or failure_rate >= _CRITICAL_FAILURE_RATE:
            level = LEVEL_CRITICAL
        elif failure_rate >= _DEGRADED_FAILURE_RATE:
            level = LEVEL_DEGRADED
        else:
            level = LEVEL_HEALTHY

        return HealthSummary(
            total=total,
            failed=failed,
            dead=dead,
            failure_rate=round(failure_rate, 4),
            level=level,
        )

    @staticmethod
    def overdue_task_level(overdue_count: int) -> str:
        if overdue_count <= 0:
            return LEVEL_HEALTHY
        if overdue_count >= 10:
            return LEVEL_CRITICAL
        return LEVEL_DEGRADED

    @staticmethod
    def aggregate_levels(levels: list[str]) -> str:
        if not levels:
            return LEVEL_IDLE
        return max(levels, key=lambda level: _LEVEL_RANK[level])
