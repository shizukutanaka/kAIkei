import logging
from datetime import date, datetime
from typing import Any

import httpx

from app.services.integrations.base_adapter import (
    ImportAdapter,
    ImportedJournal,
    ImportedMaster,
)

logger = logging.getLogger(__name__)

FREEE_TAX_MAPPING = {
    "1": "tax_10_ex",
    "2": "tax_8_ex",
    "3": "tax_10_in",
    "4": "tax_8_in",
    "5": "non_taxable",
    "6": "exempt",
    "0": "non_taxable",
}


class FreeeAccountingAdapter(ImportAdapter):
    """freee会計 API import adapter."""

    BASE_URL = "https://api.freee.co.jp"

    def __init__(self, access_token: str | None = None, refresh_token: str | None = None):
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._company_id: int | None = None

    @property
    def software_code(self) -> str:
        return "freee_accounting"

    @property
    def software_name(self) -> str:
        return "freee会計"

    @property
    def supports_api(self) -> bool:
        return True

    @property
    def supports_csv(self) -> bool:
        return True

    async def authenticate(self, credentials: dict[str, str]) -> bool:
        """Exchange authorization code for access token via OAuth 2.0."""
        code = credentials.get("code")
        if not code:
            return False

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.BASE_URL}/oauth/token",
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "client_id": credentials.get("client_id", ""),
                    "client_secret": credentials.get("client_secret", ""),
                    "redirect_uri": credentials.get("redirect_uri", ""),
                },
            )

        if response.status_code == 200:
            data = response.json()
            self._access_token = data.get("access_token")
            self._refresh_token = data.get("refresh_token")
            return True
        return False

    async def test_connection(self) -> bool:
        if not self._access_token:
            return False
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.BASE_URL}/api/1/users/me",
                    headers={"Authorization": f"Bearer {self._access_token}"},
                )
            return response.status_code == 200
        except Exception:
            return False

    async def _get_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }

    async def fetch_journals(self, date_from: date, date_to: date) -> list[ImportedJournal]:
        """Fetch journals from freee API."""
        if not self._access_token or not self._company_id:
            raise RuntimeError("Not authenticated or company_id not set")

        headers = await self._get_headers()
        journals: list[ImportedJournal] = []

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/api/1/journals",
                headers=headers,
                params={
                    "company_id": self._company_id,
                    "start_date": date_from.isoformat(),
                    "end_date": date_to.isoformat(),
                    "limit": 1000,
                },
            )

        if response.status_code != 200:
            logger.error("freee API error: %s", response.text)
            return []

        data = response.json()
        for item in data.get("journals", []):
            lines: list[dict[str, Any]] = []
            for detail in item.get("details", []):
                lines.append({
                    "debit_credit": "debit" if detail.get("debit_credit") == "debit" else "credit",
                    "account_code": str(detail.get("account_item_id", "")),
                    "account_name": detail.get("account_item_name", ""),
                    "sub_account_name": detail.get("sub_account_item_name", ""),
                    "amount": float(detail.get("amount", 0)),
                    "tax_type": FREEE_TAX_MAPPING.get(str(detail.get("tax_id", "0")), "non_taxable"),
                    "department": detail.get("section_name", ""),
                })

            txn_date = datetime.strptime(item.get("date", ""), "%Y-%m-%d").date()
            journals.append(ImportedJournal(
                transaction_date=txn_date,
                journal_number=f"F-{item.get('id', '')}",
                summary=item.get("description", ""),
                lines=lines,
                source_software=self.software_code,
            ))

        return journals

    async def fetch_masters(self) -> ImportedMaster:
        """Fetch account masters from freee API."""
        if not self._access_token or not self._company_id:
            raise RuntimeError("Not authenticated or company_id not set")

        headers = await self._get_headers()

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/api/1/account_items",
                headers=headers,
                params={"company_id": self._company_id, "limit": 1000},
            )

        accounts: list[dict[str, Any]] = []
        if response.status_code == 200:
            data = response.json()
            for item in data.get("account_items", []):
                accounts.append({
                    "account_code": str(item.get("id", "")),
                    "account_name": item.get("name", ""),
                    "account_type": item.get("account_category", ""),
                    "debit_credit": "debit" if item.get("account_category") in ("assets", "expenses") else "credit",
                })

        return ImportedMaster(accounts=accounts, partners=[], departments=[])

    async def fetch_documents(self, date_from: date, date_to: date) -> list[dict[str, Any]]:
        """Fetch documents from freee API (receipts)."""
        if not self._access_token or not self._company_id:
            return []

        headers = await self._get_headers()
        documents: list[dict[str, Any]] = []

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/api/1/receipts",
                headers=headers,
                params={
                    "company_id": self._company_id,
                    "start_date": date_from.isoformat(),
                    "end_date": date_to.isoformat(),
                },
            )

        if response.status_code == 200:
            data = response.json()
            for item in data.get("receipts", []):
                documents.append({
                    "id": item.get("id"),
                    "date": item.get("date"),
                    "amount": item.get("amount"),
                    "description": item.get("description"),
                    "download_url": item.get("download_url"),
                })

        return documents
