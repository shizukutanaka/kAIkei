"""給与に伴う納付事務タスク(納付先・納期限・金額)の自動生成。

納付仕訳(slice 80)を作っても、担当者が納期限を暦で数えて振込・納付タスクを登録する工程が残る。
納期限は法定なので機械化でき、次の2点が手計算で最も間違いやすい。

    1. 期限が日曜・祝日等に当たる場合は**翌開庁日**が期限になる(国税通則法10条2項)
       例: 2025年7月給与の源泉所得税は法定8/10だが日曜なので8/11、社会保険料は8/31(日)→9/1
    2. 12/29〜1/3 は休日扱いのため年末の期限は翌年1月最初の開庁日へ動く
       例: 2025年11月分の社会保険料は12/31 → 2026/1/5(1/4は日曜)

さらに源泉所得税は納期の特例(所得税法216条・給与支給人員10人未満)を選択すると毎月納付ではなく
半年分をまとめて納付する(1〜6月分=7/10、7〜12月分=翌年1/20)ため、納付回数と期限が変わる。

祝日は年により変動し法改正で増減するため、固定テーブルを埋め込まず `holidays` で受け取る
(土日と12/29〜1/3は暦から判定できるので内蔵)。金額0の納付はタスクを作らない。
"""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

PAYEE_TAX_OFFICE = "税務署"
PAYEE_MUNICIPALITY = "市区町村"
PAYEE_SOCIAL_INSURANCE = "年金事務所・健康保険組合"

TASK_WITHHOLDING_TAX = "withholding_tax_payment"
TASK_RESIDENCE_TAX = "residence_tax_payment"
TASK_SOCIAL_INSURANCE = "social_insurance_payment"

_ZERO = Decimal("0")


@dataclass(frozen=True)
class PaymentTaskInput:
    payroll_year: int
    payroll_month: int
    income_tax: Decimal = _ZERO
    residence_tax: Decimal = _ZERO
    social_insurance_total: Decimal = _ZERO
    withholding_special_exception: bool = False
    holidays: list[date] | None = None


@dataclass(frozen=True)
class PaymentTask:
    task_type: str
    title: str
    payee: str
    amount: Decimal
    statutory_due_date: date
    due_date: date
    shifted: bool
    legal_basis: str


@dataclass(frozen=True)
class PaymentTaskResult:
    payroll_year: int
    payroll_month: int
    tasks: list[PaymentTask]
    total_amount: Decimal
    earliest_due_date: date | None


class PaymentTaskService:
    """納付事務タスクを生成する純粋サービス。"""

    @staticmethod
    def is_closed_day(target: date, holidays: frozenset[date]) -> bool:
        if target.weekday() >= 5:
            return True
        if target.month == 12 and target.day >= 29:
            return True
        if target.month == 1 and target.day <= 3:
            return True
        return target in holidays

    @classmethod
    def next_business_day(cls, target: date, holidays: frozenset[date]) -> date:
        shifted = target
        for _ in range(31):
            if not cls.is_closed_day(shifted, holidays):
                return shifted
            shifted += timedelta(days=1)
        raise ValueError("could not find a business day within 31 days")

    @staticmethod
    def next_month(year: int, month: int) -> tuple[int, int]:
        if month == 12:
            return year + 1, 1
        return year, month + 1

    @classmethod
    def next_month_day(cls, year: int, month: int, day: int | None) -> date:
        next_year, next_month = cls.next_month(year, month)
        if day is None:
            return date(next_year, next_month, monthrange(next_year, next_month)[1])
        return date(next_year, next_month, day)

    @classmethod
    def withholding_statutory_due_date(cls, year: int, month: int, *, special: bool) -> date:
        """源泉所得税の法定納期限。納期の特例では半年分をまとめて納付する。"""
        if not special:
            return cls.next_month_day(year, month, 10)
        if month <= 6:
            return date(year, 7, 10)
        return date(year + 1, 1, 20)

    @classmethod
    def _task(
        cls,
        *,
        task_type: str,
        title: str,
        payee: str,
        amount: Decimal,
        statutory_due_date: date,
        legal_basis: str,
        holidays: frozenset[date],
    ) -> PaymentTask:
        due_date = cls.next_business_day(statutory_due_date, holidays)
        return PaymentTask(
            task_type=task_type,
            title=title,
            payee=payee,
            amount=amount,
            statutory_due_date=statutory_due_date,
            due_date=due_date,
            shifted=due_date != statutory_due_date,
            legal_basis=legal_basis,
        )

    @classmethod
    def generate(cls, payload: PaymentTaskInput) -> PaymentTaskResult:
        if not 1 <= payload.payroll_month <= 12:
            raise ValueError("payroll_month must be between 1 and 12")
        amounts = (payload.income_tax, payload.residence_tax, payload.social_insurance_total)
        if any(amount < _ZERO for amount in amounts):
            raise ValueError("amounts must not be negative")
        if all(amount == _ZERO for amount in amounts):
            raise ValueError("at least one payment amount is required")

        holidays = frozenset(payload.holidays or ())
        label = f"{payload.payroll_year}年{payload.payroll_month}月分"
        tasks: list[PaymentTask] = []

        if payload.income_tax > _ZERO:
            statutory = cls.withholding_statutory_due_date(
                payload.payroll_year,
                payload.payroll_month,
                special=payload.withholding_special_exception,
            )
            suffix = "(納期の特例)" if payload.withholding_special_exception else ""
            tasks.append(
                cls._task(
                    task_type=TASK_WITHHOLDING_TAX,
                    title=f"源泉所得税納付 {label}{suffix}",
                    payee=PAYEE_TAX_OFFICE,
                    amount=payload.income_tax,
                    statutory_due_date=statutory,
                    legal_basis="所得税法216条" if payload.withholding_special_exception else "所得税法183条",
                    holidays=holidays,
                ),
            )

        if payload.residence_tax > _ZERO:
            tasks.append(
                cls._task(
                    task_type=TASK_RESIDENCE_TAX,
                    title=f"住民税(特別徴収)納付 {label}",
                    payee=PAYEE_MUNICIPALITY,
                    amount=payload.residence_tax,
                    statutory_due_date=cls.next_month_day(
                        payload.payroll_year, payload.payroll_month, 10
                    ),
                    legal_basis="地方税法321条の5",
                    holidays=holidays,
                ),
            )

        if payload.social_insurance_total > _ZERO:
            tasks.append(
                cls._task(
                    task_type=TASK_SOCIAL_INSURANCE,
                    title=f"社会保険料納付 {label}",
                    payee=PAYEE_SOCIAL_INSURANCE,
                    amount=payload.social_insurance_total,
                    statutory_due_date=cls.next_month_day(
                        payload.payroll_year, payload.payroll_month, None
                    ),
                    legal_basis="健康保険法164条・厚生年金保険法83条",
                    holidays=holidays,
                ),
            )

        return PaymentTaskResult(
            payroll_year=payload.payroll_year,
            payroll_month=payload.payroll_month,
            tasks=tasks,
            total_amount=sum((task.amount for task in tasks), _ZERO),
            earliest_due_date=min((task.due_date for task in tasks), default=None),
        )
