import logging
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, require_permission
from app.core.rbac import Permission
from app.services.ai.enhanced_inference import EnhancedInferenceEngine
from app.services.ai.inference_engine import ai_engine
from app.services.ai.pdf_extractor import PdfTextExtractor

logger = logging.getLogger(__name__)
router = APIRouter()


class InferenceRequestSchema(BaseModel):
    description: str = Field(..., min_length=1, max_length=500)
    amount: float = Field(..., gt=0)
    transaction_date: str
    partner_name: str | None = None
    document_text: str | None = None


class EnhancedInferenceRequestSchema(BaseModel):
    description: str = Field(..., min_length=1, max_length=500)
    amount: float = Field(..., gt=0)
    transaction_date: str
    company_id: str
    partner_name: str | None = None
    document_text: str | None = None


class TaxPredictionRequest(BaseModel):
    description: str
    amount: float = Field(..., gt=0)


class AnomalyDetectionRequest(BaseModel):
    journal_data: dict


@router.post("/infer-journal")
async def infer_journal(
    payload: InferenceRequestSchema,
    current_user: CurrentUser = Depends(require_permission(Permission.AI_INFER)),
) -> dict:
    """AI仕訳推論: 自然言語の取引説明から仕訳を推論する。"""
    from app.services.ai.base_provider import InferenceRequest

    request = InferenceRequest(
        description=payload.description,
        amount=payload.amount,
        transaction_date=payload.transaction_date,
        partner_name=payload.partner_name,
        document_text=payload.document_text,
    )
    result = await ai_engine.infer_journal(request)

    if result["status"] == "unavailable":
        raise HTTPException(status_code=503, detail="AI provider not configured")

    return result


@router.post("/infer-journal-enhanced")
async def infer_journal_enhanced(
    payload: EnhancedInferenceRequestSchema,
    current_user: CurrentUser = Depends(require_permission(Permission.AI_INFER)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """拡張AI仕訳推論: 過去仕訳を参照して推論精度を向上させる。

    過去の処理済み仕訳から類似パターンを抽出し、AIプロンプトにコンテキストとして
    含めることで、一貫性のある仕訳推論を可能にする。
    """
    from app.services.ai.base_provider import InferenceRequest

    if not ai_engine.is_available:
        raise HTTPException(status_code=503, detail="AI provider not configured")

    request = InferenceRequest(
        description=payload.description,
        amount=payload.amount,
        transaction_date=payload.transaction_date,
        partner_name=payload.partner_name,
        document_text=payload.document_text,
    )

    enhanced_engine = EnhancedInferenceEngine(providers=ai_engine._providers)
    result = await enhanced_engine.infer_with_context(
        request, db, payload.company_id
    )

    if result["status"] == "error":
        raise HTTPException(status_code=500, detail=result.get("message", "Inference failed"))

    return result


@router.post("/infer-from-pdf")
async def infer_from_pdf(
    company_id: str,
    transaction_date: str,
    amount: float = 0,
    description: str = "",
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(require_permission(Permission.AI_INFER)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """PDFファイルをアップロードして仕訳推論を行う。

    PDFからテキスト・金額・日付・取引先を抽出し、過去仕訳コンテキストと合わせて
    AI推論を実行する。
    """
    if not ai_engine.is_available:
        raise HTTPException(status_code=503, detail="AI provider not configured")

    file_bytes = await file.read()

    if not PdfTextExtractor.is_pdf(file_bytes):
        raise HTTPException(status_code=400, detail="Uploaded file is not a PDF")

    extracted = PdfTextExtractor.extract_structured(file_bytes)

    if not extracted["raw_text"]:
        raise HTTPException(
            status_code=422,
            detail="No text could be extracted from the PDF. It may be a scanned image.",
        )

    inferred_amount = amount
    if inferred_amount == 0 and extracted["amounts"]:
        inferred_amount = max(extracted["amounts"])

    inferred_description = description
    if not inferred_description:
        first_lines = extracted["raw_text"].strip().split("\n")[:3]
        inferred_description = " ".join(first_lines)[:200]

    inferred_partner = None
    if extracted["potential_partner_names"]:
        inferred_partner = extracted["potential_partner_names"][0]

    from app.services.ai.base_provider import InferenceRequest

    request = InferenceRequest(
        description=inferred_description,
        amount=inferred_amount,
        transaction_date=transaction_date,
        partner_name=inferred_partner,
        document_text=extracted["raw_text"][:3000],
    )

    enhanced_engine = EnhancedInferenceEngine(providers=ai_engine._providers)
    result = await enhanced_engine.infer_with_context(request, db, company_id)

    result["pdf_extraction"] = {
        "file_name": file.filename,
        "extracted_amounts": extracted["amounts"],
        "extracted_dates": extracted["dates"],
        "extracted_tax_rates": extracted["tax_rates"],
        "potential_partner_names": extracted["potential_partner_names"],
        "text_length": len(extracted["raw_text"]),
        "text_preview": extracted["raw_text"][:500],
    }

    if result["status"] == "error":
        raise HTTPException(status_code=500, detail=result.get("message", "Inference failed"))

    return result


@router.post("/predict-tax")
async def predict_tax(
    payload: TaxPredictionRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.AI_INFER)),
) -> dict:
    """AI税務予測: 取引の消費税区分を予測する。"""
    result = await ai_engine.predict_tax(payload.description, payload.amount)

    if result.get("status") == "unavailable":
        raise HTTPException(status_code=503, detail="AI provider not configured")

    return result


@router.post("/detect-anomaly")
async def detect_anomaly(
    payload: AnomalyDetectionRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.AI_INFER)),
) -> dict:
    """AI異常検知: 仕訳データの異常を検出する。"""
    result = await ai_engine.detect_anomaly(payload.journal_data)

    if result.get("status") == "unavailable":
        raise HTTPException(status_code=503, detail="AI provider not configured")

    return result


@router.get("/status")
async def get_ai_status(
    current_user: CurrentUser = Depends(require_permission(Permission.AI_INFER)),
) -> dict:
    """AI プロバイダー状態・タスクルーティング設定を取得する。"""
    return ai_engine.get_status()


@router.get("/models")
async def list_local_models(
    current_user: CurrentUser = Depends(require_permission(Permission.AI_INFER)),
) -> dict:
    """ローカルLLMで利用可能なモデル一覧を取得する。"""
    from app.services.ai.local_llm_provider import LocalLLMProvider

    from app.core.config import settings

    if not settings.LOCAL_LLM_ENDPOINT:
        return {"status": "unavailable", "models": [], "message": "LOCAL_LLM_ENDPOINT not configured"}

    provider = LocalLLMProvider(
        endpoint_url=settings.LOCAL_LLM_ENDPOINT,
        api_key=settings.LOCAL_LLM_API_KEY,
    )
    is_healthy = await provider.health_check()
    if not is_healthy:
        return {"status": "offline", "models": [], "message": f"Cannot reach {settings.LOCAL_LLM_ENDPOINT}"}

    models = await provider.list_models()
    return {"status": "online", "models": models, "endpoint": settings.LOCAL_LLM_ENDPOINT}
