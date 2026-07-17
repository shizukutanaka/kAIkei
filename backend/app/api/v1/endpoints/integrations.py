from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from pydantic import BaseModel

from app.core.deps import CurrentUser, require_permission
from app.core.rbac import Permission
from app.services.integrations.registry import get_adapter, list_supported_software

router = APIRouter()


class CsvImportResponse(BaseModel):
    total: int
    valid: int
    errors: int
    error_details: list[dict]
    is_valid: bool


@router.get("/supported-software")
async def get_supported_software(
    current_user: CurrentUser = Depends(require_permission(Permission.INTEGRATION_IMPORT)),
) -> dict:
    """対応ソフトウェア一覧を取得する。"""
    return {"items": list_supported_software()}


@router.post("/import-csv/{software_code}")
async def import_csv(
    software_code: str,
    file: UploadFile = File(...),
    dry_run: bool = Query(True, description="true=シミュレーションのみ"),
    current_user: CurrentUser = Depends(require_permission(Permission.INTEGRATION_IMPORT)),
) -> dict:
    """CSVファイルをアップロードして取り込み（Dry-run対応）。"""
    adapter = get_adapter(software_code)
    if not adapter:
        raise HTTPException(status_code=404, detail=f"Unsupported software: {software_code}")

    if not adapter.supports_csv:
        raise HTTPException(status_code=400, detail=f"{software_code} does not support CSV import")

    content = await file.read()
    csv_text = content.decode("utf-8-sig")

    # 各アダプタがparse_csv/validate_importを提供するため、software_code毎の
    # 分岐なしにポリモーフィックに取り込む。
    try:
        journals = adapter.parse_csv(csv_text)
    except NotImplementedError:
        raise HTTPException(
            status_code=400,
            detail=f"CSV import is not available for {software_code}",
        )
    validation = adapter.validate_import(journals)

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
