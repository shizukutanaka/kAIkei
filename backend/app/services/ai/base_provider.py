from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class InferenceResult:
    """Result of AI journal inference."""
    account_code: str
    account_name: str
    debit_credit: str
    amount: float
    tax_rate: float
    tax_type: str
    confidence: float
    reasoning: str


@dataclass
class InferenceRequest:
    """Input for AI journal inference."""
    description: str
    amount: float
    transaction_date: str
    partner_name: str | None = None
    document_text: str | None = None
    company_context: dict | None = None


class AIProvider(ABC):
    """Abstract base class for AI providers (OpenAI, Anthropic)."""

    @abstractmethod
    async def infer_journal(self, request: InferenceRequest) -> list[InferenceResult]:
        """Infer journal lines from natural language description."""
        pass

    @abstractmethod
    async def predict_tax(self, description: str, amount: float) -> dict:
        """Predict tax category and rate for a transaction."""
        pass

    @abstractmethod
    async def detect_anomaly(self, journal_data: dict) -> dict:
        """Detect anomalies in journal data."""
        pass
