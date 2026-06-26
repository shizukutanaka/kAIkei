import pytest

from app.services.ai.base_provider import AIProvider, InferenceRequest, InferenceResult
from app.services.ai.task_router import TaskComplexity, TaskRouter


class MockProvider(AIProvider):
    """Mock provider for testing."""

    def __init__(self, name: str, fail: bool = False):
        self._name = name
        self._fail = fail

    async def infer_journal(self, request: InferenceRequest) -> list[InferenceResult]:
        if self._fail:
            raise RuntimeError(f"{self._name} failed")
        return [
            InferenceResult(
                account_code="1110",
                account_name="現金",
                debit_credit="debit",
                amount=request.amount,
                tax_rate=0.10,
                tax_type="tax_10_ex",
                confidence=0.85,
                reasoning=f"Inferred by {self._name}",
            ),
            InferenceResult(
                account_code="4110",
                account_name="売上",
                debit_credit="credit",
                amount=request.amount,
                tax_rate=0.10,
                tax_type="tax_10_ex",
                confidence=0.85,
                reasoning=f"Inferred by {self._name}",
            ),
        ]

    async def predict_tax(self, description: str, amount: float) -> dict:
        if self._fail:
            raise RuntimeError(f"{self._name} failed")
        return {"tax_type": "tax_10_ex", "tax_rate": 0.10, "confidence": 0.9}

    async def detect_anomaly(self, journal_data: dict) -> dict:
        if self._fail:
            raise RuntimeError(f"{self._name} failed")
        return {"has_anomaly": False, "anomalies": []}


class TestTaskRouter:
    def test_register_and_select(self):
        router = TaskRouter()
        local = MockProvider("local")
        cloud = MockProvider("cloud")

        router.register(local, "local_llm", [TaskComplexity.LIGHT, TaskComplexity.MEDIUM], priority=10, cost_tier="free")
        router.register(cloud, "openai", [TaskComplexity.LIGHT, TaskComplexity.MEDIUM, TaskComplexity.HEAVY], priority=5, cost_tier="high")

        assert router.available_providers == ["local_llm", "openai"]

    def test_select_prefers_free_for_light(self):
        router = TaskRouter()
        local = MockProvider("local")
        cloud = MockProvider("cloud")

        router.register(local, "local_llm", [TaskComplexity.LIGHT], priority=10, cost_tier="free")
        router.register(cloud, "openai", [TaskComplexity.LIGHT, TaskComplexity.HEAVY], priority=5, cost_tier="high")

        selected = router.select_provider(TaskComplexity.LIGHT, prefer_free=True)
        assert selected.name == "local_llm"

    def test_select_falls_back_to_cloud_for_heavy(self):
        router = TaskRouter()
        local = MockProvider("local")
        cloud = MockProvider("cloud")

        router.register(local, "local_llm", [TaskComplexity.LIGHT], priority=10, cost_tier="free")
        router.register(cloud, "openai", [TaskComplexity.LIGHT, TaskComplexity.HEAVY], priority=5, cost_tier="high")

        selected = router.select_provider(TaskComplexity.HEAVY, prefer_free=True)
        assert selected.name == "openai"

    def test_select_returns_none_when_no_match(self):
        router = TaskRouter()
        local = MockProvider("local")
        router.register(local, "local_llm", [TaskComplexity.LIGHT], priority=10, cost_tier="free")

        selected = router.select_provider(TaskComplexity.HEAVY)
        assert selected is None

    def test_classify_task_light(self):
        router = TaskRouter()
        request = InferenceRequest(
            description="現金売上",
            amount=10000,
            transaction_date="2026-06-26",
        )
        assert router.classify_task(request) == TaskComplexity.LIGHT

    def test_classify_task_heavy(self):
        router = TaskRouter()
        request = InferenceRequest(
            description="複雑な取引",
            amount=50000,
            transaction_date="2026-06-26",
            document_text="x" * 1500,
        )
        assert router.classify_task(request) == TaskComplexity.HEAVY

    def test_classify_task_medium(self):
        router = TaskRouter()
        request = InferenceRequest(
            description="電気代支払い - 東京電力 - 4月分",
            amount=15000,
            transaction_date="2026-06-26",
        )
        assert router.classify_task(request) == TaskComplexity.MEDIUM

    def test_infer_routes_to_local_for_light(self):
        import asyncio

        router = TaskRouter()
        local = MockProvider("local")
        cloud = MockProvider("cloud")

        router.register(local, "local_llm", [TaskComplexity.LIGHT, TaskComplexity.MEDIUM], priority=10, cost_tier="free")
        router.register(cloud, "openai", [TaskComplexity.LIGHT, TaskComplexity.MEDIUM, TaskComplexity.HEAVY], priority=5, cost_tier="high")

        request = InferenceRequest(
            description="現金売上",
            amount=10000,
            transaction_date="2026-06-26",
        )
        result = asyncio.get_event_loop().run_until_complete(router.infer_journal(request))
        assert result["provider"] == "local_llm"
        assert result["complexity"] == "light"
        assert result["cost_tier"] == "free"

    def test_infer_fallback_on_failure(self):
        import asyncio

        router = TaskRouter()
        local = MockProvider("local", fail=True)
        cloud = MockProvider("cloud")

        router.register(local, "local_llm", [TaskComplexity.LIGHT], priority=10, cost_tier="free")
        router.register(cloud, "openai", [TaskComplexity.LIGHT], priority=5, cost_tier="high")

        request = InferenceRequest(
            description="現金売上",
            amount=10000,
            transaction_date="2026-06-26",
        )
        result = asyncio.get_event_loop().run_until_complete(router.infer_journal(request))
        assert result["provider"] == "openai"
        assert result.get("fallback") is True

    def test_get_status(self):
        router = TaskRouter()
        local = MockProvider("local")
        router.register(local, "local_llm", [TaskComplexity.LIGHT], priority=10, cost_tier="free")

        status = router.get_status()
        assert status["total_providers"] == 1
        assert status["providers"][0]["name"] == "local_llm"
        assert status["providers"][0]["cost_tier"] == "free"
