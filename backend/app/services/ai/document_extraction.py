"""証憑からの構造化フィールド抽出（マルチモーダルLLM＋regexフォールバック）。

電帳法の検索3軸（取引年月日・金額・取引先）をアップロード証憑から自動抽出する。
純粋関数コア（メッセージ組み立て・応答パース・正規化・マージ）はDB/ネットワーク
非依存で単体テスト可能。実LLM呼び出しは AIProvider.extract_document_fields に
委譲し、LLMが使えない環境では既存の正規表現抽出のみで動作する。
"""

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

FIELD_KEYS = ("transaction_date", "amount", "counterparty_name")

DOCUMENT_EXTRACTION_PROMPT = """\
あなたは日本の会計証憑（請求書・領収書・見積書等）の読み取りに精通したAIです。
この書類から以下の項目を抽出し、JSONオブジェクトのみで回答してください。

{
  "transaction_date": "取引年月日（YYYY-MM-DD形式。不明ならnull）",
  "amount": 税込合計金額の数値（不明ならnull）,
  "counterparty_name": "発行者（取引先）の名称（不明ならnull）",
  "confidence": 0.0〜1.0の信頼度
}

ルール:
1. 金額は合計（税込）を優先し、カンマ・円記号を除いた数値で返すこと
2. 日付が複数ある場合は取引日・発行日を優先すること
3. 判読できない項目は推測せずnullとし、confidenceを下げること
"""


def build_vision_messages(
    image_base64: str,
    media_type: str = "image/png",
    prompt: str = DOCUMENT_EXTRACTION_PROMPT,
    provider_format: str = "anthropic",
) -> list[dict]:
    """画像入力付きのLLMメッセージ構造を組み立てる。

    Args:
        image_base64: base64エンコード済み画像データ
        media_type: 画像のMIMEタイプ
        prompt: 抽出指示プロンプト
        provider_format: "anthropic" または "openai"

    Returns:
        各SDKの messages 引数にそのまま渡せるリスト。
    """
    if provider_format == "anthropic":
        return [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_base64,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ]
    if provider_format == "openai":
        return [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{media_type};base64,{image_base64}"},
                    },
                ],
            }
        ]
    raise ValueError(f"Unknown provider_format: {provider_format}")


def build_text_messages(
    text: str,
    prompt: str = DOCUMENT_EXTRACTION_PROMPT,
    max_chars: int = 6000,
) -> list[dict]:
    """画像なし（テキストのみ）のLLMメッセージ構造を組み立てる。

    Anthropic/OpenAIとも単純な単一ユーザーメッセージ形式のため共通化する。
    """
    return [
        {
            "role": "user",
            "content": f"{prompt}\n\n書類テキスト:\n{text[:max_chars]}",
        }
    ]


def parse_extraction_response(text: str) -> dict:
    """LLM応答テキストから抽出フィールドのJSONを取り出す。

    コードフェンスを剥がしてパースし、既知キーのみを返す。
    パース不能なら空辞書。
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()
    try:
        data = json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: data[k] for k in (*FIELD_KEYS, "confidence") if k in data}


_DATE_PATTERNS = [
    re.compile(r"(\d{4})[年/\-\.](\d{1,2})[月/\-\.](\d{1,2})日?"),
    re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})"),
]


def normalize_date_value(value: Any) -> str | None:
    """日付表現を YYYY-MM-DD に正規化する。解釈不能なら None。"""
    if value is None:
        return None
    text = str(value).strip()
    m = _DATE_PATTERNS[0].search(text)
    if m:
        year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
    else:
        m = _DATE_PATTERNS[1].search(text)
        if not m:
            return None
        month, day, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    return f"{year:04d}-{month:02d}-{day:02d}"


def normalize_amount_value(value: Any) -> float | None:
    """金額表現を数値に正規化する。解釈不能・非正値なら None。"""
    if value is None:
        return None
    if isinstance(value, int | float):
        amount = float(value)
    else:
        cleaned = re.sub(r"[¥￥,円\s]", "", str(value))
        try:
            amount = float(cleaned)
        except ValueError:
            return None
    return amount if amount > 0 else None


def regex_fields_from_entities(entities: dict) -> dict:
    """PdfTextExtractor.extract_structured の結果を3軸フィールドへ変換する。"""
    fields: dict[str, Any] = {}
    if entities.get("dates"):
        fields["transaction_date"] = normalize_date_value(entities["dates"][0])
    if entities.get("amounts"):
        fields["amount"] = max(entities["amounts"])
    if entities.get("potential_partner_names"):
        fields["counterparty_name"] = entities["potential_partner_names"][0]
    return {k: v for k, v in fields.items() if v is not None}


def merge_document_fields(regex_fields: dict, llm_fields: dict) -> dict:
    """LLM抽出値を優先し、欠落分をregex抽出値で補完する。

    値は正規化して返す。confidence は LLM値があればそれを、
    regexのみなら0.5、何も取れなければ0.0とする。
    """
    normalizers = {
        "transaction_date": normalize_date_value,
        "amount": normalize_amount_value,
        "counterparty_name": lambda v: str(v).strip() or None if v is not None else None,
    }
    merged: dict[str, Any] = {}
    llm_used = False
    for key in FIELD_KEYS:
        normalize = normalizers[key]
        llm_value = normalize(llm_fields.get(key))
        if llm_value is not None:
            merged[key] = llm_value
            llm_used = True
        else:
            merged[key] = normalize(regex_fields.get(key))

    if llm_used:
        confidence = llm_fields.get("confidence")
        try:
            merged["confidence"] = min(max(float(confidence), 0.0), 1.0)
        except (TypeError, ValueError):
            merged["confidence"] = 0.8
    elif any(merged[k] is not None for k in FIELD_KEYS):
        merged["confidence"] = 0.5
    else:
        merged["confidence"] = 0.0
    return merged


async def extract_document_fields_from_pdf(file_bytes: bytes, provider=None) -> dict:
    """証憑PDFから3軸フィールドを抽出する（enhanced経路）。

    プロバイダが与えられればvision/テキストLLM抽出＋regexマージ、
    なければregexのみ。LLM呼び出しの失敗はregex結果へフォールバックする。
    """
    from app.services.ai.pdf_extractor import PdfTextExtractor

    entities = PdfTextExtractor.extract_structured(file_bytes)
    regex_fields = regex_fields_from_entities(entities)

    if provider is None:
        return merge_document_fields(regex_fields, {})

    images = PdfTextExtractor.pdf_to_images(file_bytes)
    image_base64 = images[0] if images else None
    text = entities.get("raw_text", "")

    if image_base64 is None and not text:
        return merge_document_fields(regex_fields, {})

    try:
        llm_fields = await provider.extract_document_fields(text, image_base64=image_base64)
    except NotImplementedError:
        llm_fields = {}
    except Exception as e:
        logger.warning("LLM document extraction failed, falling back to regex: %s", e)
        llm_fields = {}
    return merge_document_fields(regex_fields, llm_fields or {})
