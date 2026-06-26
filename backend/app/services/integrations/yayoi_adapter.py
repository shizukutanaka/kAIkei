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

YAYOI_TAX_MAPPING = {
    "1": "tax_10_ex",
    "2": "tax_8_ex",
    "3": "tax_10_in",
    "4": "tax_8_in",
    "5": "non_taxable",
    "6": "exempt",
    "0": "non_taxable",
}


class YayoiAccountingAdapter(ImportAdapter):
    """弥生会計 CSV import adapter."""

    @property
    def software_code(self) -> str:
        return "yayoi_accounting"

    @property
    def software_name(self) -> str:
        return "弥生会計"

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
        raise NotImplementedError("CSV-based adapter requires file upload, not API fetch.")

    async def fetch_masters(self) -> ImportedMaster:
        raise NotImplementedError("CSV-based adapter requires file upload, not API fetch.")

    async def fetch_documents(self, date_from: date, date_to: date) -> list[dict[str, Any]]:
        return []

    def parse_csv(self, csv_content: str, encoding: str = "utf-8") -> list[ImportedJournal]:
        """Parse Yayoi-format CSV into ImportedJournal list.

        Expected columns: 取引日, 伝票番号, 借方科目コード, 借方科目名, 借方補助科目,
        借方金額, 貸方科目コード, 貸方科目名, 貸方補助科目, 貸方金額, 摘要, 税区分, 部門
        """
        reader = csv.DictReader(io.StringIO(csv_content))
        journals: list[ImportedJournal] = []

        for row in reader:
            try:
                txn_date = datetime.strptime(row.get("取引日", ""), "%Y/%m/%d").date()
                journal_number = row.get("伝票番号", "")
                summary = row.get("摘要", "")

                lines: list[dict[str, Any]] = []

                debit_amount = Decimal(row.get("借方金額", "0") or "0")
                if debit_amount > 0:
                    lines.append({
                        "debit_credit": "debit",
                        "account_code": row.get("借方科目コード", ""),
                        "account_name": row.get("借方科目名", ""),
                        "sub_account_name": row.get("借方補助科目", ""),
                        "amount": float(debit_amount),
                        "tax_type": YAYOI_TAX_MAPPING.get(row.get("税区分", "0"), "non_taxable"),
                        "department": row.get("部門", ""),
                    })

                credit_amount = Decimal(row.get("貸方金額", "0") or "0")
                if credit_amount > 0:
                    lines.append({
                        "debit_credit": "credit",
                        "account_code": row.get("貸方科目コード", ""),
                        "account_name": row.get("貸方科目名", ""),
                        "sub_account_name": row.get("貸方補助科目", ""),
                        "amount": float(credit_amount),
                        "tax_type": YAYOI_TAX_MAPPING.get(row.get("税区分", "0"), "non_taxable"),
                        "department": row.get("部門", ""),
                    })

                journals.append(ImportedJournal(
                    transaction_date=txn_date,
                    journal_number=journal_number,
                    summary=summary,
                    lines=lines,
                    source_software=self.software_code,
                ))

            except (ValueError, KeyError) as e:
                logger.warning("Failed to parse CSV row: %s, error: %s", row, e)
                continue

        return journals

    def parse_master_csv(self, csv_content: str) -> ImportedMaster:
        """Parse Yayoi account master CSV."""
        reader = csv.DictReader(io.StringIO(csv_content))
        accounts: list[dict[str, Any]] = []

        for row in reader:
            accounts.append({
                "account_code": row.get("科目コード", ""),
                "account_name": row.get("科目名", ""),
                "account_type": row.get("科目分類", ""),
                "debit_credit": row.get("貸借区分", ""),
            })

        return ImportedMaster(accounts=accounts, partners=[], departments=[])
