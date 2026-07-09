"""承認ポリシー・ルーティングサービス（フェーズ1）。

文書種別と金額に応じて適用される承認ポリシーを解決し、必要な承認ステップ
（承認ロールの順序）を導出する。

ポリシー適合判定・ステップ導出の中核はDB非依存の純粋関数として切り出す。
"""
import logging
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import ApprovalPolicy

logger = logging.getLogger(__name__)


# --- 純粋関数（DB非依存・テスト可能） ---------------------------------------

@dataclass
class ApprovalPolicySpec:
    """承認ポリシーの適合仕様。"""
    policy_id: str
    document_type: str
    approver_role: str
    step_order: int
    min_amount: Decimal | None = None
    max_amount: Decimal | None = None


def policy_applies(spec: ApprovalPolicySpec, document_type: str, amount: Decimal) -> bool:
    """ポリシーが対象文書・金額に適用されるか判定する。

    金額範囲は下限以上・上限以下（上限は未指定なら無制限）。
    """
    if spec.document_type != document_type:
        return False
    amount = Decimal(amount)
    if spec.min_amount is not None and amount < Decimal(spec.min_amount):
        return False
    if spec.max_amount is not None and amount > Decimal(spec.max_amount):
        return False
    return True


def select_policies(
    specs: list[ApprovalPolicySpec], document_type: str, amount: Decimal
) -> list[ApprovalPolicySpec]:
    """適用されるポリシーをstep_order昇順で返す。"""
    applicable = [s for s in specs if policy_applies(s, document_type, amount)]
    return sorted(applicable, key=lambda s: s.step_order)


def required_approval_steps(
    specs: list[ApprovalPolicySpec], document_type: str, amount: Decimal
) -> list[str]:
    """必要な承認ステップ（承認ロール）をstep_order順で返す。

    同一step_orderの重複ロールは最初の1つに集約する。
    """
    steps: list[str] = []
    seen_orders: set[int] = set()
    for spec in select_policies(specs, document_type, amount):
        if spec.step_order in seen_orders:
            continue
        seen_orders.add(spec.step_order)
        steps.append(spec.approver_role)
    return steps


# --- 非同期サービス（DB依存） ------------------------------------------------

def _spec_from(policy: ApprovalPolicy) -> ApprovalPolicySpec:
    return ApprovalPolicySpec(
        policy_id=str(policy.approval_policy_id),
        document_type=policy.document_type,
        approver_role=policy.approver_role,
        step_order=policy.step_order,
        min_amount=policy.min_amount,
        max_amount=policy.max_amount,
    )


async def create_policy(
    db: AsyncSession,
    tenant_id: UUID,
    company_id: UUID,
    document_type: str,
    approver_role: str,
    step_order: int = 1,
    min_amount: Decimal | None = None,
    max_amount: Decimal | None = None,
) -> ApprovalPolicy:
    """承認ポリシーを作成する。"""
    policy = ApprovalPolicy(
        tenant_id=tenant_id,
        company_id=company_id,
        document_type=document_type,
        approver_role=approver_role,
        step_order=step_order,
        min_amount=min_amount,
        max_amount=max_amount,
        is_active=True,
    )
    db.add(policy)
    await db.commit()
    await db.refresh(policy)
    return policy


async def list_policies(
    db: AsyncSession, company_id: UUID, document_type: str | None = None, active_only: bool = False
) -> list[ApprovalPolicy]:
    """承認ポリシーを一覧取得する。"""
    conditions = [ApprovalPolicy.company_id == company_id]
    if document_type is not None:
        conditions.append(ApprovalPolicy.document_type == document_type)
    if active_only:
        conditions.append(ApprovalPolicy.is_active == True)  # noqa: E712
    result = await db.execute(
        select(ApprovalPolicy).where(*conditions).order_by(
            ApprovalPolicy.document_type, ApprovalPolicy.step_order
        )
    )
    return list(result.scalars().all())


async def delete_policy(db: AsyncSession, company_id: UUID, policy_id: UUID) -> bool:
    """承認ポリシーを削除する。"""
    result = await db.execute(
        select(ApprovalPolicy).where(
            ApprovalPolicy.approval_policy_id == policy_id,
            ApprovalPolicy.company_id == company_id,
        )
    )
    policy = result.scalar_one_or_none()
    if policy is None:
        return False
    await db.delete(policy)
    await db.commit()
    return True


async def resolve_required_steps(
    db: AsyncSession, company_id: UUID, document_type: str, amount: Decimal
) -> list[str]:
    """対象文書・金額に必要な承認ロール列を解決する。"""
    policies = await list_policies(db, company_id, document_type=document_type, active_only=True)
    specs = [_spec_from(p) for p in policies]
    return required_approval_steps(specs, document_type, amount)
