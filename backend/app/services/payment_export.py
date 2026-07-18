from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from app.models.models import PaymentRequest


class ZenginExportService:
    RECORD_BYTES = 120

    @staticmethod
    def _fit(value: str, width: int) -> str:
        text = value[:width]
        return text.ljust(width)

    @classmethod
    def _render_line(cls, prefix: str, parts: list[str]) -> bytes:
        raw = "|".join([prefix, *parts])
        encoded = raw.encode("utf-8")
        if len(encoded) > cls.RECORD_BYTES:
            # バイト単位で切ると末尾のマルチバイト文字が分割され不正なUTF-8になるため、
            # 文字境界まで縮めてから切り詰める（口座名義等の破損は上位でフィールド幅管理する前提）。
            encoded = encoded[: cls.RECORD_BYTES]
            while encoded:
                try:
                    encoded.decode("utf-8")
                    break
                except UnicodeDecodeError:
                    encoded = encoded[:-1]
        return encoded.ljust(cls.RECORD_BYTES, b" ")

    @classmethod
    def render(cls, requests: list[PaymentRequest], company_id: UUID, payment_date: str, bank_account_id: UUID) -> bytes:
        total = sum((Decimal(str(req.payment_amount)) for req in requests), Decimal("0"))
        records = [
            cls._render_line(
                "HDR",
                [company_id.hex, payment_date, bank_account_id.hex, str(len(requests)), f"{total:.2f}"],
            )
        ]
        for req in requests:
            records.append(
                cls._render_line(
                    "DTL",
                    [
                        # 内部UUID（64バイト）は全銀レコードに不要で、これが120バイト枠を
                        # 圧迫し口座名義を切り捨てさせていたため除外する。
                        req.payment_date.isoformat(),
                        f"{Decimal(str(req.payment_amount)):.2f}",
                        req.dest_bank_code or "",
                        req.dest_branch_code or "",
                        req.dest_account_type or "",
                        req.dest_account_no or "",
                        req.dest_account_name_kana or "",
                    ],
                )
            )
        records.append(cls._render_line("TRL", [str(len(requests)), f"{total:.2f}"]))
        return b"\n".join(records)
