from app.services.integrations.registry import get_adapter, list_supported_software
from app.services.integrations.generic_csv_adapter import GenericCsvAdapter
from app.services.integrations.yayoi_adapter import YayoiAccountingAdapter


class TestRegistry:
    def test_list_supported_software(self):
        items = list_supported_software()
        assert len(items) >= 3

        codes = [item["software_code"] for item in items]
        assert "freee_accounting" in codes
        assert "yayoi_accounting" in codes
        assert "generic_csv" in codes

    def test_get_adapter_yayoi(self):
        adapter = get_adapter("yayoi_accounting")
        assert adapter is not None
        assert isinstance(adapter, YayoiAccountingAdapter)

    def test_get_adapter_generic_csv(self):
        adapter = get_adapter("generic_csv")
        assert adapter is not None
        assert isinstance(adapter, GenericCsvAdapter)

    def test_get_adapter_unknown(self):
        adapter = get_adapter("unknown_software")
        assert adapter is None

    def test_freee_supports_api(self):
        items = list_supported_software()
        freee = next(item for item in items if item["software_code"] == "freee_accounting")
        assert freee["supports_api"] is True
        assert freee["supports_csv"] is True

    def test_yayoi_no_api(self):
        items = list_supported_software()
        yayoi = next(item for item in items if item["software_code"] == "yayoi_accounting")
        assert yayoi["supports_api"] is False
        assert yayoi["supports_csv"] is True
