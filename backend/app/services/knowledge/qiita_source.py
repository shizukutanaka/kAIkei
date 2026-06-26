import logging
import re
from datetime import datetime
from typing import Any

import httpx

from app.services.knowledge.base_source import KnowledgeItem, KnowledgeSourceAdapter, SearchQuery

logger = logging.getLogger(__name__)


class QiitaSourceAdapter(KnowledgeSourceAdapter):
    """Qiita — 日本語技術記事APIから最新情報を取得。"""

    API_BASE = "https://qiita.com/api/v2"

    def __init__(self, token: str = ""):
        self._token = token

    @property
    def source_name(self) -> str:
        return "Qiita"

    @property
    def source_code(self) -> str:
        return "qiita"

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    async def search(self, query: SearchQuery) -> list[KnowledgeItem]:
        keywords = " ".join(query.keywords)
        items: list[KnowledgeItem] = []

        try:
            params: dict[str, Any] = {
                "page": 1,
                "per_page": min(query.max_results, 100),
                "sort": "stock",
            }

            if query.language == "ja":
                params["query"] = f"title:{keywords} OR body:{keywords}"
            else:
                params["query"] = keywords

            if query.date_from:
                params["query"] += f" created:>{query.date_from.strftime('%Y-%m-%d')}"

            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(
                    f"{self.API_BASE}/items",
                    headers=self._headers(),
                    params=params,
                )

            if response.status_code == 200:
                for article in response.json():
                    body_text = self._strip_html(article.get("rendered_body", ""))
                    items.append(KnowledgeItem(
                        title=article["title"],
                        url=article["url"],
                        source=self.source_code,
                        content=body_text[:3000],
                        summary=article.get("title", ""),
                        tags=[t["name"] for t in article.get("tags", [])],
                        published_at=datetime.fromisoformat(article["created_at"].replace("Z", "+00:00")) if article.get("created_at") else None,
                        author=article.get("user", {}).get("id", ""),
                        relevance_score=float(article.get("likes_count", 0)) / 100,
                        metadata={
                            "likes": article.get("likes_count", 0),
                            "stocks": article.get("stocks_count", 0),
                            "comments": article.get("comments_count", 0),
                        },
                    ))

        except Exception as e:
            logger.warning("Qiita search failed: %s", e)

        return items[: query.max_results]

    async def fetch_detail(self, url: str) -> KnowledgeItem:
        item_id = url.rstrip("/").split("/")[-1]
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(
                    f"{self.API_BASE}/items/{item_id}",
                    headers=self._headers(),
                )
            if response.status_code == 200:
                article = response.json()
                body_text = self._strip_html(article.get("rendered_body", ""))
                return KnowledgeItem(
                    title=article["title"],
                    url=article["url"],
                    source=self.source_code,
                    content=body_text[:5000],
                    summary=article.get("title", ""),
                    tags=[t["name"] for t in article.get("tags", [])],
                    published_at=datetime.fromisoformat(article["created_at"].replace("Z", "+00:00")),
                    author=article.get("user", {}).get("id", ""),
                    metadata={
                        "likes": article.get("likes_count", 0),
                        "stocks": article.get("stocks_count", 0),
                    },
                )
        except Exception as e:
            logger.error("Qiita fetch_detail failed: %s", e)
        return KnowledgeItem(title="", url=url, source=self.source_code, content="")

    @staticmethod
    def _strip_html(html: str) -> str:
        return re.sub(r"<[^>]+>", "", html).strip()

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self.API_BASE}/authenticated_user", headers=self._headers())
            return response.status_code in (200, 401)
        except Exception:
            return False
