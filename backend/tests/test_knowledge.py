import pytest

from app.services.knowledge.base_source import KnowledgeItem, SearchQuery
from app.services.knowledge.aggregator import KnowledgeAggregator, DEFAULT_KEYWORDS


class TestKnowledgeAggregator:
    def test_available_sources(self):
        agg = KnowledgeAggregator()
        sources = agg.available_sources
        assert "github" in sources
        assert "qiita" in sources
        assert "zenn" in sources
        assert "paper" in sources

    def test_get_topics(self):
        agg = KnowledgeAggregator()
        topics = agg.get_topics()
        assert len(topics) >= 5
        topic_keys = [t["topic"] for t in topics]
        assert "accounting_ai" in topic_keys
        assert "llm_finance" in topic_keys
        assert "japanese_tax" in topic_keys

    def test_default_keywords(self):
        assert "accounting_ai" in DEFAULT_KEYWORDS
        assert "会計" in DEFAULT_KEYWORDS["accounting_ai"]
        assert "llm_finance" in DEFAULT_KEYWORDS
        assert "LLM" in DEFAULT_KEYWORDS["llm_finance"]


class TestKnowledgeItem:
    def test_creation(self):
        item = KnowledgeItem(
            title="Test Article",
            url="https://example.com/article",
            source="qiita",
            content="This is a test article about accounting AI.",
            summary="Test summary",
            tags=["AI", "accounting"],
            author="test_user",
            relevance_score=0.8,
        )
        assert item.title == "Test Article"
        assert item.source == "qiita"
        assert len(item.tags) == 2
        assert item.relevance_score == 0.8

    def test_default_tags(self):
        item = KnowledgeItem(
            title="Test",
            url="https://example.com",
            source="github",
            content="content",
        )
        assert item.tags == []
        assert item.metadata == {}


class TestSearchQuery:
    def test_creation(self):
        query = SearchQuery(
            keywords=["会計", "AI"],
            domain="accounting",
            language="ja",
            max_results=10,
        )
        assert query.keywords == ["会計", "AI"]
        assert query.domain == "accounting"
        assert query.language == "ja"
        assert query.max_results == 10

    def test_defaults(self):
        query = SearchQuery(keywords=["test"])
        assert query.domain == "accounting"
        assert query.language == "ja"
        assert query.max_results == 10
        assert query.date_from is None
