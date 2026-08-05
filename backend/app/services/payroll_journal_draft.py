"""月次給与から仕訳ドラフト(計上・納付)を自動生成する。

給与計算が終わっても、事務担当者は総支給・控除内訳・事業主負担を見ながら給与計上仕訳と
翌月の納付仕訳を手で起票する工程が残る。この起票は控除内訳から一意に決まるので機械化できる。

    (借) 給料手当     総支給額        (貸) 預り金(社会保険料)  従業員負担社保
    (借) 法定福利費   事業主負担合計   (貸) 預り金(源泉所得税)  源泉所得税
                                     (貸) 預り金(住民税)      住民税
                                     (貸) その他控除預り金     その他控除
                                     (貸) 未払金(社会保険料)   事業主負担合計
                                     (貸) 現金預金            差引支給額

**差引支給額は入力させず `総支給 − 従業員控除合計` で導出する**のが要点で、これにより貸借不一致の
仕訳が構造的に作れない(控除額の入力ミスは422で弾き、貸借差額として通過させない)。

さらに預り金・未払金は翌月に納付して消えるため、納付仕訳ドラフトと法定納期限も同時に返す。

    源泉所得税・住民税 → 翌月10日
    社会保険料         → 翌月末日 (従業員負担の預り金 + 事業主負担の未払金)

勘定コードは会社ごとに異なるため、行は既存 `event_journal` と同じ勘定ロールで表現し、
実際の勘定科目への対応付けは呼び出し側が行う。
"""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

ROLE_SALARY_EXPENSE = "salary_expense"
ROLE_LEGAL_WELFARE_EXPENSE = "legal_welfare_expense"
ROLE_SOCIAL_INSURANCE_WITHHOLDING = "social_insurance_withholding"
ROLE_INCOME_TAX_WITHHOLDING = "income_tax_withholding"
ROLE_RESIDENCE_TAX_WITHHOLDING = "residence_tax_withholding"
ROLE_OTHER_DEDUCTION_PAYABLE = "other_deduction_payable"
ROLE_SOCIAL_INSURANCE_PAYABLE = "social_insurance_payable"
ROLE_BANK_DEPOSIT = "bank_deposit"

DRAFT_PAYROLL = "payroll"
DRAFT_WITHHOLDING_TAX_PAYMENT = "withholding_tax_payment"
DRAFT_RESIDENCE_TAX_PAYMENT = "residence_tax_payment"
DRAFT_SOCIAL_INSURANCE_PAYMENT = "social_insurance_payment"

_ZERO = Decimal("0")


@dataclass(frozen=True)
class PayrollJournalInput:
    payroll_year: int
    payroll_month: int
    total_gross: Decimal
    employee_social_insurance: Decimal = _ZERO
    employee_employment_insurance: Decimal = _ZERO
    income_tax: Decimal = _ZERO
    residence_tax: Decimal = _ZERO
    other_deductions: Decimal = _ZERO
    employer_social_insurance: Decimal = _ZERO
    employer_employment_insurance: Decimal = _ZERO
    employer_workers_compensation: Decimal = _ZERO
    payment_day: int = 25


@dataclass(frozen=True)
class DraftLine:
    account_role: str
    debit: Decimal
    credit: Decimal


@dataclass(frozen=True)
class PayrollJournalDraft:
    draft_type: str
    description: str
    transaction_date: date
    due_date: date | None
    lines: list[DraftLine]
    total_debit: Decimal
    total_credit: Decimal


@dataclass(frozen=True)
class PayrollJournalResult:
    payroll_year: int
    payroll_month: int
    total_gross: Decimal
    employee_deduction_total: Decimal
    employer_burden_total: Decimal
    net_pay: Decimal
    drafts: list[PayrollJournalDraft]
    balanced: bool


