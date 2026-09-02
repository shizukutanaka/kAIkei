"""仕訳番号は会社ごとに一意で、同時に作っても重複しないこと。

採番の実装が2つあった。`POST /journals` は既存番号の **MAX** から次を作り、
自動仕訳（請求書・給与から起こす仕訳）は行数の **COUNT** から作る。どちらも
「読んでから書く」ので、同じ会社で同時に作ると**両方が同じ番号を読む**。
DBに一意制約が無いので、そのまま同じ番号の仕訳が2件できる。

実測（修正前）: 3つの接続から同時に登録すると、3件とも `JRN-00000001` になった。

仕訳番号は監査で仕訳を追う識別子で、重複すると追跡できない。しかも重複しても
エラーにならないので誰も気付かない。採番を1箇所に集約し、DBの一意制約に
守らせる（衝突したら採り直す）。
"""
import asyncio
import os
import uuid
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.models import Company, JournalHeader, Tenant, User
from app.services.journal_numbering import insert_with_number, next_journal_number

pytestmark = [pytest.mark.db, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def company(db_session):
    tenant = Tenant(tenant_name="採番", tenant_code=f"NB-{uuid.uuid4().hex[:6]}")
    db_session.add(tenant)
    await db_session.flush()
    co = Company(
        tenant_id=tenant.tenant_id,
        company_name="採番商事",
        company_code=f"NB-{uuid.uuid4().hex[:6]}",
    )
    db_session.add(co)
    await db_session.flush()
    user = User(
        tenant_id=tenant.tenant_id,
        email=f"nb-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="x",
        display_name="経理",
        role="admin",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    return co, user


def _header(company_id, user_id, number, summary="採番"):
    return JournalHeader(
        company_id=company_id,
        journal_number=number,
        transaction_date=date(2026, 6, 1),
        voucher_type="transfer",
        summary=summary,
        approval_status="draft",
        created_by=user_id,
    )


async def test_numbers_are_sequential(db_session, company):
    co, user = company

    first = await next_journal_number(db_session, co.company_id)
    db_session.add(_header(co.company_id, user.user_id, first))
    await db_session.flush()
    second = await next_journal_number(db_session, co.company_id)

    assert first == "JRN-00000001"
    assert second == "JRN-00000002"


async def test_a_number_from_another_scheme_does_not_shift_the_sequence(db_session, company):
    """取り込んだ仕訳が別体系の番号を持っていても連番が飛ばないこと。

    以前の MAX 方式は `F-12345` を `int("12345")` と読み、次の番号を
    `JRN-00012346` にしていた。COUNT 方式は `JRN-00000002` を返すので、
    2つの実装が同じ会社で別々の番号を振っていた。
    """
    co, user = company
    db_session.add(_header(co.company_id, user.user_id, "F-12345"))
    await db_session.flush()

    assert await next_journal_number(db_session, co.company_id) == "JRN-00000001"


async def test_the_same_number_cannot_be_stored_twice(db_session, company):
    """重複がDBで禁じられていること（重複しても気付けない状態を無くす）。"""
    co, user = company
    db_session.add(_header(co.company_id, user.user_id, "JRN-00000001"))
    await db_session.flush()
    db_session.add(_header(co.company_id, user.user_id, "JRN-00000001"))

    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_another_company_can_use_the_same_number(db_session, company):
    """番号は会社ごと。他社が同じ番号を使えること。"""
    co, user = company
    db_session.add(_header(co.company_id, user.user_id, "JRN-00000001"))
    await db_session.flush()

    other_tenant = Tenant(tenant_name="別", tenant_code=f"NB2-{uuid.uuid4().hex[:6]}")
    db_session.add(other_tenant)
    await db_session.flush()
    other = Company(
        tenant_id=other_tenant.tenant_id,
        company_name="別商事",
        company_code=f"NB2-{uuid.uuid4().hex[:6]}",
    )
    db_session.add(other)
    await db_session.flush()
    other_user = User(
        tenant_id=other_tenant.tenant_id,
        email=f"nb2-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="x",
        display_name="経理",
        role="admin",
        is_active=True,
    )
    db_session.add(other_user)
    await db_session.flush()
    db_session.add(_header(other.company_id, other_user.user_id, "JRN-00000001"))

    await db_session.flush()  # 落ちるなら制約が会社ごとになっていない


async def test_insert_with_number_retries_after_a_collision(db_session, company):
    """先に同じ番号が取られていたら、採り直して登録できること。"""
    co, user = company
    db_session.add(_header(co.company_id, user.user_id, "JRN-00000001"))
    await db_session.flush()

    header = await insert_with_number(
        db_session,
        co.company_id,
        lambda number: _header(co.company_id, user.user_id, number, summary="採り直し"),
    )

    assert header.journal_number == "JRN-00000002"


async def test_concurrent_creation_does_not_duplicate_a_number():
    """別々の接続から同時に作っても番号が重複しないこと。

    これが実際の壊れ方だった。修正前は3件とも `JRN-00000001` になる。

    `db_session` は未コミットの外側トランザクションなので、他の接続からは
    会社の行が見えない（外部キーの確認で待たされて固まる）。ここだけは
    自前の接続で作って確定させ、最後に消す。
    """
    engine = create_async_engine(os.environ["TEST_DATABASE_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as setup:
        tenant = Tenant(tenant_name="同時", tenant_code=f"NBC-{uuid.uuid4().hex[:6]}")
        setup.add(tenant)
        await setup.flush()
        co = Company(
            tenant_id=tenant.tenant_id,
            company_name="同時商事",
            company_code=f"NBC-{uuid.uuid4().hex[:6]}",
        )
        setup.add(co)
        await setup.flush()
        user = User(
            tenant_id=tenant.tenant_id,
            email=f"nbc-{uuid.uuid4().hex[:6]}@example.com",
            password_hash="x",
            display_name="経理",
            role="admin",
            is_active=True,
        )
        setup.add(user)
        await setup.flush()
        await setup.commit()
        company_id, user_id = co.company_id, user.user_id
        tenant_id = tenant.tenant_id

    async def create_one():
        async with factory() as session:
            await insert_with_number(
                session,
                company_id,
                lambda number: _header(company_id, user_id, number, summary="同時"),
            )
            await session.commit()

    try:
        await asyncio.gather(*(create_one() for _ in range(3)))

        async with factory() as session:
            rows = await session.execute(
                select(JournalHeader.journal_number).where(
                    JournalHeader.company_id == company_id
                )
            )
            numbers = [n for (n,) in rows.all()]
    finally:
        async with factory() as cleanup:
            await cleanup.execute(
                delete(JournalHeader).where(JournalHeader.company_id == company_id)
            )
            await cleanup.execute(delete(User).where(User.user_id == user_id))
            await cleanup.execute(delete(Company).where(Company.company_id == company_id))
            await cleanup.execute(delete(Tenant).where(Tenant.tenant_id == tenant_id))
            await cleanup.commit()
        await engine.dispose()

    assert len(numbers) == 3, f"同時登録で件数が合わない: {numbers}"
    assert len(set(numbers)) == 3, f"番号が重複している: {sorted(numbers)}"
