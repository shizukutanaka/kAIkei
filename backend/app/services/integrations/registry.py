from app.services.integrations.base_adapter import ImportAdapter
from app.services.integrations.freee_adapter import FreeeAccountingAdapter
from app.services.integrations.generic_csv_adapter import GenericCsvAdapter
from app.services.integrations.yayoi_adapter import YayoiAccountingAdapter

_ADAPTERS: dict[str, type[ImportAdapter]] = {
    "yayoi_accounting": YayoiAccountingAdapter,
    "freee_accounting": FreeeAccountingAdapter,
    "generic_csv": GenericCsvAdapter,
}

SUPPORTED_SOFTWARE = [
    {
        "software_code": "freee_accounting",
        "software_name": "freee会計",
        "supports_api": True,
        "supports_csv": True,
        "import_targets": ["journals", "masters", "documents"],
    },
    {
        "software_code": "yayoi_accounting",
        "software_name": "弥生会計",
        "supports_api": False,
        "supports_csv": True,
        "import_targets": ["journals", "masters"],
    },
    {
        "software_code": "generic_csv",
        "software_name": "汎用CSV",
        "supports_api": False,
        "supports_csv": True,
        "import_targets": ["journals", "masters"],
    },
]


def get_adapter(software_code: str, **kwargs) -> ImportAdapter | None:
    """Get an adapter instance for the given software code."""
    adapter_class = _ADAPTERS.get(software_code)
    if not adapter_class:
        return None
    return adapter_class(**kwargs)


def list_supported_software() -> list[dict]:
    """List all supported software."""
    return SUPPORTED_SOFTWARE
