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
