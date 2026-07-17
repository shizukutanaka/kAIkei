"""定期バックグラウンドジョブ（Webhook配信の自動処理）。

外部スケジューラへの依存を避け、asyncioタスクで一定間隔ごとにジョブを起動する。
判定・送信ロジックは既存サービス関数（webhook_service.process_due_deliveries）を
再利用し、このモジュールは間隔実行・例外隔離・起動停止のみを担う。
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PeriodicJob:
    """一定間隔で実行するジョブの定義。"""

    name: str
    interval_seconds: float
    func: Callable[[], Awaitable[None]]

    def __post_init__(self) -> None:
        if self.interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")


async def run_job_forever(job: PeriodicJob) -> None:
    """ジョブを間隔実行する。例外はログに記録して次回実行を継続する。"""
    while True:
        try:
            await job.func()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("Background job %s failed: %s", job.name, e)
        await asyncio.sleep(job.interval_seconds)


async def _process_webhook_deliveries() -> None:
    from app.core.database import async_session_factory
    from app.services.webhook_service import process_due_deliveries

    async with async_session_factory() as session:
        processed = await process_due_deliveries(session)
        await session.commit()
    if processed:
        logger.info("Webhook worker processed %d due deliveries", processed)


def build_default_jobs() -> list[PeriodicJob]:
    """設定に基づき既定のジョブ一覧を組み立てる。"""
    from app.core.config import settings

    return [
        PeriodicJob(
            name="webhook_delivery_worker",
            interval_seconds=settings.WEBHOOK_WORKER_INTERVAL_SECONDS,
            func=_process_webhook_deliveries,
        ),
    ]


def start_background_jobs(jobs: list[PeriodicJob] | None = None) -> list[asyncio.Task]:
    """ジョブをasyncioタスクとして起動し、停止用にタスク一覧を返す。"""
    tasks: list[asyncio.Task] = []
    for job in jobs if jobs is not None else build_default_jobs():
        tasks.append(asyncio.create_task(run_job_forever(job), name=job.name))
        logger.info("Started background job %s (every %.0fs)", job.name, job.interval_seconds)
    return tasks


async def stop_background_jobs(tasks: list[asyncio.Task]) -> None:
    """起動済みジョブをキャンセルし、終了を待つ。"""
    for task in tasks:
        task.cancel()
    for task in tasks:
        try:
            await task
        except asyncio.CancelledError:
            pass
