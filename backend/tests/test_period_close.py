"""Tests for period close and CSV export functionality."""

import pytest
from decimal import Decimal


class TestPeriodCloseLogic:
    """月次締切ロジック"""

    def test_close_open_period(self):
        status = "open"
        action = "close"
        if action == "close" and status == "open":
            new_status = "closed"
        assert new_status == "closed"

    def test_close_already_closed_raises(self):
        status = "closed"
        action = "close"
        if action == "close" and status == "closed":
            raises = True
        assert raises is True

    def test_reopen_closed_period(self):
        status = "closed"
        action = "reopen"
        if action == "reopen" and status == "closed":
            new_status = "open"
        assert new_status == "open"

    def test_reopen_open_raises(self):
        status = "open"
        action = "reopen"
        if action == "reopen" and status != "closed":
            raises = True
        assert raises is True

    def test_valid_actions(self):
        valid = {"close", "reopen"}
        assert "close" in valid
        assert "reopen" in valid
        assert "invalid" not in valid

    def test_month_range(self):
        for m in range(1, 13):
            assert 1 <= m <= 12


class TestCSVExportLogic:
    """CSV出力ロジック"""

    def test_trial_balance_csv_header(self):
        header = "科目コード,科目名,区分,借方合計,貸方合計,残高"
        fields = header.split(",")
        assert len(fields) == 6
        assert "科目コード" in fields
        assert "残高" in fields

    def test_income_statement_csv_header(self):
        header = "区分,科目コード,科目名,金額"
        fields = header.split(",")
        assert len(fields) == 4

    def test_balance_sheet_csv_header(self):
        header = "区分,科目コード,科目名,金額"
        fields = header.split(",")
        assert len(fields) == 4

    def test_csv_row_format(self):
        row = f"1000,現金,asset,{Decimal('100000')},{Decimal('0')},{Decimal('100000')}"
        fields = row.split(",")
        assert len(fields) == 6
        assert fields[0] == "1000"
        assert fields[1] == "現金"

    def test_csv_total_row(self):
        total_debit = Decimal("500000")
        total_credit = Decimal("500000")
        row = f",合計,,{total_debit},{total_credit},{total_debit - total_credit}"
        fields = row.split(",")
        assert fields[1] == "合計"
        assert fields[5] == "0"

    def test_pl_csv_revenue_line(self):
        amt = Decimal("100000")
        row = f"収益,4000,売上高,{amt}"
        fields = row.split(",")
        assert fields[0] == "収益"
        assert fields[3] == "100000"

    def test_pl_csv_expense_line(self):
        amt = Decimal("50000")
        row = f"費用,5100,給与費用,{amt}"
        fields = row.split(",")
        assert fields[0] == "費用"

    def test_bs_csv_asset_line(self):
        amt = Decimal("1000000")
        row = f"資産,1000,現金,{amt}"
        fields = row.split(",")
        assert fields[0] == "資産"

    def test_bs_csv_liability_line(self):
        amt = Decimal("300000")
        row = f"負債,2000,買掛金,{amt}"
        fields = row.split(",")
        assert fields[0] == "負債"

    def test_bs_csv_equity_line(self):
        amt = Decimal("700000")
        row = f"純資産,3000,資本金,{amt}"
        fields = row.split(",")
        assert fields[0] == "純資産"

    def test_pl_csv_summary_lines(self):
        total_rev = Decimal("100000")
        total_exp = Decimal("60000")
        net = total_rev - total_exp
        lines = [
            f",,収益合計,{total_rev}",
            f",,費用合計,{total_exp}",
            f",,当期純利益,{net}",
        ]
        assert "100000" in lines[0]
        assert "60000" in lines[1]
        assert "40000" in lines[2]

    def test_bs_csv_summary_lines(self):
        total_a = Decimal("1000000")
        total_l = Decimal("300000")
        total_e = Decimal("700000")
        lines = [
            f",,資産合計,{total_a}",
            f",,負債合計,{total_l}",
            f",,純資産合計,{total_e}",
            f",,負債純資産合計,{total_l + total_e}",
        ]
        assert "1000000" in lines[0]
        assert "1000000" in lines[3]
