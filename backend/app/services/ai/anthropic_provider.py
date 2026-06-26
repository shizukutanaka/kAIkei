import json
import logging
from typing import Any

from app.services.ai.base_provider import AIProvider, InferenceRequest, InferenceResult

logger = logging.getLogger(__name__)


class AnthropicProvider(AIProvider):
    """Anthropic Claude based AI provider."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        self._api_key = api_key
        self._model = model
        self._client = None

    def _get_client(self):
        if self._client is None:
            from anthropic import AsyncAnthropic

            self._client = AsyncAnthropic(api_key=self._api_key)
        return self._client

    async def infer_journal(self, request: InferenceRequest) -> list[InferenceResult]:
        prompt = f"""あなたは日本の会計に精通したAIアシスタントです。
以下の取引情報から、適切な仕訳を推論してください。

取引情報:
- 説明: {request.description}
- 金額: {request.amount}
- 取引日: {request.transaction_date}
- 取引先: {request.partner_name or "不明"}
- 書類テキスト: {request.document_text or "なし"}

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
    "reasoning": "推論理由"
  }}
]

ルール: 借方合計=貸方合計、外税処理基本、日本の複式簿記の原則。"""

        try:
            client = self._get_client()
            response = await client.messages.create(
                model=self._model,
                max_tokens=2000,
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

            data = json.loads(text)
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

        except Exception as e:
            logger.error("Anthropic inference failed: %s", e)
            raise

    async def predict_tax(self, description: str, amount: float) -> dict:
        prompt = f"取引「{description}」(金額{amount}円)の消費税区分を推定してください。tax_typeとtax_rateをJSONで返してください。"

        try:
            client = self._get_client()
            response = await client.messages.create(
                model=self._model,
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}],
            )

            content = response.content[0].text if response.content else "{}"
            return json.loads(content.strip().strip("`").strip())

        except Exception as e:
            logger.error("Anthropic tax prediction failed: %s", e)
            raise

    async def detect_anomaly(self, journal_data: dict) -> dict:
        prompt = f"以下の仕訳データの異常を検出してください:\n{json.dumps(journal_data, ensure_ascii=False)}"

        try:
            client = self._get_client()
            response = await client.messages.create(
                model=self._model,
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}],
            )

            content = response.content[0].text if response.content else "{}"
            return json.loads(content.strip().strip("`").strip())

        except Exception as e:
            logger.error("Anthropic anomaly detection failed: %s", e)
            raise
