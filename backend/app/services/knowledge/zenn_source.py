import logging
import re
from datetime import datetime
from typing import Any

import httpx

from app.services.knowledge.base_source import KnowledgeItem, KnowledgeSourceAdapter, SearchQuery

logger = logging.getLogger(__name__)


class ZennSourceAdapter(KnowledgeSourceAdapter):
    """Zenn — 日本語技術記事プラットフォームから最新情報を取得。

    Zennには公式APIがないため、公開RSS/検索ページをスクレイピングする。
    """

    BASE_URL = "https://zenn.dev"

    def __init__(self):
        pass

    @property
    def source_name(self) -> str:
        return "Zenn"

    @property
    def source_code(self) -> str:
        return "zenn"

    async def search(self, query: SearchQuery) -> list[KnowledgeItem]:
        keywords = "%20".join(query.keywords)
        items: list[KnowledgeItem] = []

        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                response = await client.get(
                    f"{self.BASE_URL}/search?q={keywords}",
                    headers={"Accept": "text/html"},
                )

            if response.status_code == 200:
                items = self._parse_search_results(response.text, query.max_results)

        except Exception as e:
            logger.warning("Zenn search failed: %s", e)

        return items[: query.max_results]

    def _parse_search_results(self, html: str, max_results: int) -> list[KnowledgeItem]:
        """Zenn検索結果ページをパースする。"""
        items: list[KnowledgeItem] = []

        article_pattern = re.compile(
            r'<a[^>]+href="(/articles/[^"]+)"[^>]*>.*?<h3[^>]*>(.*?)</h3>',
            re.DOTALL,
        )

        for match in article_pattern.finditer(html):
            if len(items) >= max_results:
                break
            path = match.group(1)
            title = re.sub(r"<[^>]+>", "", match.group(2)).strip()
            url = f"{self.BASE_URL}{path}"

            items.append(KnowledgeItem(
                title=title,
                url=url,
                source=self.source_code,
                content=title,
                summary=title,
                tags=[],
                relevance_score=0.5,
                metadata={"path": path},
            ))

        return items

    async def fetch_detail(self, url: str) -> KnowledgeItem:
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                response = await client.get(url, headers={"Accept": "text/html"})

            if response.status_code == 200:
                content = self._extract_article_content(response.text)
                title = self._extract_title(response.text)
                return KnowledgeItem(
                    title=title,
                    url=url,
                    source=self.source_code,
                    content=content[:5000],
                    summary=title,
                    tags=self._extract_tags(response.text),
                    relevance_score=0.5,
                )
        except Exception as e:
            logger.error("Zenn fetch_detail failed: %s", e)
        return KnowledgeItem(title="", url=url, source=self.source_code, content="")

    @staticmethod
    def _extract_article_content(html: str) -> str:
        content_match = re.search(r'<div[^>]*class="[^"]*articleBody[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL)
        if content_match:
            text = re.sub(r"<[^>]+>", "", content_match.group(1))
            return text.strip()
        return re.sub(r"<[^>]+>", "", html).strip()[:3000]

    @staticmethod
    def _extract_title(html: str) -> str:
        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.DOTALL)
        if title_match:
            return title_match.group(1).split(" - ")[0].strip()
        return ""

    @staticmethod
    def _extract_tags(html: str) -> list[str]:
        tag_matches = re.findall(r'href="/topics/([^"]+)"', html)
        return list(set(tag_matches))[:10]

    async def fetch_trending(self, limit: int = 10) -> list[KnowledgeItem]:
        """Zennのトレンド記事を取得する。"""
        items: list[KnowledgeItem] = []
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                response = await client.get(f"{self.BASE_URL}/", headers={"Accept": "text/html"})

            if response.status_code == 200:
                items = self._parse_search_results(response.text, limit)
                for item in items:
                    item.relevance_score = 0.8
                    item.metadata["trending"] = True

        except Exception as e:
            logger.warning("Zenn trending fetch failed: %s", e)
        return items

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(self.BASE_URL)
            return response.status_code == 200
        except Exception:
            return False
