from datetime import date

import pytest

from app.services.payment_terms import PaymentTermsService


class TestPaymentTermsService:
    def test_month_end_clamp_next_month_end_payment(self):
        result = PaymentTermsService.compute_payment_date(
            invoice_date=date(2025, 1, 15),
            closing_day=31,
            payment_month_offset=1,
            payment_day=31,
        )
        assert result == date(2025, 2, 28)

    def test_after_cutoff_rolls_to_next_period(self):
        result = PaymentTermsService.compute_payment_date(
            invoice_date=date(2025, 1, 25),
            closing_day=20,
            payment_month_offset=1,
            payment_day=31,
        )
        assert result == date(2025, 3, 31)

    def test_weekend_adjustment_next_and_previous(self):
        next_result = PaymentTermsService.compute_payment_date(
            invoice_date=date(2025, 5, 10),
            closing_day=10,
            payment_month_offset=0,
            payment_day=31,
            adjustment="next",
        )
        previous_result = PaymentTermsService.compute_payment_date(
            invoice_date=date(2025, 5, 10),
            closing_day=10,
            payment_month_offset=0,
            payment_day=31,
            adjustment="previous",
        )
        assert next_result == date(2025, 6, 2)
        assert previous_result == date(2025, 5, 30)

    def test_holiday_adjustment(self):
        raw_payment_date = date(2025, 5, 30)
        result = PaymentTermsService.compute_payment_date(
            invoice_date=date(2025, 5, 10),
            closing_day=10,
            payment_month_offset=0,
            payment_day=30,
            holidays={raw_payment_date},
        )
        assert result == date(2025, 6, 2)

    def test_month_end_clamp(self):
        result = PaymentTermsService.compute_payment_date(
            invoice_date=date(2025, 4, 15),
            closing_day=15,
            payment_month_offset=0,
            payment_day=31,
            adjustment="none",
        )
        assert result == date(2025, 4, 30)

    def test_invalid_inputs_raise(self):
        with pytest.raises(ValueError):
            PaymentTermsService.compute_payment_date(date(2025, 1, 1), 0, 1, 31)
        with pytest.raises(ValueError):
            PaymentTermsService.compute_payment_date(date(2025, 1, 1), 32, 1, 31)
        with pytest.raises(ValueError):
            PaymentTermsService.compute_payment_date(date(2025, 1, 1), 20, -1, 31)
        with pytest.raises(ValueError):
            PaymentTermsService.compute_payment_date(date(2025, 1, 1), 20, 1, 31, adjustment="bad")
