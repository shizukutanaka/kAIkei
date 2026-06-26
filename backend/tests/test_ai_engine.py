import pytest

from app.services.ai.base_provider import InferenceRequest
from app.services.ai.inference_engine import AIInferenceEngine


class TestAIInferenceEngine:
    def test_no_providers_configured(self):
        engine = AIInferenceEngine()
        if not engine.is_available:
            import asyncio

            request = InferenceRequest(
                description="現金売上 10000円",
                amount=10000,
                transaction_date="2026-06-26",
            )
            result = asyncio.get_event_loop().run_until_complete(engine.infer_journal(request))
            assert result["status"] == "unavailable"
            assert result["results"] == []

    def test_predict_tax_unavailable(self):
        engine = AIInferenceEngine()
        if not engine.is_available:
            import asyncio

            result = asyncio.get_event_loop().run_until_complete(
                engine.predict_tax("現金売上", 10000)
            )
            assert result["status"] == "unavailable"
            assert result["tax_type"] == "non_taxable"

    def test_detect_anomaly_unavailable(self):
        engine = AIInferenceEngine()
        if not engine.is_available:
            import asyncio

            result = asyncio.get_event_loop().run_until_complete(
                engine.detect_anomaly({"amount": 10000})
            )
            assert result["status"] == "unavailable"
            assert result["has_anomaly"] is False
