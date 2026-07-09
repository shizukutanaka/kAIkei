"""税務調整（別表四）エンジン（フェーズ6）。

会計上の当期純利益に対し、加算（損金不算入等）・減算（益金不算入等）の税務調整を
適用して課税所得を計算する。交際費限度超過のような「限度超過額」計算にも対応する。

調整額計算・課税所得算定の中核はDB非依存の純粋関数として切り出し、単体テスト可能。
"""
import logging
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import TaxAdjustmentRule

logger = logging.getLogger(__name__)

ADJUSTMENT_TYPES = {"addition", "subtraction"}
CALCULATION_METHODS = {"fixed", "rate", "excess_over_limit"}


# --- 純粋関数（DB非依存・テスト可能） ---------------------------------------

@dataclass
class AdjustmentRuleSpec:
    """調整ルールの計算仕様。"""
    rule_id: str
    name: str
    adjustment_type: str        # addition | subtraction
    calculation_method: str     # fixed | rate | excess_over_limit
    rate: Decimal | None = None
    limit_amount: Decimal | None = None
    fixed_amount: Decimal | None = None


@dataclass
class AdjustmentResult:
    """1ルールの調整結果。"""
    rule_id: str
    name: str
    adjustment_type: str
    amount: Decimal


def compute_adjustment_amount(spec: AdjustmentRuleSpec, base_amount: Decimal = Decimal("0")) -> Decimal:
    """ルール仕様と入力額から調整額（円・非負）を計算する。

    - fixed: 固定額（fixed_amount）
    - rate: base_amount × rate を円未満切捨て
    - excess_over_limit: max(0, base_amount − limit_amount)（限度超過額）
    """
    base_amount = Decimal(base_amount or 0)
    if spec.calculation_method == "fixed":
        amount = Decimal(spec.fixed_amount or 0)
    elif spec.calculation_method == "rate":
        rate = Decimal(spec.rate or 0)
        amount = (base_amount * rate).quantize(Decimal("1"), rounding=ROUND_DOWN)
    elif spec.calculation_method == "excess_over_limit":
        limit = Decimal(spec.limit_amount or 0)
        amount = base_amount - limit
    else:
        raise ValueError(f"Unknown calculation_method: {spec.calculation_method}")
    # 調整額は非負に丸める（限度内なら調整なし）。
    return amount if amount > 0 else Decimal("0")


def compute_taxable_income(
    accounting_income: Decimal, results: list[AdjustmentResult]
) -> Decimal:
    """会計上利益に加算・減算を適用して課税所得を計算する。"""
    additions = sum(
        (r.amount for r in results if r.adjustment_type == "addition"), Decimal("0")
    )
    subtractions = sum(
        (r.amount for r in results if r.adjustment_type == "subtraction"), Decimal("0")
    )
    return Decimal(accounting_income) + additions - subtractions


def build_result(spec: AdjustmentRuleSpec, base_amount: Decimal = Decimal("0")) -> AdjustmentResult:
    """ルール仕様から調整結果を組み立てる。"""
    return AdjustmentResult(
        rule_id=spec.rule_id,
        name=spec.name,
        adjustment_type=spec.adjustment_type,
        amount=compute_adjustment_amount(spec, base_amount),
    )


# --- 非同期サービス（DB依存） ------------------------------------------------

def _spec_from(rule: TaxAdjustmentRule) -> AdjustmentRuleSpec:
    return AdjustmentRuleSpec(
        rule_id=str(rule.tax_adjustment_rule_id),
        name=rule.name,
        adjustment_type=rule.adjustment_type,
        calculation_method=rule.calculation_method,
        rate=rule.rate,
        limit_amount=rule.limit_amount,
        fixed_amount=rule.fixed_amount,
    )


async def create_rule(
    db: AsyncSession,
    tenant_id: UUID,
    company_id: UUID,
    name: str,
    adjustment_type: str,
    calculation_method: str,
    rate: Decimal | None = None,
    limit_amount: Decimal | None = None,
    fixed_amount: Decimal | None = None,
    target_account_code: str | None = None,
) -> TaxAdjustmentRule:
    """税務調整ルールを作成する。"""
    if adjustment_type not in ADJUSTMENT_TYPES:
        raise ValueError(f"Invalid adjustment_type: {adjustment_type}")
    if calculation_method not in CALCULATION_METHODS:
        raise ValueError(f"Invalid calculation_method: {calculation_method}")
    rule = TaxAdjustmentRule(
        tenant_id=tenant_id,
        company_id=company_id,
        name=name,
        adjustment_type=adjustment_type,
        calculation_method=calculation_method,
        rate=rate,
        limit_amount=limit_amount,
        fixed_amount=fixed_amount,
        target_account_code=target_account_code,
        is_active=True,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return rule


async def list_rules(
    db: AsyncSession, company_id: UUID, active_only: bool = False
) -> list[TaxAdjustmentRule]:
    """税務調整ルールを一覧取得する。"""
    conditions = [TaxAdjustmentRule.company_id == company_id]
    if active_only:
        conditions.append(TaxAdjustmentRule.is_active == True)  # noqa: E712
    result = await db.execute(
        select(TaxAdjustmentRule).where(*conditions).order_by(TaxAdjustmentRule.created_at)
    )
    return list(result.scalars().all())


async def delete_rule(db: AsyncSession, company_id: UUID, rule_id: UUID) -> bool:
    """税務調整ルールを削除する。"""
    result = await db.execute(
        select(TaxAdjustmentRule).where(
            TaxAdjustmentRule.tax_adjustment_rule_id == rule_id,
            TaxAdjustmentRule.company_id == company_id,
        )
    )
    rule = result.scalar_one_or_none()
    if rule is None:
        return False
    await db.delete(rule)
    await db.commit()
    return True


async def compute_company_taxable_income(
    db: AsyncSession,
    company_id: UUID,
    accounting_income: Decimal,
    base_amounts: dict[str, Decimal] | None = None,
) -> dict:
    """会社の有効な調整ルールを適用して課税所得を計算する。

    Args:
        accounting_income: 会計上の当期純利益。
        base_amounts: ルールID→入力額（rate/excess_over_limit用）。未指定は0扱い。
    """
    base_amounts = base_amounts or {}
    rules = await list_rules(db, company_id, active_only=True)
    results: list[AdjustmentResult] = []
    for rule in rules:
        spec = _spec_from(rule)
        base = Decimal(base_amounts.get(spec.rule_id, 0))
        results.append(build_result(spec, base))

    taxable = compute_taxable_income(accounting_income, results)
    return {
        "accounting_income": accounting_income,
        "taxable_income": taxable,
        "total_additions": sum(
            (r.amount for r in results if r.adjustment_type == "addition"), Decimal("0")
        ),
        "total_subtractions": sum(
            (r.amount for r in results if r.adjustment_type == "subtraction"), Decimal("0")
        ),
        "adjustments": [
            {
                "rule_id": r.rule_id,
                "name": r.name,
                "adjustment_type": r.adjustment_type,
                "amount": r.amount,
            }
            for r in results
        ],
    }