class PayrollJournalDraftService:
    """給与の計上仕訳と納付仕訳のドラフトを生成する純粋サービス。"""

    @staticmethod
    def next_month(year: int, month: int) -> tuple[int, int]:
        if month == 12:
            return year + 1, 1
        return year, month + 1

    @classmethod
    def payment_deadline(cls, year: int, month: int, *, day: int | None) -> date:
        """翌月の納期限(day=None は翌月末日)。"""
        next_year, next_month = cls.next_month(year, month)
        if day is None:
            return date(next_year, next_month, monthrange(next_year, next_month)[1])
        return date(next_year, next_month, day)

    @staticmethod
    def _build(
        draft_type: str,
        description: str,
        transaction_date: date,
        due_date: date | None,
        entries: list[tuple[str, Decimal, Decimal]],
    ) -> PayrollJournalDraft:
        lines = [
            DraftLine(account_role=role, debit=debit, credit=credit)
            for role, debit, credit in entries
            if debit > _ZERO or credit > _ZERO
        ]
        total_debit = sum((line.debit for line in lines), _ZERO)
        total_credit = sum((line.credit for line in lines), _ZERO)
        if total_debit != total_credit:
            raise ValueError(f"generated {draft_type} draft is unbalanced")
        return PayrollJournalDraft(
            draft_type=draft_type,
            description=description,
            transaction_date=transaction_date,
            due_date=due_date,
            lines=lines,
            total_debit=total_debit,
            total_credit=total_credit,
        )

    @classmethod
    def generate(cls, payload: PayrollJournalInput) -> PayrollJournalResult:
        amounts = (
            payload.total_gross,
            payload.employee_social_insurance,
            payload.employee_employment_insurance,
            payload.income_tax,
            payload.residence_tax,
            payload.other_deductions,
            payload.employer_social_insurance,
            payload.employer_employment_insurance,
            payload.employer_workers_compensation,
        )
        if any(amount < _ZERO for amount in amounts):
            raise ValueError("amounts must not be negative")
        if payload.total_gross <= _ZERO:
            raise ValueError("total_gross must be positive")
        if not 1 <= payload.payroll_month <= 12:
            raise ValueError("payroll_month must be between 1 and 12")
        last_day = monthrange(payload.payroll_year, payload.payroll_month)[1]
        if not 1 <= payload.payment_day <= last_day:
            raise ValueError("payment_day is outside the payroll month")

        employee_insurance = (
            payload.employee_social_insurance + payload.employee_employment_insurance
        )
        deduction_total = (
            employee_insurance
            + payload.income_tax
            + payload.residence_tax
            + payload.other_deductions
        )
        if deduction_total > payload.total_gross:
            raise ValueError("deductions must not exceed total_gross")

        employer_burden = (
            payload.employer_social_insurance
            + payload.employer_employment_insurance
            + payload.employer_workers_compensation
        )
        net_pay = payload.total_gross - deduction_total
        payment_date = date(payload.payroll_year, payload.payroll_month, payload.payment_day)
        label = f"{payload.payroll_year}年{payload.payroll_month}月"

        drafts = [
            cls._build(
                DRAFT_PAYROLL,
                f"給与計上 {label}",
                payment_date,
                None,
                [
                    (ROLE_SALARY_EXPENSE, payload.total_gross, _ZERO),
                    (ROLE_LEGAL_WELFARE_EXPENSE, employer_burden, _ZERO),
                    (ROLE_SOCIAL_INSURANCE_WITHHOLDING, _ZERO, employee_insurance),
                    (ROLE_INCOME_TAX_WITHHOLDING, _ZERO, payload.income_tax),
                    (ROLE_RESIDENCE_TAX_WITHHOLDING, _ZERO, payload.residence_tax),
                    (ROLE_OTHER_DEDUCTION_PAYABLE, _ZERO, payload.other_deductions),
                    (ROLE_SOCIAL_INSURANCE_PAYABLE, _ZERO, employer_burden),
                    (ROLE_BANK_DEPOSIT, _ZERO, net_pay),
                ],
            ),
        ]

        if payload.income_tax > _ZERO:
            due = cls.payment_deadline(payload.payroll_year, payload.payroll_month, day=10)
            drafts.append(
                cls._build(
                    DRAFT_WITHHOLDING_TAX_PAYMENT,
                    f"源泉所得税納付 {label}分",
                    due,
                    due,
                    [
                        (ROLE_INCOME_TAX_WITHHOLDING, payload.income_tax, _ZERO),
                        (ROLE_BANK_DEPOSIT, _ZERO, payload.income_tax),
                    ],
                ),
            )

        if payload.residence_tax > _ZERO:
            due = cls.payment_deadline(payload.payroll_year, payload.payroll_month, day=10)
            drafts.append(
                cls._build(
                    DRAFT_RESIDENCE_TAX_PAYMENT,
                    f"住民税納付 {label}分",
                    due,
                    due,
                    [
                        (ROLE_RESIDENCE_TAX_WITHHOLDING, payload.residence_tax, _ZERO),
                        (ROLE_BANK_DEPOSIT, _ZERO, payload.residence_tax),
                    ],
                ),
            )

        social_payment_total = employee_insurance + employer_burden
        if social_payment_total > _ZERO:
            due = cls.payment_deadline(payload.payroll_year, payload.payroll_month, day=None)
            drafts.append(
                cls._build(
                    DRAFT_SOCIAL_INSURANCE_PAYMENT,
                    f"社会保険料・労働保険料納付 {label}分",
                    due,
                    due,
                    [
                        (ROLE_SOCIAL_INSURANCE_WITHHOLDING, employee_insurance, _ZERO),
                        (ROLE_SOCIAL_INSURANCE_PAYABLE, employer_burden, _ZERO),
                        (ROLE_BANK_DEPOSIT, _ZERO, social_payment_total),
                    ],
                ),
            )

        return PayrollJournalResult(
            payroll_year=payload.payroll_year,
            payroll_month=payload.payroll_month,
            total_gross=payload.total_gross,
            employee_deduction_total=deduction_total,
            employer_burden_total=employer_burden,
            net_pay=net_pay,
            drafts=drafts,
            balanced=all(draft.total_debit == draft.total_credit for draft in drafts),
        )
