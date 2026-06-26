import json
import logging
from typing import Any

import httpx

from app.services.ai.base_provider import AIProvider, InferenceRequest, InferenceResult

logger = logging.getLogger(__name__)


class LocalLLMProvider(AIProvider):
    """OpenAI API互換のローカルLLMプロバイダー。

    Ollama (http://localhost:11434/v1), vLLM, llama.cpp server,
    LM Studio等のOpenAI互換エンドポイントに対応。
    """

    def __init__(
        self,
        endpoint_url: str = "http://localhost:11434/v1",
        model: str = "llama3.2:7b",
        api_key: str = "ollama",
        timeout: float = 60.0,
        max_tokens: int = 2000,
        temperature: float = 0.1,
    ):
        self._endpoint = endpoint_url.rstrip("/")
        self._model = model
        self._api_key = api_key
        self._timeout = timeout
        self._max_tokens = max_tokens
        self._temperature = temperature

    @property
    def endpoint(self) -> str:
        return self._endpoint

    @property
    def model(self) -> str:
        return self._model

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    async def _chat_completion(self, system_prompt: str, user_prompt: str, max_tokens: int | None = None) -> str:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._endpoint}/chat/completions",
                headers=self._headers(),
                json={
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": self._temperature,
                    "max_tokens": max_tokens or self._max_tokens,
                },
            )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"] or ""

    async def infer_journal(self, request: InferenceRequest) -> list[InferenceResult]:
        system = "あなたは日本の会計AIです。JSON形式で正確な仕訳を推論してください。"
        user = f"""取引情報から仕訳を推論してください。

取引情報:
- 説明: {request.description}
- 金額: {request.amount}
- 取引日: {request.transaction_date}
- 取引先: {request.partner_name or "不明"}
- 書類テキスト: {request.document_text or "なし"}

以下のJSON配列で回答:
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

ルール: 借方合計=貸方合計、外税処理基本。"""

        try:
            content = await self._chat_completion(system, user)
            text = content.strip()
            if text.startswith("```"):
                parts = text.split("```")
                text = parts[1] if len(parts) > 1 else text
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
                results.append(InferenceResult(
                    account_code=line.get("account_code", ""),
                    account_name=line.get("account_name", ""),
                    debit_credit=line.get("debit_credit", "debit"),
                    amount=float(line.get("amount", 0)),
                    tax_rate=float(line.get("tax_rate", 0)),
                    tax_type=line.get("tax_type", "non_taxable"),
                    confidence=float(line.get("confidence", 0)),
                    reasoning=line.get("reasoning", ""),
                ))
            return results

        except Exception as e:
            logger.error("LocalLLM inference failed: %s", e)
            raise

    async def predict_tax(self, description: str, amount: float) -> dict:
        system = "消費税区分を推定するAIです。JSONで回答してください。"
        user = f"取引「{description}」(金額{amount}円)の消費税区分を推定してください。tax_typeとtax_rateをJSONで返してください。"

        try:
            content = await self._chat_completion(system, user, max_tokens=200)
            text = content.strip().strip("`").strip()
            if text.startswith("json"):
                text = text[4:].strip()
            return json.loads(text)
        except Exception as e:
            logger.error("LocalLLM tax prediction failed: %s", e)
            raise

    async def detect_anomaly(self, journal_data: dict) -> dict:
        system = "会計データの異常検知AIです。JSONで回答してください。"
        user = f"以下の仕訳データの異常を検出してください:\n{json.dumps(journal_data, ensure_ascii=False)}"

        try:
            content = await self._chat_completion(system, user, max_tokens=500)
            text = content.strip().strip("`").strip()
            if text.startswith("json"):
                text = text[4:].strip()
            return json.loads(text)
        except Exception as e:
            logger.error("LocalLLM anomaly detection failed: %s", e)
            raise

    async def list_models(self) -> list[str]:
        """ローカルLLMサーバーで利用可能なモデル一覧を取得する。"""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(f"{self._endpoint}/models", headers=self._headers())
            if response.status_code == 200:
                data = response.json()
                return [m["id"] for m in data.get("data", [])]
        except Exception as e:
            logger.warning("Failed to list local models: %s", e)
        return []

    async def health_check(self) -> bool:
        """ローカルLLMサーバーの稼働確認。"""
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self._endpoint}/models", headers=self._headers())
            return response.status_code == 200
        except Exception:
            return False
