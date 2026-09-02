"""月次残高・予実比較・帳簿検算が、仕訳の取消と転記に追随すること。

月次残高（`monthly_balances`）は転記時に**加算だけ**する集計キャッシュだった。
取消（void）しても減算されないので、同じ画面の「試算表」タブ（仕訳から直接集計、
PR #52 で取消・削除・期間外を除外済み）と「月次残高」タブの数字が食い違う。
予実比較の実績も同じキャッシュを読んでいた。

さらに、そのキャッシュを検算するはずの `POST /audit/ledger-check` は
`approval_status == "approved"` の仕訳を期待値にしていたが、キャッシュは
**転記（"posted"）**の時に書かれる。転記した瞬間に期待値から外れ、キャッシュにだけ
残るので、転記済み仕訳がある会社では**常に drift を報告していた**。
常に赤い検算は誰も見ない。

直し方はキャッシュを直すことではなく、キャッシュを消すこと。試算表と同じく
仕訳から直接集計すれば、同期すべき第二の真実が無くなる。
"""
from datetime import date
from decimal import Decimal

import pytest

from tests.test_journal_lifecycle_db import (  # noqa: F401 -- fixtures
    _auth,
    _create,
    _submit,
    api,
    approver,
    books,
)

pytestmark = [pytest.mark.db, pytest.mark.asyncio]

AMOUNT = "110000"


async def _post_one(api, books, approver):
    """作成 → 提出 → 承認 → 転記まで進めた仕訳のIDを返す。"""
    created = (await _create(api, books, amount=AMOUNT)).json()
    jid = created["journal_header_id"]
    assert (await _submit(api, books, jid)).status_code == 200
    assert (await api.put(f"/api/v1/journals/{jid}/approve", headers=approver)).status_code == 200
    posted = await api.put(f"/api/v1/journals/{jid}/post", headers=approver)
    assert posted.status_code == 200, posted.text
    return jid


async def _monthly_cash(api, books):
    res = await api.get(
        "/api/v1/reports/monthly-balances",
        params={"company_id": str(books["company_id"]), "year": 2026, "month": 6},
        headers=_auth(books),
    )
    assert res.status_code == 200, res.text
    rows = {r["account_code"]: r for r in res.json()["items"]}
    return rows.get("1000"), res.json()


async def _trial_cash(api, books):
    res = await api.get(
        "/api/v1/reports/trial-balance",
        params={"company_id": str(books["company_id"]), "as_of": date(2026, 6, 30).isoformat()},
        headers=_auth(books),
    )
    assert res.status_code == 200, res.text
    return {r["account_code"]: r for r in res.json()["accounts"]}["1000"]


async def _ledger_check(api, books):
    res = await api.post(
        "/api/v1/audit/ledger-check",
        json={"company_id": str(books["company_id"]), "target_date": date(2026, 6, 30).isoformat()},
        headers=_auth(books),
    )
    assert res.status_code == 200, res.text
    return res.json()


async def test_a_posted_journal_appears_in_the_monthly_balance(api, books, approver):
    await _post_one(api, books, approver)

    cash, _ = await _monthly_cash(api, books)

    assert cash is not None, "転記した仕訳が月次残高に載っていない"
    assert Decimal(cash["debit_total"]) == Decimal(AMOUNT)


async def test_a_voided_journal_leaves_the_monthly_balance(api, books, approver):
    """取り消した仕訳の金額が月次残高に残らないこと。

    加算だけのキャッシュでは 110,000 が残り続けていた。
    """
    jid = await _post_one(api, books, approver)
    assert (await api.put(f"/api/v1/journals/{jid}/void", headers=_auth(books))).status_code == 200

    cash, body = await _monthly_cash(api, books)

    assert cash is None or Decimal(cash["debit_total"]) == Decimal("0"), (
        f"取消済みの仕訳が月次残高に残っている: {body}"
    )


