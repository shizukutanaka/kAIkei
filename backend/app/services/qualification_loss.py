"""被保険者資格喪失届のデータ生成と保険料徴収月の判定。

資格喪失日は喪失事由で決まり、社会保険料は**資格喪失日が属する月の前月分まで**徴収する
(健康保険法156条・厚生年金保険法19条: 保険料は資格取得月から喪失月の前月まで)。
このため月末退職と月末以外の退職で徴収する最終月が1か月ずれる。

    退職日 3/31 → 喪失日 4/1  → 最終徴収月 3月 (退職月の保険料を控除する)
    退職日 3/30 → 喪失日 3/31 → 最終徴収月 2月 (退職月の保険料は控除しない)

喪失事由ごとの喪失日:

    retirement / death : 退職日・死亡日の翌日
    age_70             : 70歳の誕生日の前日 (厚生年金の資格喪失)
    age_75             : 75歳の誕生日当日 (健康保険の資格喪失・後期高齢者医療へ)

同一月内に資格取得と資格喪失があった場合(同月得喪)は、喪失月の前月まで徴収という原則の
例外として、その月の保険料が1か月分必要になる。

生成CSVは 被保険者資格喪失届 記載事項に沿った構造化連携用データであり、特定バージョンの
e-Gov CSV仕様書に対して byte-verified ではない。実連携時に正確なレイアウトへマッピングする。
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, timedelta
from io import StringIO

LOSS_REASONS: frozenset[str] = frozenset({"retirement", "death", "age_70", "age_75"})


@dataclass(frozen=True)
class LossEmployee:
    insured_number: str
    name: str
    event_date: date
    reason: str
    qualification_date: date | None = None
    is_over_70_employee: bool = False


@dataclass(frozen=True)
class LossResult:
    insured_number: str
    name: str
    reason: str
    event_date: date
    loss_date: date
    final_premium_year: int
    final_premium_month: int
    event_month_premium_charged: bool
    same_month_acquisition_loss: bool
    requires_over70_notification: bool


@dataclass(frozen=True)
class QualificationLossResult:
    employee_count: int
    results: list[LossResult]
    same_month_numbers: list[str]
    csv_text: str


class QualificationLossService:
    """資格喪失届データを生成する純粋サービス。"""

    HEADER = [
        "insured_number",
        "name",
        "reason",
        "event_date",
        "loss_date",
        "final_premium_month",
        "event_month_premium_charged",
        "same_month_acquisition_loss",
        "requires_over70_notification",
    ]

    @staticmethod
    def loss_date(event_date: date, reason: str) -> date:
        if reason not in LOSS_REASONS:
            raise ValueError(f"unknown loss reason: {reason}")
        if reason in ("retirement", "death"):
            return event_date + timedelta(days=1)
        if reason == "age_70":
            return event_date - timedelta(days=1)
        return event_date

    @staticmethod
    def previous_month(target: date) -> tuple[int, int]:
        if target.month == 1:
            return target.year - 1, 12
        return target.year, target.month - 1

    @classmethod
    def compute_employee(cls, employee: LossEmployee) -> LossResult:
        if employee.insured_number.strip() == "":
            raise ValueError("insured_number is required")

        loss_date = cls.loss_date(employee.event_date, employee.reason)
        if employee.qualification_date is not None and employee.qualification_date > loss_date:
            raise ValueError("qualification_date must not be later than loss_date")

        final_year, final_month = cls.previous_month(loss_date)
        same_month = employee.qualification_date is not None and (
            employee.qualification_date.year,
            employee.qualification_date.month,
        ) == (loss_date.year, loss_date.month)
        event_month_charged = same_month or (final_year, final_month) == (
            employee.event_date.year,
            employee.event_date.month,
        )
        if same_month:
            final_year, final_month = loss_date.year, loss_date.month

        return LossResult(
            insured_number=employee.insured_number,
            name=employee.name,
            reason=employee.reason,
            event_date=employee.event_date,
            loss_date=loss_date,
            final_premium_year=final_year,
            final_premium_month=final_month,
            event_month_premium_charged=event_month_charged,
            same_month_acquisition_loss=same_month,
            requires_over70_notification=employee.is_over_70_employee
            and employee.reason in ("retirement", "death"),
        )

    @classmethod
    def build_csv(cls, results: list[LossResult]) -> str:
        buffer = StringIO(newline="")
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(cls.HEADER)
        for result in results:
            writer.writerow(
                [
                    result.insured_number,
                    result.name,
                    result.reason,
                    result.event_date.isoformat(),
                    result.loss_date.isoformat(),
                    f"{result.final_premium_year:04d}-{result.final_premium_month:02d}",
                    "1" if result.event_month_premium_charged else "0",
                    "1" if result.same_month_acquisition_loss else "0",
                    "1" if result.requires_over70_notification else "0",
                ],
            )
        return buffer.getvalue()

    @classmethod
    def generate(cls, employees: list[LossEmployee]) -> QualificationLossResult:
        if not employees:
            raise ValueError("employees must not be empty")

        results = [cls.compute_employee(employee) for employee in employees]
        return QualificationLossResult(
            employee_count=len(results),
            results=results,
            same_month_numbers=[
                result.insured_number for result in results if result.same_month_acquisition_loss
            ],
            csv_text=cls.build_csv(results),
        )
