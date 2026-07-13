import pytest

from app.services.ai.document_extraction import (
    DOCUMENT_EXTRACTION_PROMPT,
    build_vision_messages,
    extract_document_fields_from_pdf,
    merge_document_fields,
    normalize_amount_value,
    normalize_date_value,
    parse_extraction_response,
    regex_fields_from_entities,
)
from app.services.ai.pdf_extractor import PdfTextExtractor


class TestBuildVisionMessages:
    def test_anthropic_format(self):
        messages = build_vision_messages("QUJD", media_type="image/jpeg")
        assert len(messages) == 1
        content = messages[0]["content"]
        assert content[0]["type"] == "image"
        assert content[0]["source"]["data"] == "QUJD"
        assert content[0]["source"]["media_type"] == "image/jpeg"
        assert content[1]["type"] == "text"
        assert content[1]["text"] == DOCUMENT_EXTRACTION_PROMPT

    def test_openai_format(self):
        messages = build_vision_messages("QUJD", provider_format="openai")
        content = messages[0]["content"]
        assert content[0]["type"] == "text"
        assert content[1]["type"] == "image_url"
        assert content[1]["image_url"]["url"] == "data:image/png;base64,QUJD"

    def test_unknown_format_raises(self):
        with pytest.raises(ValueError):
            build_vision_messages("QUJD", provider_format="gemini")


class TestParseExtractionResponse:
    def test_plain_json(self):
        result = parse_extraction_response(
            '{"transaction_date": "2026-04-15", "amount": 11000, '
            '"counterparty_name": "株式会社テスト", "confidence": 0.95}'
        )
        assert result["transaction_date"] == "2026-04-15"
        assert result["amount"] == 11000
        assert result["confidence"] == 0.95

    def test_code_fenced_json(self):
        result = parse_extraction_response('```json\n{"amount": 500}\n```')
        assert result == {"amount": 500}

    def test_invalid_json_returns_empty(self):
        assert parse_extraction_response("読み取れませんでした") == {}

    def test_non_dict_returns_empty(self):
        assert parse_extraction_response("[1, 2, 3]") == {}

    def test_unknown_keys_dropped(self):
        result = parse_extraction_response('{"amount": 100, "notes": "x"}')
        assert result == {"amount": 100}


class TestNormalizeDateValue:
    def test_japanese_era_format(self):
        assert normalize_date_value("2026年4月15日") == "2026-04-15"

    def test_slash_format(self):
        assert normalize_date_value("2026/04/15") == "2026-04-15"

    def test_iso_format(self):
        assert normalize_date_value("2026-04-15") == "2026-04-15"

    def test_us_format(self):
        assert normalize_date_value("4/15/2026") == "2026-04-15"

    def test_invalid_month_rejected(self):
        assert normalize_date_value("2026年13月1日") is None

    def test_none_and_garbage(self):
        assert normalize_date_value(None) is None
        assert normalize_date_value("不明") is None


class TestNormalizeAmountValue:
    def test_numeric(self):
        assert normalize_amount_value(11000) == 11000.0

    def test_yen_string(self):
        assert normalize_amount_value("¥12,000円") == 12000.0

    def test_zero_and_negative_rejected(self):
        assert normalize_amount_value(0) is None
        assert normalize_amount_value(-500) is None

    def test_garbage(self):
        assert normalize_amount_value("不明") is None
        assert normalize_amount_value(None) is None


class TestRegexFieldsFromEntities:
    def test_maps_entities(self):
        entities = {
            "dates": ["2026年4月15日"],
            "amounts": [1000.0, 11000.0],
            "potential_partner_names": ["株式会社テスト"],
        }
        fields = regex_fields_from_entities(entities)
        assert fields["transaction_date"] == "2026-04-15"
        assert fields["amount"] == 11000.0
        assert fields["counterparty_name"] == "株式会社テスト"

    def test_empty_entities(self):
        assert regex_fields_from_entities({"dates": [], "amounts": []}) == {}


