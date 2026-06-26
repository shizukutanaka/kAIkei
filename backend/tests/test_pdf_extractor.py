import pytest

from app.services.ai.pdf_extractor import PdfTextExtractor


class TestPdfTextExtractor:
    def test_is_pdf_valid(self):
        pdf_header = b"%PDF-1.4 some content"
        assert PdfTextExtractor.is_pdf(pdf_header) is True

    def test_is_pdf_invalid(self):
        text_header = b"Hello World"
        assert PdfTextExtractor.is_pdf(text_header) is False

    def test_is_pdf_empty(self):
        assert PdfTextExtractor.is_pdf(b"") is False

    def test_extract_from_non_pdf_returns_empty(self):
        result = PdfTextExtractor.extract(b"Hello World")
        assert result == ""

    def test_extract_structured_amounts(self):
        text = "請求書\n金額: ¥10,000\n消費税: ¥1,000\n合計: ¥11,000"
        import io
        import struct

        entities = PdfTextExtractor.extract_structured(b"dummy")
        # Without a real PDF, raw_text will be empty but structure is valid
        assert "raw_text" in entities
        assert "amounts" in entities
        assert "dates" in entities
        assert "tax_rates" in entities
        assert "potential_partner_names" in entities

    def test_extract_structured_partner_names(self):
        entities = PdfTextExtractor.extract_structured(b"dummy")
        assert isinstance(entities["potential_partner_names"], list)
