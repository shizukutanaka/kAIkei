import io
import logging
from typing import Any

logger = logging.getLogger(__name__)


class PdfTextExtractor:
    """PDFファイルからテキストを抽出する。

    pdfplumber（推奨）またはPyPDF2をフォールバックとして使用。
    いずれもインストールされていない場合はエラーメッセージを返す。
    """

    @staticmethod
    def extract(file_bytes: bytes) -> str:
        """PDFのバイトデータからテキストを抽出する。

        Args:
            file_bytes: PDFファイルのバイトデータ

        Returns:
            抽出されたテキスト。抽出失敗時は空文字。
        """
        try:
            return PdfTextExtractor._extract_with_pdfplumber(file_bytes)
        except ImportError:
            logger.info("pdfplumber not available, trying PyPDF2")
        except Exception as e:
            logger.warning("pdfplumber extraction failed: %s", e)

        try:
            return PdfTextExtractor._extract_with_pypdf2(file_bytes)
        except ImportError:
            logger.warning("Neither pdfplumber nor PyPDF2 is installed")
        except Exception as e:
            logger.warning("PyPDF2 extraction failed: %s", e)

        return ""

    @staticmethod
    def _extract_with_pdfplumber(file_bytes: bytes) -> str:
        import pdfplumber

        text_parts: list[str] = []
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                text_parts.append(page_text)
        return "\n".join(text_parts)

    @staticmethod
    def _extract_with_pypdf2(file_bytes: bytes) -> str:
        from PyPDF2 import PdfReader

        reader = PdfReader(io.BytesIO(file_bytes))
        text_parts: list[str] = []
        for page in reader.pages:
            text_parts.append(page.extract_text() or "")
        return "\n".join(text_parts)

    @staticmethod
    def is_pdf(file_bytes: bytes) -> bool:
        """ファイルがPDFかどうかを判定する。"""
        return file_bytes[:5] == b"%PDF-"

    @staticmethod
    def extract_structured(file_bytes: bytes) -> dict[str, Any]:
        """PDFから構造化された情報を抽出する（金額・日付・取引先等）。

        Returns:
            抽出されたテキストと推定されるエンティティの辞書。
        """
        text = PdfTextExtractor.extract(file_bytes)

        entities: dict[str, Any] = {
            "raw_text": text,
            "amounts": [],
            "dates": [],
            "tax_rates": [],
            "potential_partner_names": [],
        }

        import re

        amount_pattern = re.compile(r"[¥￥]?\s*([0-9,]{1,3}(?:,[0-9]{3})*(?:\.[0-9]+)?)\s*円?")
        for match in amount_pattern.finditer(text):
            raw = match.group(1).replace(",", "")
            try:
                entities["amounts"].append(float(raw))
            except ValueError:
                pass

        date_patterns = [
            re.compile(r"(\d{4})[年/](\d{1,2})[月/](\d{1,2})日?"),
            re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})"),
        ]
        for pattern in date_patterns:
            for match in pattern.finditer(text):
                entities["dates"].append(match.group(0))

        tax_pattern = re.compile(r"(?:消費税|税率)\s*[:：]?\s*(\d+(?:\.\d+)?)\s*%")
        for match in tax_pattern.finditer(text):
            entities["tax_rates"].append(float(match.group(1)) / 100)

        lines = text.split("\n")
        for line in lines[:20]:
            line = line.strip()
            if line and not any(c.isdigit() for c in line[:3]) and len(line) > 2 and len(line) < 50:
                if "株式会社" in line or "有限会社" in line or "合同会社" in line:
                    entities["potential_partner_names"].append(line)

        return entities
