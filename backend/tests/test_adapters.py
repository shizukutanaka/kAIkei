from datetime import date
from decimal import Decimal

import pytest

from app.services.integrations.freee_adapter import FreeeAccountingAdapter
from app.services.integrations.generic_csv_adapter import GenericCsvAdapter
from app.services.integrations.yayoi_adapter import YayoiAccountingAdapter


SAMPLE_YAYOI_CSV = """取引日,伝票番号,借方科目コード,借方科目名,借方補助科目,借方金額,貸方科目コード,貸方科目名,貸方補助科目,貸方金額,摘要,税区分,部門
2026/04/15,Y-000001,1110,現金,,5000,4110,売上,,5000,現金売上,1,営業部
2026/04/16,Y-000002,1120,預金,,10000,4110,売上,,10000,振込売上,1,営業部
"""

SAMPLE_GENERIC_CSV = """取引日,伝票番号,借方科目コード,借方科目名,借方金額,貸方科目コード,貸方科目名,貸方金額,摘要,税区分,部門
2026/04/15,GEN-001,1110,現金,5000,4110,売上,5000,現金売上,1,営業部
2026/04/16,GEN-002,1120,預金,10000,4110,売上,10000,振込売上,1,営業部
"""

UNBALANCED_CSV = """取引日,伝票番号,借方科目コード,借方科目名,借方金額,貸方科目コード,貸方科目名,貸方金額,摘要,税区分,部門
2026/04/15,BAD-001,1110,現金,5000,4110,売上,3000,貸借不一致,1,営業部
"""

# freeeの振替形式CSV（勘定科目は名称、税区分はラベル、金額は桁区切り）。
SAMPLE_FREEE_CSV = """発生日,取引No,借方勘定科目,借方金額,借方税区分,貸方勘定科目,貸方金額,貸方税区分,摘要
2026/04/15,F-001,現金,"5,000",対象外,売上高,"5,000",課税売上10%,現金売上
2026/04/16,F-002,普通預金,"10,000",対象外,売上高,"10,000",課税売上10%,振込売上
"""


class TestYayoiAdapter:
    def test_parse_csv(self):
        adapter = YayoiAccountingAdapter()
        journals = adapter.parse_csv(SAMPLE_YAYOI_CSV)

        assert len(journals) == 2
        assert journals[0].transaction_date == date(2026, 4, 15)
        assert journals[0].journal_number == "Y-000001"
        assert journals[0].summary == "現金売上"
        assert len(journals[0].lines) == 2
        assert journals[0].lines[0]["debit_credit"] == "debit"
        assert journals[0].lines[0]["amount"] == 5000.0
        assert journals[0].lines[1]["debit_credit"] == "credit"
        assert journals[0].lines[1]["amount"] == 5000.0

    def test_software_info(self):
        adapter = YayoiAccountingAdapter()
        assert adapter.software_code == "yayoi_accounting"
        assert adapter.software_name == "弥生会計"
        assert adapter.supports_csv is True
        assert adapter.supports_api is False

    def test_empty_csv(self):
        adapter = YayoiAccountingAdapter()
        journals = adapter.parse_csv("取引日,伝票番号,借方科目コード\n")
        assert len(journals) == 0


