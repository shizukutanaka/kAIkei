import logging
from datetime import datetime
from typing import Any

from app.services.knowledge.base_source import KnowledgeItem, SearchQuery
from app.services.knowledge.github_source import GitHubSourceAdapter
from app.services.knowledge.paper_source import PaperSourceAdapter
from app.services.knowledge.qiita_source import QiitaSourceAdapter
from app.services.knowledge.zenn_source import ZennSourceAdapter

logger = logging.getLogger(__name__)

DEFAULT_KEYWORDS: dict[str, list[str]] = {
    "accounting_ai": ["会計", "AI", "仕訳", "自動化"],
    "llm_finance": ["LLM", "finance", "accounting", "bookkeeping"],
    "japanese_tax": ["消費税", "軽減税率", "インボイス", "日本"],
    "erp_modern": ["ERP", "会計ソフト", "オープンソース", "Python"],
    "ai_bookkeeping": ["AI", "簿記", "仕訳推論", "機械学習"],
}


class KnowledgeAggregator:
    """複数の情報源からナレッジを統合取得するアグリゲータ。

    GitHub・Qiita・Zenn・論文（arXiv/Semantic Scholar）を横断検索し、
    結果を統合・ランキングしてAI推論のコンテキストとして提供する。
    """

    def __init__(
        self,
        github_token: str = "",
        qiita_token: str = "",
        use_semantic_scholar: bool = True,
    ):
        self._sources = {
            "github": GitHubSourceAdapter(token=github_token),
            "qiita": QiitaSourceAdapter(token=qiita_token),
            "zenn": ZennSourceAdapter(),
            "paper": PaperSourceAdapter(use_semantic_scholar=use_semantic_scholar),
        }

    @property
    def available_sources(self) -> list[str]:
        return list(self._sources.keys())

    async def search_all(
        self,
        keywords: list[str],
        domain: str = "accounting",
        language: str = "ja",
        max_per_source: int = 5,
    ) -> dict[str, Any]:
        """全情報源を横断検索し、統合結果を返す。"""
        query = SearchQuery(
            keywords=keywords,
            domain=domain,
            language=language,
            max_results=max_per_source,
        )

        results: dict[str, list[KnowledgeItem]] = {}
        errors: dict[str, str] = {}

        for code, adapter in self._sources.items():
            try:
                items = await adapter.search(query)
                results[code] = items
                logger.info("Source %s returned %d items", code, len(items))
            except Exception as e:
                errors[code] = str(e)
                results[code] = []
                logger.warning("Source %s failed: %s", code, e)

        all_items: list[KnowledgeItem] = []
        for items in results.values():
            all_items.extend(items)

        all_items.sort(key=lambda x: x.relevance_score, reverse=True)

        return {
            "query": {
                "keywords": keywords,
                "domain": domain,
                "language": language,
            },
            "total_results": len(all_items),
            "by_source": {
                code: len(items) for code, items in results.items()
            },
            "items": [
                {
                    "title": item.title,
                    "url": item.url,
                    "source": item.source,
                    "summary": item.summary,
                    "content_preview": item.content[:500],
                    "tags": item.tags,
                    "author": item.author,
                    "published_at": item.published_at.isoformat() if item.published_at else None,
                    "relevance_score": item.relevance_score,
                    "metadata": item.metadata,
                }
                for item in all_items
            ],
            "errors": errors if errors else None,
        }

    async def search_for_improvement(
        self,
        topic: str = "accounting_ai",
        max_per_source: int = 5,
    ) -> dict[str, Any]:
        """事前定義されたトピックで改善に役立つ情報を検索する。"""
        keywords = DEFAULT_KEYWORDS.get(topic, ["会計", "AI"])
        return await self.search_all(keywords, max_per_source=max_per_source)

    async def build_ai_context(
        self,
        keywords: list[str],
        max_items: int = 5,
    ) -> str:
        """AI推論プロンプトに組み込むナレッジコンテキストを構築する。"""
        result = await self.search_all(keywords, max_per_source=3)

        context_parts: list[str] = []
        for item in result["items"][:max_items]:
            context_parts.append(
                f"### {item['title']}\n"
                f"出典: {item['source']} ({item['url']})\n"
                f"概要: {item['summary']}\n"
                f"内容抜粋: {item['content_preview']}\n"
            )

        if context_parts:
            return "## 外部ナレッジ（最新技術動向）\n\n" + "\n".join(context_parts)
        return ""

    async def fetch_detail(self, source_code: str, url: str) -> dict[str, Any]:
        """特定の情報源から詳細情報を取得する。"""
        adapter = self._sources.get(source_code)
        if not adapter:
            return {"error": f"Unknown source: {source_code}"}

        try:
            item = await adapter.fetch_detail(url)
            return {
                "title": item.title,
                "url": item.url,
                "source": item.source,
                "content": item.content,
                "summary": item.summary,
                "tags": item.tags,
                "author": item.author,
                "published_at": item.published_at.isoformat() if item.published_at else None,
                "metadata": item.metadata,
            }
        except Exception as e:
            return {"error": str(e)}

    async def health_check_all(self) -> dict[str, bool]:
        """全情報源の可用性を確認する。"""
        results: dict[str, bool] = {}
        for code, adapter in self._sources.items():
            try:
                results[code] = await adapter.health_check()
            except Exception:
                results[code] = False
        return results

    def get_topics(self) -> list[dict[str, Any]]:
        """事前定義された検索トピック一覧を取得する。"""
        return [
            {"topic": k, "keywords": v, "description": f"{k}に関する最新情報"}
            for k, v in DEFAULT_KEYWORDS.items()
        ]


knowledge_aggregator = KnowledgeAggregator()
