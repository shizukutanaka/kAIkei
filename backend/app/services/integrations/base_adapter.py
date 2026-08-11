from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass
class ImportedJournal:
    """Imported journal entry from external software."""
    transaction_date: date
    journal_number: str
    summary: str
    lines: list[dict[str, Any]]
    source_software: str


@dataclass
class ImportedMaster:
    """Imported master data from external software."""
    accounts: list[dict[str, Any]]
    partners: list[dict[str, Any]]
    departments: list[dict[str, Any]]


class ImportAdapter(ABC):
    """Abstract base class for external software import adapters."""

    @abstractmethod
    async def authenticate(self, credentials: dict[str, str]) -> bool:
        """Authenticate with the external software."""
        pass

    @abstractmethod
    async def test_connection(self) -> bool:
        """Test the connection to the external software."""
        pass

    @abstractmethod
    async def fetch_journals(self, date_from: date, date_to: date) -> list[ImportedJournal]:
        """Fetch journal entries for the given date range."""
        pass

    @abstractmethod
    async def fetch_masters(self) -> ImportedMaster:
        """Fetch master data (accounts, partners, departments)."""
        pass

    @abstractmethod
    async def fetch_documents(self, date_from: date, date_to: date) -> list[dict[str, Any]]:
        """Fetch document files for the given date range."""
        pass

    @property
    @abstractmethod
    def software_code(self) -> str:
        """Unique identifier for this software."""
        pass

    @property
    @abstractmethod
    def software_name(self) -> str:
        """Display name for this software."""
        pass

    @property
    @abstractmethod
    def supports_api(self) -> bool:
        """Whether this software supports API integration."""
        pass

    @property
    @abstractmethod
    def supports_csv(self) -> bool:
        """Whether this software supports CSV import."""
        pass

    def parse_csv(self, csv_content: str, encoding: str = "utf-8") -> list[ImportedJournal]:
        """Parse a CSV export into ImportedJournal entries.

        CSV-capable adapters override this. The default raises so that an
        adapter advertising ``supports_csv`` without an implementation fails
        loudly rather than silently importing nothing.
        """
        raise NotImplementedError(f"{self.software_code} does not implement CSV parsing")

    def validate_import(self, journals: list[ImportedJournal]) -> dict[str, Any]:
        """Validate imported journals and return an error report.

        Format-agnostic: operates on the normalized ImportedJournal line
        dicts, so every adapter shares one balance/amount/account check.
        """
        errors: list[dict[str, Any]] = []
        valid_count = 0
        error_count = 0

        for i, journal in enumerate(journals):
            row_errors: list[str] = []

            debit_total = sum(ln["amount"] for ln in journal.lines if ln["debit_credit"] == "debit")
            credit_total = sum(ln["amount"] for ln in journal.lines if ln["debit_credit"] == "credit")

            if abs(debit_total - credit_total) > 0.01:
                row_errors.append(f"貸借不一致: 借方{debit_total} / 貸方{credit_total}")

            if not journal.lines:
                row_errors.append("行データが空")

            for j, line in enumerate(journal.lines):
                if line["amount"] == 0:
                    row_errors.append(f"行{j+1}: 金額が0")
                # 科目はコードまたは名称のいずれかで識別できればよい
                # （freee等の名称ベースCSVを許容）。
                if not line.get("account_code") and not line.get("account_name"):
                    row_errors.append(f"行{j+1}: 科目が空")

            if row_errors:
                error_count += 1
                errors.append({
                    "row": i + 1,
                    "journal_number": journal.journal_number,
                    "date": journal.transaction_date.isoformat(),
                    "errors": row_errors,
                })
            else:
                valid_count += 1

        return {
            "total": len(journals),
            "valid": valid_count,
            "errors": error_count,
            "error_details": errors,
            "is_valid": error_count == 0,
        }