class TestGenericCsvAdapter:
    def test_parse_csv(self):
        adapter = GenericCsvAdapter()
        journals = adapter.parse_csv(SAMPLE_GENERIC_CSV)

        assert len(journals) == 2
        assert journals[0].transaction_date == date(2026, 4, 15)
        assert journals[0].journal_number == "GEN-001"
        assert len(journals[0].lines) == 2

    def test_validate_valid(self):
        adapter = GenericCsvAdapter()
        journals = adapter.parse_csv(SAMPLE_GENERIC_CSV)
        result = adapter.validate_import(journals)

        assert result["total"] == 2
        assert result["valid"] == 2
        assert result["errors"] == 0
        assert result["is_valid"] is True

    def test_validate_unbalanced(self):
        adapter = GenericCsvAdapter()
        journals = adapter.parse_csv(UNBALANCED_CSV)
        result = adapter.validate_import(journals)

        assert result["errors"] == 1
        assert result["is_valid"] is False
        assert len(result["error_details"]) == 1
        assert "貸借不一致" in result["error_details"][0]["errors"][0]

    def test_software_info(self):
        adapter = GenericCsvAdapter()
        assert adapter.software_code == "generic_csv"
        assert adapter.supports_csv is True
        assert adapter.supports_api is False

    def test_custom_column_mapping(self):
        custom_mapping = {
            "transaction_date": "Date",
            "journal_number": "VoucherNo",
            "debit_account_code": "DrCode",
            "debit_account_name": "DrName",
            "debit_amount": "DrAmount",
            "credit_account_code": "CrCode",
            "credit_account_name": "CrName",
            "credit_amount": "CrAmount",
            "summary": "Notes",
            "tax_category": "Tax",
            "department": "Dept",
        }
        custom_csv = "Date,VoucherNo,DrCode,DrName,DrAmount,CrCode,CrName,CrAmount,Notes,Tax,Dept\n2026/05/01,C-001,1000,Cash,8000,4000,Sales,8000,Test sale,1,Sales\n"
        adapter = GenericCsvAdapter(column_mapping=custom_mapping)
        journals = adapter.parse_csv(custom_csv)

        assert len(journals) == 1
        assert journals[0].journal_number == "C-001"
        assert journals[0].summary == "Test sale"


class TestFreeeCsvImport:
    def test_supports_csv(self):
        adapter = FreeeAccountingAdapter()
        assert adapter.supports_csv is True

    def test_parse_csv(self):
        adapter = FreeeAccountingAdapter()
        journals = adapter.parse_csv(SAMPLE_FREEE_CSV)

        assert len(journals) == 2
        assert journals[0].transaction_date == date(2026, 4, 15)
        assert journals[0].journal_number == "F-001"
        assert journals[0].summary == "現金売上"
        assert len(journals[0].lines) == 2
        # 名称ベース: 借方=現金, 貸方=売上高
        assert journals[0].lines[0]["account_name"] == "現金"
        assert journals[0].lines[0]["amount"] == 5000.0
        assert journals[0].lines[1]["account_name"] == "売上高"
        # 桁区切りカンマを含む金額が正しくパースされる
        assert journals[1].lines[0]["amount"] == 10000.0

    def test_tax_label_mapping(self):
        adapter = FreeeAccountingAdapter()
        journals = adapter.parse_csv(SAMPLE_FREEE_CSV)
        credit_line = journals[0].lines[1]
        assert credit_line["tax_type"] == "tax_10_ex"

    def test_validate_name_based_import_is_valid(self):
        """freeeは科目コードを持たないが、名称で識別できれば有効と判定される。"""
        adapter = FreeeAccountingAdapter()
        journals = adapter.parse_csv(SAMPLE_FREEE_CSV)
        result = adapter.validate_import(journals)

        assert result["total"] == 2
        assert result["valid"] == 2
        assert result["is_valid"] is True


class TestBaseValidateImport:
    def test_missing_account_code_and_name_flagged(self):
        from app.services.integrations.base_adapter import ImportedJournal

        journal = ImportedJournal(
            transaction_date=date(2026, 4, 15),
            journal_number="X-1",
            summary="科目なし",
            lines=[
                {"debit_credit": "debit", "account_code": "", "account_name": "", "amount": 100.0},
                {"debit_credit": "credit", "account_code": "", "account_name": "", "amount": 100.0},
            ],
            source_software="generic_csv",
        )
        result = GenericCsvAdapter().validate_import([journal])
        assert result["is_valid"] is False
        assert any("科目が空" in e for e in result["error_details"][0]["errors"])
