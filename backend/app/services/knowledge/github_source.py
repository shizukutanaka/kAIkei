import logging
from datetime import datetime
from typing import Any

import httpx

from app.services.knowledge.base_source import KnowledgeItem, KnowledgeSourceAdapter, SearchQuery

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"


class GitHubSourceAdapter(KnowledgeSourceAdapter):
    """GitHub — リポジトリ・Issue・Release・READMEから最新情報を取得。"""

    def __init__(self, token: str = ""):
        self._token = token

    @property
    def source_name(self) -> str:
        return "GitHub"

    @property
    def source_code(self) -> str:
        return "github"

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/vnd.github+json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    async def search(self, query: SearchQuery) -> list[KnowledgeItem]:
        keywords = " ".join(query.keywords)
        search_query = f"{keywords} in:readme,description"

        if query.domain == "accounting":
            search_query += " topic:accounting OR topic:erp OR topic:bookkeeping"
        elif query.domain == "llm":
            search_query += " topic:llm OR topic:ai OR topic:machine-learning"
        elif query.domain == "tax":
            search_query += " topic:tax OR topic:consumption-tax"

        items: list[KnowledgeItem] = []

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(
                    f"{GITHUB_API}/search/repositories",
                    headers=self._headers(),
                    params={
                        "q": search_query,
                        "sort": "updated",
                        "order": "desc",
                        "per_page": min(query.max_results, 30),
                    },
                )

            if response.status_code == 200:
                data = response.json()
                for repo in data.get("items", []):
                    items.append(KnowledgeItem(
                        title=repo["full_name"],
                        url=repo["html_url"],
                        source=self.source_code,
                        content=repo.get("description", ""),
                        summary=repo.get("description", ""),
                        tags=repo.get("topics", []),
                        published_at=datetime.fromisoformat(repo["updated_at"].replace("Z", "+00:00")) if repo.get("updated_at") else None,
                        author=repo.get("owner", {}).get("login", ""),
                        relevance_score=float(repo.get("stargazers_count", 0)) / 10000,
                        metadata={
                            "stars": repo.get("stargazers_count", 0),
                            "forks": repo.get("forks_count", 0),
                            "language": repo.get("language", ""),
                            "license": repo.get("license", {}).get("name", "") if repo.get("license") else "",
                        },
                    ))

        except Exception as e:
            logger.warning("GitHub search failed: %s", e)

        return items[: query.max_results]

    async def fetch_detail(self, url: str) -> KnowledgeItem:
        owner_repo = url.replace("https://github.com/", "").rstrip("/")
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                repo_resp = await client.get(f"{GITHUB_API}/repos/{owner_repo}", headers=self._headers())
                readme_resp = await client.get(
                    f"{GITHUB_API}/repos/{owner_repo}/readme",
                    headers={**self._headers(), "Accept": "application/vnd.github.raw"},
                )

            repo = repo_resp.json()
            readme = readme_resp.text if readme_resp.status_code == 200 else ""

            return KnowledgeItem(
                title=repo["full_name"],
                url=repo["html_url"],
                source=self.source_code,
                content=readme[:5000],
                summary=repo.get("description", ""),
                tags=repo.get("topics", []),
                published_at=datetime.fromisoformat(repo["updated_at"].replace("Z", "+00:00")) if repo.get("updated_at") else None,
                author=repo.get("owner", {}).get("login", ""),
                metadata={
                    "stars": repo.get("stargazers_count", 0),
                    "forks": repo.get("forks_count", 0),
                    "language": repo.get("language", ""),
                },
            )
        except Exception as e:
            logger.error("GitHub fetch_detail failed: %s", e)
            return KnowledgeItem(title="", url=url, source=self.source_code, content="")

    async def fetch_latest_releases(self, owner: str, repo: str, limit: int = 5) -> list[KnowledgeItem]:
        """特定リポジトリの最新リリースノートを取得する。"""
        items: list[KnowledgeItem] = []
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(
                    f"{GITHUB_API}/repos/{owner}/{repo}/releases",
                    headers=self._headers(),
                    params={"per_page": limit},
                )
            if response.status_code == 200:
                for release in response.json():
                    items.append(KnowledgeItem(
                        title=f"{owner}/{repo} - {release['tag_name']}",
                        url=release["html_url"],
                        source=self.source_code,
                        content=release.get("body", "")[:3000],
                        summary=release.get("name", release["tag_name"]),
                        published_at=datetime.fromisoformat(release["published_at"].replace("Z", "+00:00")) if release.get("published_at") else None,
                        author=release.get("author", {}).get("login", ""),
                        metadata={"tag": release["tag_name"], "prerelease": release.get("prerelease", False)},
                    ))
        except Exception as e:
            logger.warning("GitHub releases fetch failed: %s", e)
        return items

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{GITHUB_API}/rate_limit", headers=self._headers())
            return response.status_code == 200
        except Exception:
            return False
