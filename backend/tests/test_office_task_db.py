import pytest

from app.services import office_task

pytestmark = pytest.mark.db


async def test_generate_is_idempotent_per_period(db_session, seed_company):
    tid, cid = seed_company["tenant_id"], seed_company["company_id"]
    created = await office_task.generate_from_templates(db_session, tid, cid, 2026, 7)
    assert len(created) == len(office_task.DEFAULT_MONTHLY_CLOSE_TEMPLATES)
    again = await office_task.generate_from_templates(db_session, tid, cid, 2026, 7)
    assert again == []  # no duplicates


async def test_status_and_progress(db_session, seed_company):
    tid, cid = seed_company["tenant_id"], seed_company["company_id"]
    tasks = await office_task.generate_from_templates(db_session, tid, cid, 2026, 8)
    await office_task.update_status(db_session, cid, tasks[0].office_task_id, "done")
    progress = await office_task.get_progress(db_session, cid, "2026-08")
    assert progress["total"] == len(tasks)
    assert progress["done"] == 1
    assert 0 < progress["completion_rate"] < 1
