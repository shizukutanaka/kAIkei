from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta


def _month_end(year: int, month: int) -> int:
    return monthrange(year, month)[1]


def _add_months(year: int, month: int, delta: int) -> tuple[int, int]:
    total_months = year * 12 + (month - 1) + delta
    return total_months // 12, total_months % 12 + 1


def _clamp_day(year: int, month: int, day: int) -> date:
    return date(year, month, min(day, _month_end(year, month)))


def _is_business_day(current: date, holidays: set[date] | None) -> bool:
    if current.weekday() >= 5:
        return False
    return holidays is None or current not in holidays


class PaymentTermsService:
    @staticmethod
    def compute_closing_date(invoice_date: date, closing_day: int) -> date:
        if closing_day < 1 or closing_day > 31:
            raise ValueError("closing_day must be between 1 and 31")

        invoice_month_end = _month_end(invoice_date.year, invoice_date.month)
        closing_target_day = invoice_month_end if closing_day >= invoice_month_end else closing_day
        closing_date = _clamp_day(invoice_date.year, invoice_date.month, closing_target_day)
        if invoice_date.day > closing_date.day:
            next_year, next_month = _add_months(invoice_date.year, invoice_date.month, 1)
            closing_date = _clamp_day(next_year, next_month, closing_target_day)
        return closing_date

    @staticmethod
    def compute_payment_date(
        invoice_date: date,
        closing_day: int,
        payment_month_offset: int,
        payment_day: int,
        holidays: set[date] | None = None,
        adjustment: str = "next",
    ) -> date:
        if payment_day < 1 or payment_day > 31:
            raise ValueError("payment_day must be between 1 and 31")
        if payment_month_offset < 0:
            raise ValueError("payment_month_offset must be non-negative")
        if adjustment not in {"next", "previous", "none"}:
            raise ValueError("adjustment must be one of next, previous, none")

        closing_date = PaymentTermsService.compute_closing_date(invoice_date, closing_day)

        payment_year, payment_month = _add_months(closing_date.year, closing_date.month, payment_month_offset)
        payment_target_day = _month_end(payment_year, payment_month) if payment_day >= 31 else payment_day
        payment_date = _clamp_day(payment_year, payment_month, payment_target_day)

        if adjustment == "none":
            return payment_date

        step = timedelta(days=1 if adjustment == "next" else -1)
        current = payment_date
        while not _is_business_day(current, holidays):
            current += step
        return current
