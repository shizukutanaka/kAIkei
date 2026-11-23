"""単体モードでの仕訳の自己承認（職務分掌の単体モード限定の緩和）の回帰テスト。

背景: 仕訳の承認は職務分掌のため作成者本人ではできなかった（SOD-001）。
多人数運用では正しいが、個人用単体モードでは利用者が1人しかおらず、
承認用の2人目アカウントを強いると「一人の仕訳作業が一息に終わる」と
いう単体モードの目的自体が成り立たない。そこで単体モードでのみ
SOD-001 を外し、自己承認→自己転記まで1アカウントで通るようにした。

ここで固定すること:
- 単体モード（DATABASE_URL が SQLite）: 作成者本人が承認・転記できる
- 通常モード（DATABASE_URL が PostgreSQL）: 従来どおり自己承認は
  SOD-001 で拒否され、他者の承認・転記は従来どおり通る
- 単体モードでも承認権限（RBAC）の確認は外れていない
  （緩和したのは職務分掌の確認だけ）

モード判定は設定の向き先で決まるため、データの置き場（このテストでは
実ファイルの SQLite）とは独立に、設定を差し替えて両モードを検証する。
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.models.models  # noqa: F401  -- 全テーブルを Base.metadata に登録する
from app.core.config import settings
from app.core.database import create_app_engine, is_standalone_mode
from app.models.models import Account, Company, JournalHeader, JournalLine, Tenant, User
from app.services.approval_service import ApprovalWorkflowService
from app.services.validation_engine import ValidationError
from app.standalone import init_schema_if_sqlite

POSTGRES_URL = "postgresql+asyncpg://kaikei:kaikei_dev@localhost:5432/kaikei"


def _sqlite_url(tmp_path) -> str:
    return f"sqlite+aiosqlite:///{tmp_path}/data/kaikei.db"


async def _make_factory(tmp_path):
    engine = create_app_engine(_sqlite_url(tmp_path))
    await init_schema_if_sqlite(engine)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, factory


async def _seed(factory, creator_role: str = "admin"):
    """テナント・会社・科目・利用者と、下書き仕訳を1件用意する。"""
    async with factory() as session:
        tenant = Tenant(tenant_name="単体", tenant_code="SOLO")
        session.add(tenant)
        await session.flush()

        company = Company(tenant_id=tenant.tenant_id, company_name="個人事業", company_code="SOLO1")
        session.add(company)
        await session.flush()

        accounts = {}
        for code, name, account_type in (
            ("1101", "普通預金", "asset"),
            ("5201", "通信費", "expense"),
        ):
            account = Account(
                company_id=company.company_id,
                account_code=code,
                account_name=name,
                account_type=account_type,
                debit_credit="debit" if account_type in ("asset", "expense") else "credit",
                is_active=True,
            )
            session.add(account)
            accounts[code] = account

        creator = User(
            tenant_id=tenant.tenant_id,
            email="solo@example.com",
            password_hash="x",
            display_name="本人",
            role=creator_role,
            is_active=True,
        )
        approver = User(
            tenant_id=tenant.tenant_id,
            email="approver@example.com",
            password_hash="x",
            display_name="承認者",
            role="approver",
            is_active=True,
        )
        session.add_all([creator, approver])
        await session.flush()

        journal = JournalHeader(
            company_id=company.company_id,
            journal_number="JRN-00000001",
            transaction_date=date(2026, 4, 15),
            summary="通信費 NTT",
            approval_status="draft",
            created_by=creator.user_id,
        )
        session.add(journal)
        await session.flush()
        for line_number, (side, code) in enumerate((("debit", "5201"), ("credit", "1101")), start=1):
            session.add(
                JournalLine(
                    journal_header_id=journal.journal_header_id,
                    line_number=line_number,
                    debit_credit=side,
                    account_id=accounts[code].account_id,
                    amount=Decimal("12800"),
                    description="通信費 NTT",
                )
            )
        await session.commit()
        return {
            "company_id": company.company_id,
            "creator_id": creator.user_id,
            "approver_id": approver.user_id,
            "journal_id": journal.journal_header_id,
        }


def test_is_standalone_mode_follows_database_url(monkeypatch):
    """モード判定は DATABASE_URL の向き先で決まる（新しい判定軸は無い）。"""
    monkeypatch.setattr(settings, "DATABASE_URL", "sqlite+aiosqlite:///./data/kaikei.db")
    assert is_standalone_mode() is True
    monkeypatch.setattr(settings, "DATABASE_URL", POSTGRES_URL)
    assert is_standalone_mode() is False


async def test_standalone_mode_allows_self_approval_and_posting(tmp_path, monkeypatch):
    """単体モード: 提出→本人の承認→本人の転記が1アカウントで通ること。"""
    monkeypatch.setattr(settings, "DATABASE_URL", _sqlite_url(tmp_path))
    engine, factory = await _make_factory(tmp_path)
    try:
        ids = await _seed(factory)
        async with factory() as db:
            journal = await ApprovalWorkflowService.submit_for_approval(db, ids["journal_id"], ids["creator_id"])
            assert journal.approval_status == "submitted"

            journal = await ApprovalWorkflowService.approve(db, ids["journal_id"], ids["creator_id"])
            assert journal.approval_status == "approved"
            assert journal.approved_by == ids["creator_id"]

            journal = await ApprovalWorkflowService.post(db, ids["journal_id"], ids["creator_id"])
            assert journal.approval_status == "posted"

            history = await ApprovalWorkflowService.get_approval_history(db, ids["journal_id"])
            assert [log.action for log in history] == ["submit", "approve", "post"]
            await db.commit()
    finally:
        await engine.dispose()


async def test_normal_mode_still_forbids_self_approval(tmp_path, monkeypatch):
    """通常モード: 自己承認は SOD-001 で拒否され、他者承認は従来どおり通ること。"""
    monkeypatch.setattr(settings, "DATABASE_URL", POSTGRES_URL)
    engine, factory = await _make_factory(tmp_path)
    try:
        ids = await _seed(factory)
        async with factory() as db:
            journal = await ApprovalWorkflowService.submit_for_approval(db, ids["journal_id"], ids["creator_id"])
            assert journal.approval_status == "submitted"

            with pytest.raises(ValidationError) as exc:
                await ApprovalWorkflowService.approve(db, ids["journal_id"], ids["creator_id"])
            assert exc.value.code == "SOD-001"

            # 拒否された仕訳は提出済みのまま（状態が進んでいない）
            journal = await ApprovalWorkflowService._get_journal(db, ids["journal_id"])
            assert journal.approval_status == "submitted"

            journal = await ApprovalWorkflowService.approve(db, ids["journal_id"], ids["approver_id"])
            assert journal.approval_status == "approved"
            assert journal.approved_by == ids["approver_id"]

            journal = await ApprovalWorkflowService.post(db, ids["journal_id"], ids["approver_id"])
            assert journal.approval_status == "posted"
            await db.commit()
    finally:
        await engine.dispose()


async def test_standalone_mode_still_enforces_approve_permission(tmp_path, monkeypatch):
    """単体モードでも承認権限の確認は効くこと（緩和したのは職務分掌だけ）。"""
    monkeypatch.setattr(settings, "DATABASE_URL", _sqlite_url(tmp_path))
    engine, factory = await _make_factory(tmp_path)
    try:
        ids = await _seed(factory, creator_role="accountant")
        async with factory() as db:
            await ApprovalWorkflowService.submit_for_approval(db, ids["journal_id"], ids["creator_id"])
            with pytest.raises(ValidationError) as exc:
                await ApprovalWorkflowService.approve(db, ids["journal_id"], ids["creator_id"])
            assert exc.value.code == "RBAC-001"
            await db.rollback()
    finally:
        await engine.dispose()
