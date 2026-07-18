from app.services.ai.anthropic_provider import AnthropicProvider
from app.services.ai.inference_engine import AIInferenceEngine
from app.services.ai.local_llm_provider import LocalLLMProvider
from app.services.ai.openai_provider import OpenAIProvider


def _bare_engine(providers: list) -> AIInferenceEngine:
    """設定読み込み・ルータ登録を伴わずに _providers だけを持つインスタンスを作る。"""
    engine = object.__new__(AIInferenceEngine)
    engine._providers = providers
    return engine


class TestDocumentExtractionProvider:
    def test_returns_none_when_no_providers(self):
        assert _bare_engine([]).document_extraction_provider is None

    def test_skips_local_llm_provider_that_lacks_override(self):
        # LocalLLMProviderはextract_document_fieldsを実装していないため、
        # 先頭に登録されていてもドキュメント抽出には使われないこと
        local = LocalLLMProvider(endpoint_url="http://localhost:11434/v1", model="m", api_key="k")
        anthropic = AnthropicProvider(api_key="test-key")
        engine = _bare_engine([local, anthropic])
        assert engine.document_extraction_provider is anthropic

    def test_returns_none_when_only_local_llm_registered(self):
        local = LocalLLMProvider(endpoint_url="http://localhost:11434/v1", model="m", api_key="k")
        engine = _bare_engine([local])
        assert engine.document_extraction_provider is None

    def test_returns_first_capable_provider_in_registration_order(self):
        anthropic = AnthropicProvider(api_key="test-key")
        openai = OpenAIProvider(api_key="test-key")
        engine = _bare_engine([anthropic, openai])
        assert engine.document_extraction_provider is anthropic

        engine2 = _bare_engine([openai, anthropic])
        assert engine2.document_extraction_provider is openai
