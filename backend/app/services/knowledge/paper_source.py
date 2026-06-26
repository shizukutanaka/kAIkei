import logging
from datetime import datetime
from typing import Any

import httpx

from app.services.knowledge.base_source import KnowledgeItem, KnowledgeSourceAdapter, SearchQuery

logger = logging.getLogger(__name__)


class PaperSourceAdapter(KnowledgeSourceAdapter):
    """arXiv・Semantic Scholar APIから最新論文を取得。"""

    ARXIV_API = "http://export.arxiv.org/api/query"
    SEMANTIC_SCHOLAR_API = "https://api.semanticscholar.org/graph/v1"

    def __init__(self, use_semantic_scholar: bool = True):
        self._use_ss = use_semantic_scholar

    @property
    def source_name(self) -> str:
        return "論文 (arXiv / Semantic Scholar)"

    @property
    def source_code(self) -> str:
        return "paper"

    async def search(self, query: SearchQuery) -> list[KnowledgeItem]:
        keywords = " ".join(query.keywords)
        items: list[KnowledgeItem] = []

        if self._use_ss:
            items = await self._search_semantic_scholar(keywords, query.max_results)
            if items:
                return items

        items = await self._search_arxiv(keywords, query.max_results)
        return items

    async def _search_arxiv(self, keywords: str, max_results: int) -> list[KnowledgeItem]:
        items: list[KnowledgeItem] = []
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.get(
                    self.ARXIV_API,
                    params={
                        "search_query": f"all:{keywords}",
                        "start": 0,
                        "max_results": max_results,
                        "sortBy": "submittedDate",
                        "sortOrder": "descending",
                    },
                )

            if response.status_code == 200:
                items = self._parse_arxiv_response(response.text)

        except Exception as e:
            logger.warning("arXiv search failed: %s", e)
        return items

    def _parse_arxiv_response(self, xml_text: str) -> list[KnowledgeItem]:
        """arXiv APIのAtom XMLレスポンスをパースする。"""
        import xml.etree.ElementTree as ET

        items: list[KnowledgeItem] = []
        ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}

        try:
            root = ET.fromstring(xml_text)
            for entry in root.findall("atom:entry", ns):
                title = entry.find("atom:title", ns)
                summary = entry.find("atom:summary", ns)
                published = entry.find("atom:published", ns)
                authors = entry.findall("atom:author/atom:name", ns)
                link = entry.find("atom:id", ns)
                categories = entry.findall("atom:category", ns)

                title_text = title.text.strip().replace("\n", " ") if title is not None else ""
                summary_text = summary.text.strip().replace("\n", " ") if summary is not None else ""
                url = link.text.strip() if link is not None else ""
                pub_date = None
                if published is not None and published.text:
                    pub_date = datetime.fromisoformat(published.text.replace("Z", "+00:00"))

                author_names = [a.text.strip() for a in authors if a.text]
                tags = [c.get("term", "") for c in categories if c.get("term")]

                items.append(KnowledgeItem(
                    title=title_text,
                    url=url,
                    source=self.source_code,
                    content=summary_text[:3000],
                    summary=summary_text[:200],
                    tags=tags,
                    published_at=pub_date,
                    author=", ".join(author_names[:3]),
                    relevance_score=0.7,
                    metadata={"arxiv_id": url.split("/")[-1] if url else ""},
                ))
        except Exception as e:
            logger.warning("arXiv XML parse failed: %s", e)

        return items

    async def _search_semantic_scholar(self, keywords: str, max_results: int) -> list[KnowledgeItem]:
        items: list[KnowledgeItem] = []
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(
                    f"{self.SEMANTIC_SCHOLAR_API}/paper/search",
                    params={
                        "query": keywords,
                        "limit": max_results,
                        "fields": "title,abstract,url,year,authors,citationCount,publicationDate,fieldsOfStudy",
                    },
                )

            if response.status_code == 200:
                data = response.json()
                for paper in data.get("data", []):
                    pub_date = None
                    if paper.get("publicationDate"):
                        try:
                            pub_date = datetime.fromisoformat(paper["publicationDate"])
                        except ValueError:
                            pass

                    authors = [a.get("name", "") for a in paper.get("authors", [])[:5]]

                    items.append(KnowledgeItem(
                        title=paper.get("title", ""),
                        url=paper.get("url", ""),
                        source=self.source_code,
                        content=paper.get("abstract", "")[:3000],
                        summary=paper.get("abstract", "")[:200] if paper.get("abstract") else paper.get("title", ""),
                        tags=paper.get("fieldsOfStudy", []),
                        published_at=pub_date,
                        author=", ".join(authors),
                        relevance_score=min(float(paper.get("citationCount", 0)) / 100, 1.0),
                        metadata={
                            "year": paper.get("year"),
                            "citation_count": paper.get("citationCount", 0),
                            "fields": paper.get("fieldsOfStudy", []),
                        },
                    ))

        except Exception as e:
            logger.warning("Semantic Scholar search failed: %s", e)
        return items

    async def fetch_detail(self, url: str) -> KnowledgeItem:
        arxiv_id = url.split("/")[-1] if "arxiv.org" in url else ""
        if arxiv_id:
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    response = await client.get(
                        self.ARXIV_API,
                        params={"id_list": arxiv_id},
                    )
                if response.status_code == 200:
                    items = self._parse_arxiv_response(response.text)
                    if items:
                        items[0].content = items[0].content[:5000]
                        return items[0]
            except Exception as e:
                logger.error("arXiv fetch_detail failed: %s", e)
        return KnowledgeItem(title="", url=url, source=self.source_code, content="")

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(self.ARXIV_API, params={"max_results": 1})
            return response.status_code == 200
        except Exception:
            return False