class TestMergeDocumentFields:
    def test_llm_wins_over_regex(self):
        merged = merge_document_fields(
            {"transaction_date": "2026-01-01", "amount": 999.0},
            {"transaction_date": "2026-04-15", "amount": "11,000円", "confidence": 0.97},
        )
        assert merged["transaction_date"] == "2026-04-15"
        assert merged["amount"] == 11000.0
        assert merged["confidence"] == 0.97

    def test_regex_fills_llm_gaps(self):
        merged = merge_document_fields(
            {"counterparty_name": "株式会社テスト"},
            {"amount": 5000, "confidence": 0.9},
        )
        assert merged["amount"] == 5000.0
        assert merged["counterparty_name"] == "株式会社テスト"

    def test_regex_only_confidence(self):
        merged = merge_document_fields({"amount": 5000.0}, {})
        assert merged["amount"] == 5000.0
        assert merged["confidence"] == 0.5

    def test_nothing_extracted(self):
        merged = merge_document_fields({}, {})
        assert merged["transaction_date"] is None
        assert merged["amount"] is None
        assert merged["counterparty_name"] is None
        assert merged["confidence"] == 0.0

    def test_llm_confidence_clamped_and_defaulted(self):
        assert merge_document_fields({}, {"amount": 1, "confidence": 5})["confidence"] == 1.0
        assert merge_document_fields({}, {"amount": 1})["confidence"] == 0.8

    def test_llm_date_normalized(self):
        merged = merge_document_fields({}, {"transaction_date": "2026年4月15日", "confidence": 0.9})
        assert merged["transaction_date"] == "2026-04-15"


class TestPdfToImages:
    def test_non_pdf_returns_empty(self):
        assert PdfTextExtractor.pdf_to_images(b"not a pdf") == []

    def test_broken_pdf_returns_empty(self):
        # 有効なマジックナンバーだが本体が壊れているPDF
        assert PdfTextExtractor.pdf_to_images(b"%PDF-1.4 broken") == []


class _StubProvider:
    def __init__(self, fields=None, error=None):
        self._fields = fields or {}
        self._error = error
        self.calls: list[tuple[str, str | None]] = []

    async def extract_document_fields(self, text, image_base64=None):
        self.calls.append((text, image_base64))
        if self._error:
            raise self._error
        return self._fields


class TestExtractDocumentFieldsFromPdf:
    @pytest.fixture
    def fake_pdf(self, monkeypatch):
        monkeypatch.setattr(
            PdfTextExtractor,
            "extract_structured",
            staticmethod(
                lambda _b: {
                    "raw_text": "請求書 2026年4月15日 合計 ¥11,000",
                    "amounts": [11000.0],
                    "dates": ["2026年4月15日"],
                    "tax_rates": [],
                    "potential_partner_names": ["株式会社テスト"],
                }
            ),
        )
        monkeypatch.setattr(PdfTextExtractor, "pdf_to_images", staticmethod(lambda _b: []))

    async def test_regex_only_without_provider(self, fake_pdf):
        result = await extract_document_fields_from_pdf(b"%PDF-dummy", provider=None)
        assert result["transaction_date"] == "2026-04-15"
        assert result["amount"] == 11000.0
        assert result["confidence"] == 0.5

    async def test_provider_result_merged(self, fake_pdf):
        provider = _StubProvider({"counterparty_name": "カイケイ商事株式会社", "confidence": 0.96})
        result = await extract_document_fields_from_pdf(b"%PDF-dummy", provider=provider)
        assert result["counterparty_name"] == "カイケイ商事株式会社"
        assert result["transaction_date"] == "2026-04-15"
        assert result["confidence"] == 0.96
        assert len(provider.calls) == 1

    async def test_provider_receives_image_when_available(self, fake_pdf, monkeypatch):
        monkeypatch.setattr(PdfTextExtractor, "pdf_to_images", staticmethod(lambda _b: ["aW1n"]))
        provider = _StubProvider({"amount": 22000, "confidence": 0.99})
        result = await extract_document_fields_from_pdf(b"%PDF-dummy", provider=provider)
        assert provider.calls[0][1] == "aW1n"
        assert result["amount"] == 22000.0

    async def test_provider_error_falls_back_to_regex(self, fake_pdf):
        provider = _StubProvider(error=RuntimeError("API down"))
        result = await extract_document_fields_from_pdf(b"%PDF-dummy", provider=provider)
        assert result["amount"] == 11000.0
        assert result["confidence"] == 0.5

    async def test_not_implemented_falls_back(self, fake_pdf):
        provider = _StubProvider(error=NotImplementedError())
        result = await extract_document_fields_from_pdf(b"%PDF-dummy", provider=provider)
        assert result["transaction_date"] == "2026-04-15"
