"""請求書番号は会社ごとに一意であること（全社で一意ではない）。

アプリ側の重複チェックは `company_id` と `invoice_number` の組で見ていたが、
DBの制約は **`invoice_number` 単独の UNIQUE** だった。つまり:

- A社が「INV-001」を登録する → 成功
- B社が「INV-001」を登録する → アプリのチェックは通る（会社が違う）が、
  DB制約で弾かれ、IntegrityError が捕捉されずに **500** になる

請求書番号は各社が 001 から採番するのが普通なので、2社目以降は
ありふれた番号を一切使えない。番号の衝突は他社の存在を漏らしてもいる。

DBの制約をアプリの意図（会社ごとに一意）に合わせる。
"""
import uuid
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.exc import IntegrityError

from app.models.models import Company, Invoice, Tenant, User

pytestmark = [pytest.mark.db, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def two_companies(db_session):
    """別テナントの2社。番号の衝突はテナントをまたいでも起きてはならない。"""
    made = []
    for label in ("A", "B"):
        tenant = Tenant(tenant_name=f"{label}社G", tenant_code=f"{label}-{uuid.uuid4().hex[:6]}")
        db_session.add(tenant)
        await db_session.flush()
        company = Company(
            tenant_id=tenant.tenant_id,
            company_name=f"{label}社",
            company_code=f"{label}-{uuid.uuid4().hex[:6]}",
        )
        db_session.add(company)
        await db_session.flush()
        made.append(company)
    return made


def _invoice(company_id, number):
    return Invoice(
        company_id=company_id,
        invoice_number=number,
        invoice_date=date(2026, 6, 1),
        due_date=date(2026, 6, 30),
        subtotal=Decimal("100"),
        tax_amount=Decimal("10"),
        total_amount=Decimal("110"),
    )


async def test_two_companies_can_use_the_same_invoice_number(db_session, two_companies):
    """各社が自分の採番体系を使えること。

    以前は `invoice_number` 単独の UNIQUE 制約だったため、2社目の
    「INV-001」が DB で弾かれ 500 になっていた。
    """
    a, b = two_companies
    number = f"INV-{uuid.uuid4().hex[:4]}"

    db_session.add(_invoice(a.company_id, number))
    await db_session.flush()
    db_session.add(_invoice(b.company_id, number))

    await db_session.flush()  # ここで落ちるなら制約が会社ごとになっていない


async def test_the_same_company_cannot_reuse_a_number(db_session, two_companies):
    """会社の中では重複を許さないこと（制約を外しただけになっていないか）。"""
    a, _ = two_companies
    number = f"INV-{uuid.uuid4().hex[:4]}"

    db_session.add(_invoice(a.company_id, number))
    await db_session.flush()
    db_session.add(_invoice(a.company_id, number))

    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest_asyncio.fixture
async def api(api_client):
    return api_client


async def _token_for(db_session, company):
    from app.core.security import create_access_token

    user = User(
        tenant_id=company.tenant_id,
        email=f"inv-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="x",
        display_name="経理",
        role="admin",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    return {"Authorization": f"Bearer {create_access_token(str(user.user_id))}"}


async def test_the_api_lets_both_companies_use_the_same_number(api, db_session, two_companies):
    """HTTP 経路でも 2 社目が同じ番号を登録できること。

    これが実際の壊れ方だった。アプリの重複チェックは会社ごとに見ていたので
    通過し、その直後に DB 制約で IntegrityError になり、捕捉されないまま 500。
    利用者には「なぜか登録できない」としか見えない。
    """
    a, b = two_companies
    number = f"INV-{uuid.uuid4().hex[:4]}"

    codes = []
    for company in (a, b):
        headers = await _token_for(db_session, company)
        res = await api.post(
            "/api/v1/invoices/invoices",
            json={
                "company_id": str(company.company_id),
                "invoice_number": number,
                "invoice_date": "2026-06-01",
                "due_date": "2026-06-30",
                "tax_rate": "10.00",
                "lines": [
                    {"description": "商品", "quantity": "1", "unit_price": "1000"}
                ],
            },
            headers=headers,
        )
        codes.append((company.company_name, res.status_code, res.text[:200]))

    assert all(code == 201 for _, code, _ in codes), codes


async def test_the_api_rejects_a_duplicate_within_one_company(api, db_session, two_companies):
    """同じ会社での重複は 409。制約を外しただけになっていないこと。"""
    a, _ = two_companies
    headers = await _token_for(db_session, a)
    number = f"INV-{uuid.uuid4().hex[:4]}"
    body = {
        "company_id": str(a.company_id),
        "invoice_number": number,
        "invoice_date": "2026-06-01",
        "due_date": "2026-06-30",
        "tax_rate": "10.00",
        "lines": [{"description": "商品", "quantity": "1", "unit_price": "1000"}],
    }
    first = await api.post("/api/v1/invoices/invoices", json=body, headers=headers)
    assert first.status_code == 201, first.text

    again = await api.post("/api/v1/invoices/invoices", json=body, headers=headers)

    assert again.status_code == 409, again.text
