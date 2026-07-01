import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.services.ai.base_provider import AIProvider, InferenceRequest

logger = logging.getLogger(__name__)


class TaskComplexity(str, Enum):
    """タスクの複雑さレベル。"""
    LIGHT = "light"
    MEDIUM = "medium"
    HEAVY = "heavy"


@dataclass
class ProviderCapability:
    """プロバイダーの能力定義。"""
    provider: AIProvider
    name: str
    supported_complexity: list[TaskComplexity]
    priority: int
    cost_tier: str  # "free", "low", "high"
    max_tokens: int


class TaskRouter:
    """タスクの複雑さに応じて最適なAIプロバイダーを振り分けるルーター。

    軽量タスク（税区分判定・简单な異常検知等）はローカルLLMに割り当て、
    重いタスク（仕訳推論・過去仕訳コンテキスト推論等）はクラウドLLMに割り当てる。
    """

    def __init__(self) -> None:
        self._providers: list[ProviderCapability] = []

    def register(
        self,
        provider: AIProvider,
        name: str,
        supported_complexity: list[TaskComplexity],
        priority: int = 0,
        cost_tier: str = "high",
        max_tokens: int = 2000,
    ) -> None:
        """プロバイダーを登録する。"""
        self._providers.append(
            ProviderCapability(
                provider=provider,
                name=name,
                supported_complexity=supported_complexity,
                priority=priority,
                cost_tier=cost_tier,
                max_tokens=max_tokens,
            )
        )
        self._providers.sort(key=lambda p: (-p.priority, p.cost_tier))

    @property
    def available_providers(self) -> list[str]:
        return [p.name for p in self._providers]

    def select_provider(
        self,
        complexity: TaskComplexity,
        prefer_free: bool = True,
    ) -> ProviderCapability | None:
        """タスク複雑度に応じた最適プロバイダーを選択する。

        優先順位:
        1. prefer_free=Trueの場合、cost_tier="free"のプロバイダーを優先
        2. 対応するcomplexityをサポートするプロバイダーの中からpriorityが高いもの
        3. 該当するプロバイダーがない場合はNone
        """
        candidates = [p for p in self._providers if complexity in p.supported_complexity]

        if not candidates:
            return None

        if prefer_free:
            free_candidates = [p for p in candidates if p.cost_tier == "free"]
            if free_candidates:
                return free_candidates[0]

        return candidates[0]

    def classify_task(self, request: InferenceRequest) -> TaskComplexity:
        """推論リクエストからタスクの複雑さを自動判定する。

        判定基準:
        - document_textが長い（>1000文字）→ HEAVY
        - descriptionが短く区切りの無い単純な摘要で金額が単純 → LIGHT
        - それ以外（構造化された摘要・長い摘要・添付テキスト有り）→ MEDIUM
        """
        text_len = len(request.document_text or "")
        description = request.description or ""
        desc_len = len(description)

        if text_len > 1000:
            return TaskComplexity.HEAVY

        has_structure = any(sep in description for sep in (" - ", "-", "/", "、", ",", "："))

        if text_len == 0 and request.amount > 0 and desc_len < 10 and not has_structure:
            return TaskComplexity.LIGHT

        return TaskComplexity.MEDIUM

    async def infer_journal(
        self,
        request: InferenceRequest,
        complexity: TaskComplexity | None = None,
        prefer_free: bool = True,
    ) -> dict[str, Any]:
        """タスクルーティング付き仕訳推論。"""
        if complexity is None:
            complexity = self.classify_task(request)

        cap = self.select_provider(complexity, prefer_free)
        if not cap:
            return {
                "status": "unavailable",
                "message": f"No provider available for complexity={complexity.value}",
                "results": [],
            }

        try:
            results = await cap.provider.infer_journal(request)

            debit_total = sum(r.amount for r in results if r.debit_credit == "debit")
            credit_total = sum(r.amount for r in results if r.debit_credit == "credit")
            avg_confidence = sum(r.confidence for r in results) / len(results) if results else 0
            is_balanced = abs(debit_total - credit_total) < 1
            needs_review = avg_confidence < 0.7 or not is_balanced

            return {
                "status": "needs_review" if needs_review else "auto_approved",
                "provider": cap.name,
                "complexity": complexity.value,
                "cost_tier": cap.cost_tier,
                "results": [
                    {
                        "account_code": r.account_code,
                        "account_name": r.account_name,
                        "debit_credit": r.debit_credit,
                        "amount": r.amount,
                        "tax_rate": r.tax_rate,
                        "tax_type": r.tax_type,
                        "confidence": r.confidence,
                        "reasoning": r.reasoning,
                    }
                    for r in results
                ],
                "debit_total": debit_total,
                "credit_total": credit_total,
                "is_balanced": is_balanced,
                "avg_confidence": avg_confidence,
                "needs_human_review": needs_review,
            }

        except Exception as e:
            logger.warning("Provider %s failed for %s task, trying fallback: %s", cap.name, complexity.value, e)

            fallback = self._get_fallback(cap, complexity)
            if fallback:
                try:
                    results = await fallback.provider.infer_journal(request)
                    return {
                        "status": "needs_review",
                        "provider": fallback.name,
                        "complexity": complexity.value,
                        "cost_tier": fallback.cost_tier,
                        "fallback": True,
                        "results": [
                            {
                                "account_code": r.account_code,
                                "account_name": r.account_name,
                                "debit_credit": r.debit_credit,
                                "amount": r.amount,
                                "tax_rate": r.tax_rate,
                                "tax_type": r.tax_type,
                                "confidence": r.confidence,
                                "reasoning": r.reasoning,
                            }
                            for r in results
                        ],
                        "debit_total": sum(r.amount for r in results if r.debit_credit == "debit"),
                        "credit_total": sum(r.amount for r in results if r.debit_credit == "credit"),
                        "is_balanced": abs(
                            sum(r.amount for r in results if r.debit_credit == "debit")
                            - sum(r.amount for r in results if r.debit_credit == "credit")
                        ) < 1,
                        "avg_confidence": sum(r.confidence for r in results) / len(results) if results else 0,
                        "needs_human_review": True,
                    }
                except Exception as e2:
                    logger.error("Fallback provider %s also failed: %s", fallback.name, e2)

            return {
                "status": "error",
                "message": str(e),
                "provider": cap.name,
                "complexity": complexity.value,
                "results": [],
            }

    async def predict_tax(
        self,
        description: str,
        amount: float,
        prefer_free: bool = True,
    ) -> dict[str, Any]:
        """税務予測 — 軽量タスクとして扱い、ローカルLLMを優先。"""
        cap = self.select_provider(TaskComplexity.LIGHT, prefer_free)
        if not cap:
            cap = self.select_provider(TaskComplexity.MEDIUM, prefer_free)
        if not cap:
            return {"tax_type": "non_taxable", "tax_rate": 0, "confidence": 0, "status": "unavailable"}

        try:
            result = await cap.provider.predict_tax(description, amount)
            result["provider"] = cap.name
            result["cost_tier"] = cap.cost_tier
            result["status"] = "success"
            return result
        except Exception as e:
            logger.warning("Tax prediction provider %s failed: %s", cap.name, e)
            return {"tax_type": "non_taxable", "tax_rate": 0, "confidence": 0, "status": "error", "message": str(e)}

    async def detect_anomaly(
        self,
        journal_data: dict,
        prefer_free: bool = True,
    ) -> dict[str, Any]:
        """異常検知 — データサイズに応じてLIGHTまたはMEDIUM。"""
        data_size = len(str(journal_data))
        complexity = TaskComplexity.LIGHT if data_size < 500 else TaskComplexity.MEDIUM

        cap = self.select_provider(complexity, prefer_free)
        if not cap:
            return {"has_anomaly": False, "status": "unavailable"}

        try:
            result = await cap.provider.detect_anomaly(journal_data)
            result["provider"] = cap.name
            result["cost_tier"] = cap.cost_tier
            result["status"] = "success"
            return result
        except Exception as e:
            logger.warning("Anomaly detection provider %s failed: %s", cap.name, e)
            return {"has_anomaly": False, "status": "error", "message": str(e)}

    def _get_fallback(
        self,
        failed: ProviderCapability,
        complexity: TaskComplexity,
    ) -> ProviderCapability | None:
        """失敗したプロバイダー以外のフォールバックを取得。"""
        candidates = [
            p for p in self._providers
            if p != failed and complexity in p.supported_complexity
        ]
        return candidates[0] if candidates else None

    def get_status(self) -> dict[str, Any]:
        """ルーターの状態を取得する。"""
        return {
            "providers": [
                {
                    "name": p.name,
                    "cost_tier": p.cost_tier,
                    "supported_complexity": [c.value for c in p.supported_complexity],
                    "priority": p.priority,
                    "max_tokens": p.max_tokens,
                }
                for p in self._providers
            ],
            "total_providers": len(self._providers),
        }
