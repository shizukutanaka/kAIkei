from fastapi import APIRouter, HTTPException, UploadFile, File, Query
from pydantic import BaseModel

from app.services.integrations.registry import get_adapter, list_supported_software

router = APIRouter()


class CsvImportResponse(BaseModel):
    total: int
    valid: int
    errors: int
    error_details: list[dict]
    is_valid: bool


@router.get("/supported-software")
async def get_supported_software() -> dict:
    """対応ソフトウェア一覧を取得する。"""
    return {"items": list_supported_software()}


@router.post("/import-csv/{software_code}")
async def import_csv(
    software_code: str,
    file: UploadFile = File(...),
    dry_run: bool = Query(True, description="true=シミュレーションのみ"),
) -> dict:
    """CSVファイルをアップロードして取り込み（Dry-run対応）。"""
    adapter = get_adapter(software_code)
    if not adapter:
        raise HTTPException(status_code=404, detail=f"Unsupported software: {software_code}")

    if not adapter.supports_csv:
        raise HTTPException(status_code=400, detail=f"{software_code} does not support CSV import")

    content = await file.read()
    csv_text = content.decode("utf-8-sig")

    if software_code == "generic_csv":
        from app.services.integrations.generic_csv_adapter import GenericCsvAdapter

        csv_adapter = GenericCsvAdapter()
        journals = csv_adapter.parse_csv(csv_text)
        validation = csv_adapter.validate_import(journals)
    elif software_code == "yayoi_accounting":
        from app.services.integrations.yayoi_adapter import YayoiAccountingAdapter

        yayoi_adapter = YayoiAccountingAdapter()
        journals = yayoi_adapter.parse_csv(csv_text)

        from app.services.integrations.generic_csv_adapter import GenericCsvAdapter

        validation = GenericCsvAdapter().validate_import(journals)
    else:
        raise HTTPException(status_code=400, detail=f"CSV import not implemented for {software_code}")

    return {
        "dry_run": dry_run,
        "software_code": software_code,
        "file_name": file.filename,
        **validation,
        "imported_journals": [
            {
                "transaction_date": j.transaction_date.isoformat(),
                "journal_number": j.journal_number,
                "summary": j.summary,
                "line_count": len(j.lines),
            }
            for j in journals
        ] if not dry_run else [],
    }