async def test_the_monthly_balance_agrees_with_the_trial_balance(api, books, approver):
    """同じ画面の「月次残高」タブと「試算表」タブが同じ数字を出すこと。

    片方は仕訳から集計し、片方はキャッシュを読んでいたので、取消後に食い違っていた。
    """
    kept = await _post_one(api, books, approver)
    voided = await _post_one(api, books, approver)
    assert kept != voided
    assert (await api.put(f"/api/v1/journals/{voided}/void", headers=_auth(books))).status_code == 200

    monthly, _ = await _monthly_cash(api, books)
    trial = await _trial_cash(api, books)

    assert monthly is not None
    assert Decimal(monthly["debit_total"]) == Decimal(trial["debit_total"]) == Decimal(AMOUNT)


async def test_an_unposted_journal_counts_the_same_way_in_both_tabs(api, books, approver):
    """未転記（draft）の仕訳も、試算表と月次残高で扱いが揃っていること。

    試算表は承認状態で絞らない（登録した仕訳は全て載る。freee 等と同じ判断）。
    キャッシュは転記時にしか書かれなかったので、draft は月次残高にだけ載らなかった。
    """
    assert (await _create(api, books, amount=AMOUNT)).status_code == 201

    monthly, _ = await _monthly_cash(api, books)
    trial = await _trial_cash(api, books)

    assert Decimal(trial["debit_total"]) == Decimal(AMOUNT)
    assert monthly is not None and Decimal(monthly["debit_total"]) == Decimal(AMOUNT), (
        "未転記の仕訳が試算表には載るのに月次残高には載らない"
    )


async def test_the_budget_variance_ignores_voided_journals(api, books, approver):
    """予実比較の実績も取消を反映すること。"""
    kept = await _post_one(api, books, approver)
    voided = await _post_one(api, books, approver)
    assert kept != voided
    assert (await api.put(f"/api/v1/journals/{voided}/void", headers=_auth(books))).status_code == 200
    budget = await api.post(
        "/api/v1/budgets",
        json={
            "company_id": str(books["company_id"]),
            "fiscal_year": 2026,
            "name": "本予算",
            "lines": [
                {"account_id": str(books["sales"].account_id), "month": 6, "budgeted_amount": "200000"}
            ],
        },
        headers=_auth(books),
    )
    assert budget.status_code == 201, budget.text

    res = await api.get(f"/api/v1/budgets/{budget.json()['budget_id']}/variance", headers=_auth(books))

    assert res.status_code == 200, res.text
    sales = {line["account_code"]: line for line in res.json()["lines"]}["4000"]
    assert Decimal(sales["actual_amount"]) == Decimal(AMOUNT), (
        f"取消済みの仕訳が予実比較の実績に残っている: {sales}"
    )


async def test_the_ledger_check_is_green_after_posting(api, books, approver):
    """転記しただけで帳簿検算が赤くならないこと。

    期待値を「承認済み」で集め、キャッシュは「転記済み」で書いていたので、
    転記した瞬間に必ず drift になっていた。
    """
    await _post_one(api, books, approver)

    body = await _ledger_check(api, books)

    assert body["status"] == "ok", body
    assert body["balance_check"]["headers_checked"] == 1
    assert body["balance_check"]["imbalanced_count"] == 0


async def test_the_ledger_check_skips_voided_journals(api, books, approver):
    jid = await _post_one(api, books, approver)
    assert (await api.put(f"/api/v1/journals/{jid}/void", headers=_auth(books))).status_code == 200

    body = await _ledger_check(api, books)

    assert body["status"] == "ok", body
    assert body["balance_check"]["headers_checked"] == 0


async def test_the_ledger_check_covers_unposted_journals(api, books):
    """貸借一致は状態に依らない不変条件なので、draft も検査対象に入ること。"""
    assert (await _create(api, books, amount=AMOUNT)).status_code == 201

    body = await _ledger_check(api, books)

    assert body["balance_check"]["headers_checked"] == 1
