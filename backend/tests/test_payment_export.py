from datetime import date
from decimal import Decimal
from uuid import uuid4

from app.models.models import PaymentRequest
from app.services.payment_export import ZenginExportService


def _payment_request(*, amount: str, payment_date: date) -> PaymentRequest:
    return PaymentRequest(
        payment_request_id=uuid4(),
        company_id=uuid4(),
        partner_id=uuid4(),
        payment_date=payment_date,
        payment_amount=Decimal(amount),
        bank_account_id=uuid4(),
        dest_bank_code="0001",
        dest_branch_code="001",
        dest_account_type="ordinary",
        dest_account_no="1234567",
        dest_account_name_kana="ﾃｽﾄﾀﾛｳ",
        status="approved",
        created_by=uuid4(),
    )


class TestZenginExportService:
    def test_each_record_is_120_bytes(self):
        requests = [
            _payment_request(amount="1000", payment_date=date(2026, 6, 30)),
            _payment_request(amount="2500", payment_date=date(2026, 6, 30)),
        ]
        body = ZenginExportService.render(
            requests=requests,
            company_id=uuid4(),
            payment_date="2026-06-30",
            bank_account_id=uuid4(),
        )
        records = body.splitlines()
        assert len(records) == 4
        assert all(len(record) == 120 for record in records)

    def test_total_amount_is_encoded(self):
        requests = [
            _payment_request(amount="1000", payment_date=date(2026, 6, 30)),
            _payment_request(amount="2500", payment_date=date(2026, 6, 30)),
        ]
        body = ZenginExportService.render(
            requests=requests,
            company_id=uuid4(),
            payment_date="2026-06-30",
            bank_account_id=uuid4(),
        )
        assert b"3500.00" in body

    def test_empty_export_still_has_header_and_trailer(self):
        body = ZenginExportService.render(
            requests=[],
            company_id=uuid4(),
            payment_date="2026-06-30",
            bank_account_id=uuid4(),
        )
        records = body.splitlines()
        assert len(records) == 2
        assert records[0].startswith(b"HDR|")
        assert records[1].startswith(b"TRL|")
