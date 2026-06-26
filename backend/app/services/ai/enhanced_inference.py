import json
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ai.base_provider import AIProvider, InferenceRequest, InferenceResult
from app.services.ai.historical_context import HistoricalContextProvider

logger = logging.getLogger(__name__)

ENHANCED_INFERENCE_PROMPT = """\
あなたは日本の会計に精通したAIアシスタントです。
以下の取引情報、過去仕訳の参照データ、および外部ナレッジ（最新技術動向）を基に、最も適切な仕訳を推論してください。

## 取引情報
- 説明: {description}
- 金額: {amount}
- 取引日: {transaction_date}
- 取引先: {partner_name}
- 書類テキスト: {document_text}

## 過去の類似仕訳（参考データ）
{historical_journals}

## よく使用される科目パターン
{account_patterns}

## よく使用される借方・貸方の組み合わせ
{frequent_combos}

## 外部ナレッジ（GitHub・Qiita・Zenn・論文からの最新情報）
{external_knowledge}

上記の過去仕訳パターンを参考に、一貫性のある仕訳を作成してください。
過去仕訳と同じ科目を使用することを優先してください。

以下のJSON配列形式で回答してください:
[
  {{
    "account_code": "勘定科目コード",
    "account_name": "勘定科目名",
    "debit_credit": "debit または credit",
    "amount": 数値,
    "tax_rate": 0.10/0.08/0,
    "tax_type": "tax_10_ex/tax_10_in/tax_8_ex/tax_8_in/non_taxable",
    "confidence": 0.0〜1.0,
    "reasoning": "推論理由（過去仕訳を参照した場合はその旨を記載）",
    "referenced_journal": "参照した過去仕訳の伝票番号（該当する場合）"
  }}
]

ルール:
1. 借方合計と貸方合計は一致させること
2. 過去仕訳と同じパターンがある場合はそれに従うこと
3. 日本の複式簿記の原則に従うこと
4. 消費税は外税処理を基本とする
5. 過去仕訳を参照した場合はreferenced_journalに伝票番号を記載すること
"""


