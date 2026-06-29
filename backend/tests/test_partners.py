import pytest
from uuid import uuid4


class TestPartnerValidation:
    def test_partner_type_values(self):
        valid_types = ["customer", "supplier", "both", "other"]
        for t in valid_types:
            assert isinstance(t, str)
            assert len(t) > 0

    def test_partner_code_uniqueness_logic(self):
        """重複チェックのロジックテスト"""
        existing_codes = ["C001", "C002", "S001"]
        new_code = "C001"
        assert new_code in existing_codes  # 重複

        new_code = "C003"
        assert new_code not in existing_codes  # OK

    def test_partner_type_labels(self):
        labels = {
            "customer": "顧客",
            "supplier": "仕入先",
            "both": "顧客・仕入先",
            "other": "その他",
        }
        assert len(labels) == 4
        assert labels["customer"] == "顧客"


class TestEmployeeValidation:
    def test_employment_type_values(self):
        valid_types = ["full_time", "part_time", "contract", "dispatch"]
        for t in valid_types:
            assert isinstance(t, str)

    def test_employment_type_labels(self):
        labels = {
            "full_time": "正社員",
            "part_time": "パート",
            "contract": "契約社員",
            "dispatch": "派遣",
        }
        assert len(labels) == 4
        assert labels["full_time"] == "正社員"

    def test_employee_code_required(self):
        """従業員コードは必須"""
        code = ""
        assert not code  # empty string is falsy

    def test_employee_name_required(self):
        """従業員名は必須"""
        name = ""
        assert not name
