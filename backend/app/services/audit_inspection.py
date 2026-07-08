from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

LARGE_AMOUNT_THRESHOLD = Decimal("10000000")


@dataclass(frozen=True)
class AuditDetection:
    risk_level: str
    category: str
    reason: str


class AuditInspectionService:
    @staticmethod
    def _line_signature(lines: list[Any]) -> tuple[tuple[str, str, str], ...]:
        signature: list[tuple[str, str, str]] = []
        for line in lines:
            signature.append(
                (
                    str(line.account_id),
                    str(line.debit_credit),
                    str(Decimal(str(line.amount))),
                )
            )
        return tuple(sorted(signature))

    @staticmethod
    def _total_debit(lines: list[Any]) -> Decimal:
        total = Decimal("0")
        for line in lines:
            if line.debit_credit == "debit" and not getattr(line, "is_deleted", False):
                total += Decimal(str(line.amount))
        return total

    @staticmethod
    def inspect(
        *,
        target_header: Any,
        target_lines: list[Any],
        peer_headers_with_lines: list[tuple[Any, list[Any]]],
    ) -> list[AuditDetection]:
        detections: list[AuditDetection] = []
        target_signature = AuditInspectionService._line_signature(target_lines)
        target_total_debit = AuditInspectionService._total_debit(target_lines)

        for peer_header, peer_lines in peer_headers_with_lines:
            if getattr(peer_header, "is_deleted", False) or getattr(peer_header, "is_voided", False):
                continue
            if peer_header.journal_header_id == target_header.journal_header_id:
                continue
            if peer_header.transaction_date != target_header.transaction_date:
                continue
            if AuditInspectionService._total_debit(peer_lines) != target_total_debit:
                continue
            if AuditInspectionService._line_signature(peer_lines) != target_signature:
                continue
            detections.append(
                AuditDetection(
                    risk_level="critical",
                    category="duplicate",
                    reason=(
                        f"同一日・同一金額・同一明細の重複仕訳が検出されました。"
                        f" 対象={target_header.journal_header_id}, 重複候補={peer_header.journal_header_id}"
                    ),
                )
            )

        created_at = getattr(target_header, "created_at", None)
        if isinstance(created_at, datetime) and 0 <= created_at.hour < 5:
            detections.append(
                AuditDetection(
                    risk_level="info",
                    category="after_hours",
                    reason=f"作成時刻が深夜帯です。作成時刻={created_at.isoformat()}",
                )
            )

        debit_accounts = {
            str(line.account_id)
            for line in target_lines
            if not getattr(line, "is_deleted", False) and line.debit_credit == "debit"
        }
        credit_accounts = {
            str(line.account_id)
            for line in target_lines
            if not getattr(line, "is_deleted", False) and line.debit_credit == "credit"
        }
        circular_accounts = sorted(debit_accounts & credit_accounts)
        if circular_accounts:
            detections.append(
                AuditDetection(
                    risk_level="warning",
                    category="circular",
                    reason=f"同一仕訳内で借方・貸方に同一勘定科目があります。 account_id={', '.join(circular_accounts)}",
                )
            )

        if target_total_debit >= LARGE_AMOUNT_THRESHOLD:
            detections.append(
                AuditDetection(
                    risk_level="warning",
                    category="large_amount",
                    reason=(
                        f"借方合計が高額です。借方合計={target_total_debit}, しきい値={LARGE_AMOUNT_THRESHOLD}"
                    ),
                )
            )

        return detections
