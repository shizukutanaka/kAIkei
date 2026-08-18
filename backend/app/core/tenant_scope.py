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
