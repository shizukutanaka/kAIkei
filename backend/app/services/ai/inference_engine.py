import logging
from typing import Any

from app.core.config import settings
from app.services.ai.anthropic_provider import AnthropicProvider
from app.services.ai.base_provider import AIProvider, InferenceRequest, InferenceResult
from app.services.ai.local_llm_provider import LocalLLMProvider
from app.services.ai.task_router import TaskComplexity, TaskRouter

logger = logging.getLogger(__name__)

_CONFIDENCE_THRESHOLD = 0.7


class AIInferenceEngine:
    """Multi-provider AI inference engine with task routing and fallback support.

    Supports:
    - Cloud LLMs: OpenAI GPT-4o, Anthropic Claude
    - Local LLMs: Ollama, vLLM, llama.cpp, LM Studio (OpenAI-compatible API)
    - Task routing: Light tasks → local LLM, heavy tasks → cloud LLM
    """

    def __init__(self) -> None:
        self._providers: list[AIProvider] = []
        self._router = TaskRouter()

        if settings.LOCAL_LLM_ENDPOINT:
            local_provider = LocalLLMProvider(
                endpoint_url=settings.LOCAL_LLM_ENDPOINT,
                model=settings.LOCAL_LLM_MODEL,
                api_key=settings.LOCAL_LLM_API_KEY,
                timeout=settings.LOCAL_LLM_TIMEOUT,
            )
            self._providers.append(local_provider)
            self._router.register(
                provider=local_provider,
                name="local_llm",
                supported_complexity=[TaskComplexity.LIGHT, TaskComplexity.MEDIUM],
                priority=10,
                cost_tier="free",
                max_tokens=2000,
            )
            logger.info("Local LLM provider initialized: %s (model=%s)", settings.LOCAL_LLM_ENDPOINT, settings.LOCAL_LLM_MODEL)

        if settings.OPENAI_API_KEY:
            openai_provider = __import__(
                "app.services.ai.openai_provider", fromlist=["OpenAIProvider"]
            ).OpenAIProvider(api_key=settings.OPENAI_API_KEY)
            self._providers.append(openai_provider)
            self._router.register(
                provider=openai_provider,
                name="openai",
                supported_complexity=[TaskComplexity.LIGHT, TaskComplexity.MEDIUM, TaskComplexity.HEAVY],
                priority=5,
                cost_tier="high",
                max_tokens=4000,
            )
            logger.info("OpenAI provider initialized")

        if settings.ANTHROPIC_API_KEY:
            anthropic_provider = AnthropicProvider(api_key=settings.ANTHROPIC_API_KEY)
            self._providers.append(anthropic_provider)
            self._router.register(
                provider=anthropic_provider,
                name="anthropic",
                supported_complexity=[TaskComplexity.LIGHT, TaskComplexity.MEDIUM, TaskComplexity.HEAVY],
                priority=5,
                cost_tier="high",
                max_tokens=4000,
            )
            logger.info("Anthropic provider initialized")

        if not self._providers:
            logger.warning("No AI provider configured. Set LOCAL_LLM_ENDPOINT, OPENAI_API_KEY, or ANTHROPIC_API_KEY.")

    @property
    def is_available(self) -> bool:
        return len(self._providers) > 0

    @property
    def router(self) -> TaskRouter:
        return self._router

    async def infer_journal(self, request: InferenceRequest) -> dict[str, Any]:
        """Infer journal lines with task routing and provider fallback.

        Returns:
            Dict with inference results, provider used, complexity, and confidence assessment.
        """
        if not self._providers:
            return {
                "status": "unavailable",
                "message": "AI provider not configured",
                "results": [],
            }

        return await self._router.infer_journal(
            request,
            prefer_free=settings.AI_PREFER_FREE,
        )

    async def predict_tax(self, description: str, amount: float) -> dict[str, Any]:
        """Predict tax category — routed to light-capable provider (prefer free)."""
        if not self._providers:
            return {"tax_type": "non_taxable", "tax_rate": 0, "confidence": 0, "status": "unavailable"}

        return await self._router.predict_tax(
            description, amount, prefer_free=settings.AI_PREFER_FREE
        )

    async def detect_anomaly(self, journal_data: dict) -> dict[str, Any]:
        """Detect anomalies — routed based on data size."""
        if not self._providers:
            return {"has_anomaly": False, "status": "unavailable"}

        return await self._router.detect_anomaly(
            journal_data, prefer_free=settings.AI_PREFER_FREE
        )

    def get_status(self) -> dict[str, Any]:
        """Get engine status including all providers and routing config."""
        return {
            "is_available": self.is_available,
            **self._router.get_status(),
            "prefer_free": settings.AI_PREFER_FREE,
        }


ai_engine = AIInferenceEngine()