class EnhancedInferenceEngine:
    """過去仕訳を参照する拡張AI推論エンジン。"""

    def __init__(self, providers: list[AIProvider]):
        self._providers = providers

    async def infer_with_context(
        self,
        request: InferenceRequest,
        db: AsyncSession,
        company_id: str,
        include_external_knowledge: bool = True,
    ) -> dict[str, Any]:
        """過去仕訳コンテキスト + 外部ナレッジを用いた仕訳推論。

        Args:
            request: 推論リクエスト（説明・金額・日付等）
            db: データベースセッション
            company_id: 会社ID（過去仕訳の検索対象）
            include_external_knowledge: 外部ナレッジ（GitHub/Qiita/Zenn/論文）を含めるか

        Returns:
            推論結果 + コンテキスト情報 + 参照した過去仕訳 + 外部ナレッジ
        """
        from uuid import UUID

        context = await HistoricalContextProvider.build_context(
            db, UUID(company_id), request.description, request.amount
        )

        historical_journals_text = json.dumps(
            context["similar_journals"], ensure_ascii=False, indent=2
        ) if context["similar_journals"] else "過去仕訳データなし"

        patterns_text = json.dumps(
            context["account_patterns"], ensure_ascii=False, indent=2
        ) if context["account_patterns"] else "パターンデータなし"

        combos_text = json.dumps(
            context["frequent_combinations"], ensure_ascii=False, indent=2
        ) if context["frequent_combinations"] else "組み合わせデータなし"

        external_knowledge_text = "外部ナレッジ取得なし"
        external_knowledge_items: list[dict] = []

        if include_external_knowledge:
            try:
                from app.services.knowledge.aggregator import knowledge_aggregator

                keywords = request.description.split()[:3] or [request.description]
                external_knowledge_text = await knowledge_aggregator.build_ai_context(
                    keywords=keywords,
                    max_items=3,
                )
                if not external_knowledge_text:
                    external_knowledge_text = "外部ナレッジ取得なし"
                else:
                    search_result = await knowledge_aggregator.search_all(
                        keywords=keywords, max_per_source=2
                    )
                    external_knowledge_items = search_result.get("items", [])[:3]
            except Exception as e:
                logger.warning("External knowledge fetch failed: %s", e)
                external_knowledge_text = f"外部ナレッジ取得エラー: {e}"

        prompt = ENHANCED_INFERENCE_PROMPT.format(
            description=request.description,
            amount=request.amount,
            transaction_date=request.transaction_date,
            partner_name=request.partner_name or "不明",
            document_text=request.document_text or "なし",
            historical_journals=historical_journals_text,
            account_patterns=patterns_text,
            frequent_combos=combos_text,
            external_knowledge=external_knowledge_text,
        )

        last_error: Exception | None = None

        for provider in self._providers:
            try:
                results = await self._call_provider(provider, prompt)

                debit_total = sum(r.amount for r in results if r.debit_credit == "debit")
                credit_total = sum(r.amount for r in results if r.debit_credit == "credit")
                avg_confidence = sum(r.confidence for r in results) / len(results) if results else 0

                is_balanced = abs(debit_total - credit_total) < 1
                needs_review = avg_confidence < 0.7 or not is_balanced

                referenced_journals = [
                    r.reasoning for r in results if "参照" in r.reasoning or "過去" in r.reasoning
                ]

                return {
                    "status": "needs_review" if needs_review else "auto_approved",
                    "provider": provider.__class__.__name__,
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
                    "context_used": {
                        "similar_journals_count": len(context["similar_journals"]),
                        "patterns_count": len(context["account_patterns"]),
                        "combos_count": len(context["frequent_combinations"]),
                        "referenced_journals": referenced_journals,
                        "external_knowledge_count": len(external_knowledge_items),
                    },
                    "historical_context": {
                        "similar_journals": context["similar_journals"],
                    },
                    "external_knowledge": external_knowledge_items,
                }

            except Exception as e:
                last_error = e
                logger.warning(
                    "Provider %s failed: %s, trying fallback",
                    provider.__class__.__name__,
                    e,
                )
                continue

        return {
            "status": "error",
            "message": f"All providers failed: {last_error}" if last_error else "Unknown error",
            "results": [],
            "context_used": {
                "similar_journals_count": len(context["similar_journals"]),
                "patterns_count": len(context["account_patterns"]),
                "combos_count": len(context["frequent_combinations"]),
            },
        }

    async def _call_provider(self, provider: AIProvider, prompt: str) -> list[InferenceResult]:
        """プロバイダー固有の呼び出しを実行する。"""
        if "OpenAI" in provider.__class__.__name__:
            return await self._call_openai(provider, prompt)
        elif "Anthropic" in provider.__class__.__name__:
            return await self._call_anthropic(provider, prompt)
        else:
            return await provider.infer_journal(
                InferenceRequest(
                    description=prompt,
                    amount=0,
                    transaction_date="",
                )
            )

    async def _call_openai(self, provider: AIProvider, prompt: str) -> list[InferenceResult]:
        import json as json_module

        client = provider._get_client()
        response = await client.chat.completions.create(
            model=provider._model,
            messages=[
                {"role": "system", "content": "あなたは日本の会計AIです。過去仕訳を参考に一貫性のある仕訳を作成してください。JSON形式で回答してください。"},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=3000,
        )

        content = response.choices[0].message.content or "{}"
        data = json_module.loads(content)

        lines = data.get("lines", data if isinstance(data, list) else [])
        if isinstance(lines, dict):
            lines = [lines]

        results: list[InferenceResult] = []
        for line in lines:
            results.append(
                InferenceResult(
                    account_code=line.get("account_code", ""),
                    account_name=line.get("account_name", ""),
                    debit_credit=line.get("debit_credit", "debit"),
                    amount=float(line.get("amount", 0)),
                    tax_rate=float(line.get("tax_rate", 0)),
                    tax_type=line.get("tax_type", "non_taxable"),
                    confidence=float(line.get("confidence", 0)),
                    reasoning=line.get("reasoning", ""),
                )
            )
        return results

    async def _call_anthropic(self, provider: AIProvider, prompt: str) -> list[InferenceResult]:
        import json as json_module

        client = provider._get_client()
        response = await client.messages.create(
            model=provider._model,
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}],
        )

        content = response.content[0].text if response.content else "{}"
        text = content.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        if text.startswith("```"):
            text = text.split("```")[0].strip()

        data = json_module.loads(text)
        if isinstance(data, dict):
            data = data.get("lines", [data])

        results: list[InferenceResult] = []
        for line in data:
            results.append(
                InferenceResult(
                    account_code=line.get("account_code", ""),
                    account_name=line.get("account_name", ""),
                    debit_credit=line.get("debit_credit", "debit"),
                    amount=float(line.get("amount", 0)),
                    tax_rate=float(line.get("tax_rate", 0)),
                    tax_type=line.get("tax_type", "non_taxable"),
                    confidence=float(line.get("confidence", 0)),
                    reasoning=line.get("reasoning", ""),
                )
            )
        return results
