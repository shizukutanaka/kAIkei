from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class KnowledgeItem:
    """取得したナレッジアイテム。"""
    title: str
    url: str
    source: str  # "github" | "qiita" | "zenn" | "paper" | "doc"
    content: str
    summary: str = ""
    tags: list[str] = field(default_factory=list)
    published_at: datetime | None = None
    author: str = ""
    relevance_score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchQuery:
    """ナレッジ検索クエリ。"""
    keywords: list[str]
    domain: str = "accounting"  # accounting, tax, llm, ai, erp
    language: str = "ja"  # ja, en
    max_results: int = 10
    date_from: datetime | None = None
    date_to: datetime | None = None


class KnowledgeSourceAdapter(ABC):
    """外部情報源からのナレッジ取得アダプタの抽象基底クラス。"""

    @property
    @abstractmethod
    def source_name(self) -> str:
        """情報源名。"""
        pass

    @property
    @abstractmethod
    def source_code(self) -> str:
        """情報源コード。"""
        pass

    @abstractmethod
    async def search(self, query: SearchQuery) -> list[KnowledgeItem]:
        """キーワードに基づいてナレッジを検索・取得する。"""
        pass

    @abstractmethod
    async def fetch_detail(self, url: str) -> KnowledgeItem:
        """特定のURLから詳細情報を取得する。"""
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """情報源の可用性を確認する。"""
        pass
