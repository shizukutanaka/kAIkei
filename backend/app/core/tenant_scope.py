"""テナント越境アクセス（IDOR）を防ぐための共通スコープ条件。

このシステムのデータ階層は Tenant > Company > 業務データ で、業務データは
`company_id` しか持たない。一方 JWT が運ぶのは `tenant_id` なので、
UUID を受け取るエンドポイントは「その company が本当に自分のテナントのものか」
を毎回照合しないと、ID を知っているだけで他社の帳簿を読み書きできてしまう。

会計データの越境は情報漏えいに留まらず、他社の仕訳を取り消すといった
帳簿の改竄になり得る。照合を各エンドポイントの書き方に委ねると必ず抜けが
出るため、条件をここに一本化する。

使い方::

    stmt = select(FixedAsset).where(FixedAsset.asset_id == asset_id)
    stmt = scope_to_tenant(stmt, FixedAsset, current_user.tenant_id)

越境時は 403 ではなく「見つからない」（0件）になる。存在有無を教えないため、
他テナントのIDを総当たりして実在を確かめる、という使い方を封じられる。
"""
from __future__ import annotations

from typing import TypeVar
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import Select, select

from app.models.models import Company

_S = TypeVar("_S", bound=Select)


def tenant_company_ids(tenant_id: UUID) -> Select:
    """当該テナントが保有する（削除されていない）会社IDのサブクエリ。"""
    return select(Company.company_id).where(
        Company.tenant_id == tenant_id,
        Company.is_deleted == False,  # noqa: E712
    )


def scope_to_tenant(stmt: _S, model: type, tenant_id: UUID) -> _S:
    """`model.company_id` が当該テナントの会社に属する行だけに絞り込む。

    `model` は `company_id` カラムを持つ必要がある。持たないモデルを渡すのは
    呼び出し側の誤りなので、静かに素通しせず AttributeError で落とす。
    """
    company_id = model.company_id  # noqa: B018  -- 属性が無ければここで落とす
    return stmt.where(company_id.in_(tenant_company_ids(tenant_id)))


def is_company_in_tenant(company_id: UUID, tenant_id: UUID) -> Select:
    """`company_id` が当該テナントのものか判定するための SELECT を返す。

    クエリパラメータで company_id を受け取るエンドポイント用。呼び出し側で
    実行し、0件なら 404 にする。
    """
    return select(Company.company_id).where(
        Company.company_id == company_id,
        Company.tenant_id == tenant_id,
        Company.is_deleted == False,  # noqa: E712
    )


async def assert_company_access(db, current_user, company_id: UUID) -> None:
    """`company_id` が呼び出し元テナントのものでなければ 404 を送出する。

    リクエストボディで company_id を受け取るエンドポイント用。
    クエリパラメータで受け取る場合は依存関係 `verified_company_id` を使う。

    403 ではなく 404 にするのは、他テナントの company_id を総当たりして
    実在を確かめられないようにするため。
    """
    found = await db.execute(is_company_in_tenant(company_id, current_user.tenant_id))
    if found.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Company not found")


async def assert_owns(db, current_user, model: type, pk_column, row_id: UUID, label: str) -> None:
    """`row_id` の行が呼び出し元テナントのものでなければ 404 を送出する。

    `company_id` を直接持たない子テーブル（承認履歴、補助科目など）は
    `scope_to_tenant` を掛けられない。そこで**親**を照合する。

        assert_owns(db, user, JournalHeader, JournalHeader.journal_header_id, jid, "Journal")

    ID をパスやリクエストボディで受け取る経路は、業務処理に入る**前**に
    これを通すこと。状態チェックを先に走らせると、他テナントの行に対して
    「その状態では実行できません」と返ってしまい、存在と状態を教えることになる。
    """
    stmt = scope_to_tenant(select(pk_column).where(pk_column == row_id), model, current_user.tenant_id)
    if (await db.execute(stmt)).scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail=f"{label} not found")
