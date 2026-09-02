"""仕訳のCSV取り込みが実際に行を取り込むこと。

`POST /journals/import/csv` には専用のテストが無かった。全書き込み経路の疎通確認
（`test_write_endpoint_smoke_db.py`）は通っていたが、あれが見ているのは
「5xxにならないこと」だけで、**科目名が一致しなければ行は1件も取り込まれずに
200 が返る**。監査エクスポートのときと同じで、行を処理するコードに入らないまま
「確認済み」になっていた。

ここでは取り込んだ結果を確かめる: 件数・仕訳番号・貸借の明細・試算表への反映。
"""
import uuid
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio

from app.models.models import Account, Company, Tenant, User

pytestmark = [pytest.mark.db, pytest.mark.asyncio]

CSV = (
    "取引日,借方勘目,貸方勘目,摘要,金額\n"
    "2026-06-15,現金,売上,6月分売上,110000\n"
    "2026-06-20,現金,売上,追加売上,50000\n"
)


@pytest_asyncio.fixture
async def api(api_client):
    return api_client


@pytest_asyncio.fixture
async def books(db_session):
    from app.core.security import create_access_token

    tenant = Tenant(tenant_name="取込", tenant_code=f"IM-{uuid.uuid4().hex[:6]}")
    db_session.add(tenant)
    await db_session.flush()
    co = Company(
        tenant_id=tenant.tenant_id,
        company_name="取込商事",
        company_code=f"IM-{uuid.uuid4().hex[:6]}",
    )
    db_session.add(co)
    await db_session.flush()
    user = User(
        tenant_id=tenant.tenant_id,
        email=f"im-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="x",
        display_name="経理",
        role="admin",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add_all([
        Account(
            company_id=co.company_id,
            account_code="1000",
            account_name="現金",
            account_type="asset",
            debit_credit="debit",
        ),
        Account(
            company_id=co.company_id,
            account_code="4000",
            account_name="売上",
            account_type="revenue",
            debit_credit="credit",
        ),
    ])
    await db_session.flush()
    return {"company_id": co.company_id, "token": create_access_token(str(user.user_id))}


def _auth(books):
    return {"Authorization": f"Bearer {books['token']}"}


async def _import(api, books, content=CSV):
    return await api.post(
        "/api/v1/journals/import/csv",
        params={"company_id": str(books["company_id"])},
        files={"file": ("journals.csv", content.encode("utf-8"), "text/csv")},
        headers=_auth(books),
    )


async def test_rows_are_actually_imported(api, books):
    """行が取り込まれること。0件でも200が返るので、件数まで見る。"""
    res = await _import(api, books)

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["imported"] == 2, body
    assert body["errors"] == [], body


async def test_imported_journals_get_distinct_numbers(api, books):
    """取り込んだ仕訳に別々の番号が付くこと。

    採番を1箇所に集約した際、取り込みは1行ずつ採番するようになった。
    同じ番号が付くと監査で追えない。
    """
    assert (await _import(api, books)).status_code == 200

    listed = await api.get(
        "/api/v1/journals",
        params={"company_id": str(books["company_id"])},
        headers=_auth(books),
    )

    assert listed.status_code == 200, listed.text
    numbers = [item["journal_number"] for item in listed.json()["items"]]
    assert len(numbers) == 2
    assert len(set(numbers)) == 2, f"取り込んだ仕訳の番号が重複している: {numbers}"
    assert sorted(numbers) == ["JRN-00000001", "JRN-00000002"]


async def test_a_second_import_continues_the_sequence(api, books):
    """2回目の取り込みが1からやり直さないこと。"""
    assert (await _import(api, books)).status_code == 200
    second = await _import(api, books, content=(
        "取引日,借方勘目,貸方勘目,摘要,金額\n2026-06-25,現金,売上,3件目,7000\n"
    ))

    assert second.status_code == 200, second.text
    listed = await api.get(
        "/api/v1/journals",
        params={"company_id": str(books["company_id"])},
        headers=_auth(books),
    )
    numbers = sorted(item["journal_number"] for item in listed.json()["items"])

    assert numbers == ["JRN-00000001", "JRN-00000002", "JRN-00000003"], numbers


async def test_the_imported_entries_balance(api, books):
    """取り込んだ仕訳が貸借一致していること（借方1行・貸方1行）。"""
    assert (await _import(api, books)).status_code == 200

    listed = await api.get(
        "/api/v1/journals",
        params={"company_id": str(books["company_id"])},
        headers=_auth(books),
    )

    for item in listed.json()["items"]:
        debit = sum(Decimal(x["amount"]) for x in item["lines"] if x["debit_credit"] == "debit")
        credit = sum(Decimal(x["amount"]) for x in item["lines"] if x["debit_credit"] == "credit")
        assert debit == credit, f"{item['journal_number']} の貸借が一致しない"


async def test_the_imported_amounts_reach_the_trial_balance(api, books):
    """取り込んだ金額が試算表に出ること（登録できても集計に乗らなければ意味がない）。"""
    assert (await _import(api, books)).status_code == 200

    res = await api.get(
        "/api/v1/reports/trial-balance",
        params={"company_id": str(books["company_id"]), "as_of": date(2026, 6, 30).isoformat()},
        headers=_auth(books),
    )

    assert res.status_code == 200, res.text
    rows = {r["account_code"]: r for r in res.json()["accounts"]}
    assert Decimal(rows["1000"]["debit_total"]) == Decimal("160000")
    assert Decimal(rows["4000"]["credit_total"]) == Decimal("160000")


async def test_an_unknown_account_is_reported_not_silently_skipped(api, books):
    """存在しない科目名は行ごとにエラーとして返ること。"""
    res = await _import(api, books, content=(
        "取引日,借方勘目,貸方勘目,摘要,金額\n2026-06-15,無い科目,売上,誤り,1000\n"
    ))

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["imported"] == 0
    assert len(body["errors"]) == 1, body
    assert "無い科目" in body["errors"][0]
