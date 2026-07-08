import csv
import io
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.services.integrations.base_adapter import (
    ImportAdapter,
    ImportedJournal,
    ImportedMaster,
)

logger = logging.getLogger(__name__)


class GenericCsvAdapter(ImportAdapter):
    """汎用CSV インポートアダプタ — ユーザー定義カラムマッピング対応。"""

    DEFAULT_MAPPING = {
        "transaction_date": "取引日",
        "journal_number": "伝票番号",
        "debit_account_code": "借方科目コード",
        "debit_account_name": "借方科目名",
        "debit_amount": "借方金額",
        "credit_account_code": "貸方科目コード",
        "credit_account_name": "貸方科目名",
        "credit_amount": "貸方金額",
        "summary": "摘要",
        "tax_category": "税区分",
        "department": "部門",
    }

    def __init__(self, column_mapping: dict[str, str] | None = None, date_format: str = "%Y/%m/%d"):
        self._column_mapping = column_mapping or self.DEFAULT_MAPPING
        self._date_format = date_format

    @property
    def software_code(self) -> str:
        return "generic_csv"

    @property
    def software_name(self) -> str:
        return "汎用CSV"

    @property
    def supports_api(self) -> bool:
        return False

    @property
    def supports_csv(self) -> bool:
        return True

    async def authenticate(self, credentials: dict[str, str]) -> bool:
        return True

    async def test_connection(self) -> bool:
        return True

    async def fetch_journals(self, date_from: date, date_to: date) -> list[ImportedJournal]:
        raise NotImplementedError("CSV adapter requires file upload.")

    async def fetch_masters(self) -> ImportedMaster:
        raise NotImplementedError("CSV adapter requires file upload.")

    async def fetch_documents(self, date_from: date, date_to: date) -> list[dict[str, Any]]:
        return []

    def parse_csv(self, csv_content: str, encoding: str = "utf-8") -> list[ImportedJournal]:
        """Parse generic CSV with user-defined column mapping."""
        reader = csv.DictReader(io.StringIO(csv_content))
        journals: list[ImportedJournal] = []
        mapping = self._column_mapping

        for row in reader:
            try:
                date_str = row.get(mapping["transaction_date"], "")
                txn_date = datetime.strptime(date_str, self._date_format).date()
                journal_number = row.get(mapping.get("journal_number", "伝票番号"), "")
                summary = row.get(mapping.get("summary", "摘要"), "")

                lines: list[dict[str, Any]] = []

                debit_amount_str = row.get(mapping.get("debit_amount", "借方金額"), "0") or "0"
                debit_amount = Decimal(debit_amount_str)
                if debit_amount > 0:
                    lines.append({
                        "debit_credit": "debit",
                        "account_code": row.get(mapping.get("debit_account_code", "借方科目コード"), ""),
                        "account_name": row.get(mapping.get("debit_account_name", "借方科目名"), ""),
                        "amount": float(debit_amount),
                        "tax_type": "non_taxable",
                        "department": row.get(mapping.get("department", "部門"), ""),
                    })

                credit_amount_str = row.get(mapping.get("credit_amount", "貸方金額"), "0") or "0"
                credit_amount = Decimal(credit_amount_str)
                if credit_amount > 0:
                    lines.append({
                        "debit_credit": "credit",
                        "account_code": row.get(mapping.get("credit_account_code", "貸方科目コード"), ""),
                        "account_name": row.get(mapping.get("credit_account_name", "貸方科目名"), ""),
                        "amount": float(credit_amount),
                        "tax_type": "non_taxable",
                        "department": row.get(mapping.get("department", "部門"), ""),
                    })

                if lines:
                    journals.append(ImportedJournal(
                        transaction_date=txn_date,
                        journal_number=journal_number,
                        summary=summary,
                        lines=lines,
                        source_software=self.software_code,
                    ))

            except (ValueError, KeyError) as e:
                logger.warning("Failed to parse generic CSV row: %s, error: %s", row, e)
                continue

        return journals
