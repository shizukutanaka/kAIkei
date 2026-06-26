from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.services.knowledge.aggregator import knowledge_aggregator

router = APIRouter()


class SearchRequest(BaseModel):
    keywords: list[str]
    domain: str = "accounting"
    language: str = "ja"
    max_per_source: int = 5


@router.get("/topics")
async def get_topics() -> dict:
    """事前定義された検索トピック一覧を取得する。"""
    return {"topics": knowledge_aggregator.get_topics()}


@router.get("/sources")
async def get_sources() -> dict:
    """利用可能な情報源一覧を取得する。"""
    return {"sources": knowledge_aggregator.available_sources}


@router.get("/health")
async def health_check() -> dict:
    """全情報源の可用性を確認する。"""
    results = await knowledge_aggregator.health_check_all()
    return {"sources": results, "all_healthy": all(results.values())}


@router.post("/search")
async def search_knowledge(payload: SearchRequest) -> dict:
    """全情報源を横断検索する。"""
    return await knowledge_aggregator.search_all(
        keywords=payload.keywords,
        domain=payload.domain,
        language=payload.language,
        max_per_source=payload.max_per_source,
    )


@router.get("/search")
async def search_knowledge_get(
    keywords: str = Query(..., description="カンマ区切りのキーワード"),
    domain: str = Query("accounting"),
    language: str = Query("ja"),
    max_per_source: int = Query(5, le=20),
) -> dict:
    """GET でナレッジ検索（カンマ区切りキーワード）。"""
    keyword_list = [k.strip() for k in keywords.split(",") if k.strip()]
    return await knowledge_aggregator.search_all(
        keywords=keyword_list,
        domain=domain,
        language=language,
        max_per_source=max_per_source,
    )


@router.get("/improvement/{topic}")
async def search_for_improvement(
    topic: str,
    max_per_source: int = Query(5, le=20),
) -> dict:
    """事前定義トピックで改善情報を検索する。

    トピック例: accounting_ai, llm_finance, japanese_tax, erp_modern, ai_bookkeeping
    """
    return await knowledge_aggregator.search_for_improvement(topic, max_per_source)


@router.get("/detail/{source_code}")
async def fetch_detail(source_code: str, url: str = Query(...)) -> dict:
    """特定の情報源から詳細情報を取得する。"""
    return await knowledge_aggregator.fetch_detail(source_code, url)


@router.post("/ai-context")
async def build_ai_context(payload: SearchRequest) -> dict:
    """AI推論プロンプト用のナレッジコンテキストを構築する。"""
    context = await knowledge_aggregator.build_ai_context(
        keywords=payload.keywords,
        max_items=5,
    )
    return {"context": context, "keywords": payload.keywords}
