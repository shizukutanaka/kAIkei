from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.models.models import Company, JobExecution, ScheduledJob, Tenant
from app.services import job_dispatch

pytestmark = pytest.mark.db


async def _make_due_job(db, company_id, job_type="monthly_close"):
    past = datetime.now(UTC) - timedelta(hours=1)
    job = ScheduledJob(
        company_id=company_id,
        job_type=job_type,
        frequency="monthly",
        run_hour=2,
        run_day=1,
        priority=100,
        next_run_at=past,
        is_active=True,
    )
    db.add(job)
    await db.flush()
    return job


async def _pending_count(db, company_id):
    result = await db.execute(
        select(func.count()).select_from(JobExecution).where(JobExecution.company_id == company_id)
    )
    return result.scalar() or 0


async def test_dispatch_creates_pending_execution_and_advances_next_run(db_session, seed_company):
    cid = seed_company["company_id"]
    job = await _make_due_job(db_session, cid)
    old_next = job.next_run_at

    created = await job_dispatch.dispatch_due_jobs(db_session, company_id=cid)
    assert len(created) == 1
    assert created[0].status == "pending"
    assert created[0].company_id == cid
    # 次回実行時刻が未来へ進み、再ディスパッチされない
    await db_session.refresh(job)
    assert job.next_run_at > old_next
    assert job.last_run_at is not None

    # 2回目は due でない（next_run_at が未来）ので何も作られない
    again = await job_dispatch.dispatch_due_jobs(db_session, company_id=cid)
    assert again == []


async def test_dispatch_skips_when_execution_already_running(db_session, seed_company):
    cid = seed_company["company_id"]
    job = await _make_due_job(db_session, cid)
    db_session.add(
        JobExecution(
            scheduled_job_id=job.scheduled_job_id,
            company_id=cid,
            job_type=job.job_type,
            status="running",
            priority=100,
        )
    )
    await db_session.flush()

    created = await job_dispatch.dispatch_due_jobs(db_session, company_id=cid)
    assert created == []  # can_claim=False のため多重ディスパッチされない


async def test_dispatch_all_companies_when_company_id_none(db_session, seed_company):
    cid = seed_company["company_id"]
    tid = seed_company["tenant_id"]
    await _make_due_job(db_session, cid)

    # 別テナント・別会社の due ジョブ
    other_tenant = Tenant(tenant_name="Other", tenant_code="OTHER-JOB")
    db_session.add(other_tenant)
    await db_session.flush()
    other_company = Company(tenant_id=other_tenant.tenant_id, company_name="Other Co", company_code="OJ1")
    db_session.add(other_company)
    await db_session.flush()
    await _make_due_job(db_session, other_company.company_id, job_type="depreciation")

    created = await job_dispatch.dispatch_due_jobs(db_session, company_id=None)
    dispatched_companies = {e.company_id for e in created}
    assert cid in dispatched_companies
    assert other_company.company_id in dispatched_companies
    assert await _pending_count(db_session, cid) == 1
    assert await _pending_count(db_session, other_company.company_id) == 1


async def test_dispatch_ignores_inactive_and_future_jobs(db_session, seed_company):
    cid = seed_company["company_id"]
    # inactive due job
    inactive = await _make_due_job(db_session, cid, job_type="inactive_one")
    inactive.is_active = False
    # future job (not due)
    future = await _make_due_job(db_session, cid, job_type="future_one")
    future.next_run_at = datetime.now(UTC) + timedelta(days=1)
    await db_session.flush()

    created = await job_dispatch.dispatch_due_jobs(db_session, company_id=cid)
    assert created == []
