import json
import logging
from typing import Any

from app.services.ai.base_provider import AIProvider, InferenceRequest, InferenceResult

logger = logging.getLogger(__name__)

JOURNAL_INFERENCE_PROMPT = """\
あなたは日本の会計に精通したAIアシスタントです。
以下の取引情報から、適切な仕訳（勘定科目・借方/貸方・金額・消費税）を推論してください。

取引情報:
- 説明: {description}
- 金額: {amount}
- 取引日: {transaction_date}
- 取引先: {partner_name}
- 書類テキスト: {document_text}

以下のJSON配列形式で回答してください。各要素は1行の仕訳を表します:
[
  {{
    "account_code": "勘定科目コード（推定）",
    "account_name": "勘定科目名",
    "debit_credit": "debit または credit",
    "amount": 数値,
    "tax_rate": 0.10 または 0.08 または 0,
    "tax_type": "tax_10_ex / tax_10_in / tax_8_ex / tax_8_in / non_taxable",
    "confidence": 0.0〜1.0の信頼度,
    "reasoning": "推論理由の簡潔な説明"
  }}
]

ルール:
1. 借方合計と貸方合計は一致させること
2. 日本の複式簿記の原則に従うこと
3. 消費税は外税処理を基本とする（税抜金額で仕訳）
4. 確信度が低い場合は0.5未満の値を設定すること
"""


class OpenAIProvider(AIProvider):
    """OpenAI GPT-4o based AI provider."""

    def __init__(self, api_key: str, model: str = "gpt-4o"):
        self._api_key = api_key
        self._model = model
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(api_key=self._api_key)
        return self._client

    async def infer_journal(self, request: InferenceRequest) -> list[InferenceResult]:
        prompt = JOURNAL_INFERENCE_PROMPT.format(
            description=request.description,
            amount=request.amount,
            transaction_date=request.transaction_date,
            partner_name=request.partner_name or "不明",
            document_text=request.document_text or "なし",
        )

        try:
            client = self._get_client()
            response = await client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": "あなたは日本の会計AIです。JSON形式で正確な仕訳を推論してください。"},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=2000,
            )

            content = response.choices[0].message.content or "{}"
            data = json.loads(content)

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

        except Exception as e:
            logger.error("OpenAI inference failed: %s", e)
            raise

    async def predict_tax(self, description: str, amount: float) -> dict:
        prompt = f"取引「{description}」(金額{amount}円)の消費税区分を推定してください。tax_typeとtax_rateをJSONで返してください。"

        try:
            client = self._get_client()
            response = await client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": "消費税区分を推定するAIです。"},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=200,
            )

            content = response.choices[0].message.content or "{}"
            return json.loads(content)

        except Exception as e:
            logger.error("OpenAI tax prediction failed: %s", e)
            raise

    async def detect_anomaly(self, journal_data: dict) -> dict:
        prompt = f"以下の仕訳データの異常を検出してください:\n{json.dumps(journal_data, ensure_ascii=False)}"

        try:
            client = self._get_client()
            response = await client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": "会計データの異常検知AIです。"},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=500,
            )

            content = response.choices[0].message.content or "{}"
            return json.loads(content)

        except Exception as e:
            logger.error("OpenAI anomaly detection failed: %s", e)
            raise
