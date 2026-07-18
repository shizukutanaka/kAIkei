"""AI推論監査証跡サービス（フェーズ2/6）。

AI推論の提案内容・信頼度・適用状況・ユーザー修正差分を記録し、説明責任
（Explainability）と精度評価に用いる。

信頼度バンド・自動コミット判定・修正差分算出・精度集計の中核はDB非依存の
純粋関数として切り出す。
"""
import logging
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import AiInferenceLog

logger = logging.getLogger(__name__)

# AI自動コミット閾値（Plan.md 6.3）。この信頼度以上なら人手確認なしで適用可能。
AUTO_COMMIT_THRESHOLD = Decimal("0.95")
HIGH_CONFIDENCE = Decimal("0.90")
MEDIUM_CONFIDENCE = Decimal("0.70")


# --- 純粋関数（DB非依存・テスト可能） ---------------------------------------

def confidence_band(confidence: Decimal) -> str:
    """信頼度をバンド（high / medium / low）に分類する。"""
    c = Decimal(confidence)
    if c >= HIGH_CONFIDENCE:
        return "high"
    if c >= MEDIUM_CONFIDENCE:
        return "medium"
    return "low"


def should_auto_commit(confidence: Decimal, threshold: Decimal = AUTO_COMMIT_THRESHOLD) -> bool:
    """信頼度が自動コミット閾値以上か判定する。"""
    return Decimal(confidence) >= Decimal(threshold)


def compute_correction_diff(suggestion: dict, final: dict) -> dict:
    """AI提案とユーザー確定内容のフィールド単位の差分を算出する。

    Returns:
        {field: {"from": 提案値, "to": 確定値}} 形式の変更のみ。
    """
    diff: dict = {}
    keys = set(suggestion or {}) | set(final or {})
    for key in keys:
        before = (suggestion or {}).get(key)
        after = (final or {}).get(key)
        if before != after:
            diff[key] = {"from": before, "to": after}
    return diff


def compute_accuracy_stats(logs: list[dict]) -> dict:
    """推論ログ（dict列）から精度指標を集計する。

    - total: 件数
    - applied: 適用件数
    - acceptance_rate: 適用率
    - corrected: 修正あり件数（適用のうち）
    - correction_rate: 適用のうち修正された割合
    - avg_confidence: 平均信頼度
    """
    total = len(logs)
    if total == 0:
        return {
            "total": 0,
            "applied": 0,
            "acceptance_rate": 0.0,
            "corrected": 0,
            "correction_rate": 0.0,
            "avg_confidence": 0.0,
        }
    applied = sum(1 for l in logs if l.get("applied"))
    corrected = sum(1 for l in logs if l.get("applied") and l.get("correction_diff"))
    avg_conf = sum(float(l.get("confidence", 0)) for l in logs) / total
    return {
        "total": total,
        "applied": applied,
        "acceptance_rate": round(applied / total, 4),
        "corrected": corrected,
        "correction_rate": round(corrected / applied, 4) if applied else 0.0,
        "avg_confidence": round(avg_conf, 4),
    }


def compute_calibration_stats(logs: list[dict]) -> dict:
    """適用済みログから信頼度バンド別の実正答率と較正誤差(ECE)を集計する。

    正答の定義: 適用され、かつ修正差分なし（AI提案がそのまま確定した）。
    自動コミット閾値(AUTO_COMMIT_THRESHOLD)の妥当性検証に用いる。

    Returns:
        {"applied_total", "ece", "bands": [{band, count, avg_confidence,
         observed_accuracy, gap}]}。ECEは件数加重した |平均信頼度-実正答率|。
    """
    applied = [l for l in logs if l.get("applied")]
    total = len(applied)
    band_specs = [
        ("low", Decimal("0"), MEDIUM_CONFIDENCE),
        ("medium", MEDIUM_CONFIDENCE, HIGH_CONFIDENCE),
        ("high", HIGH_CONFIDENCE, Decimal("1.01")),
    ]
    bands: list[dict] = []
    ece = 0.0
    for name, lo, hi in band_specs:
        rows = [l for l in applied if lo <= Decimal(str(l.get("confidence", 0))) < hi]
        count = len(rows)
        if count:
            correct = sum(1 for l in rows if not l.get("correction_diff"))
            accuracy = correct / count
            avg_conf = sum(float(l.get("confidence", 0)) for l in rows) / count
            gap = abs(avg_conf - accuracy)
            ece += (count / total) * gap
            bands.append({
                "band": name,
                "count": count,
                "avg_confidence": round(avg_conf, 4),
                "observed_accuracy": round(accuracy, 4),
                "gap": round(gap, 4),
            })
        else:
            bands.append({
                "band": name, "count": 0,
                "avg_confidence": None, "observed_accuracy": None, "gap": None,
            })
    return {"applied_total": total, "ece": round(ece, 4) if total else 0.0, "bands": bands}


# --- 非同期サービス（DB依存） ------------------------------------------------

async def log_inference(
    db: AsyncSession,
    tenant_id: UUID,
    company_id: UUID,
    source_type: str,
    suggestion: dict,
    confidence: Decimal,
    input_summary: str | None = None,
    provider: str | None = None,
    journal_header_id: UUID | None = None,
) -> AiInferenceLog:
    """AI推論の証跡を記録する。"""
    log = AiInferenceLog(
        tenant_id=tenant_id,
        company_id=company_id,
        source_type=source_type,
        input_summary=input_summary,
        suggestion=suggestion,
        confidence=Decimal(confidence),
        provider=provider,
        journal_header_id=journal_header_id,
        applied=False,
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)
    return log


async def mark_applied(
    db: AsyncSession,
    company_id: UUID,
    log_id: UUID,
    final: dict | None = None,
) -> AiInferenceLog | None:
    """推論を適用済みにし、確定内容との修正差分を記録する。"""
    result = await db.execute(
        select(AiInferenceLog).where(
            AiInferenceLog.ai_inference_log_id == log_id,
            AiInferenceLog.company_id == company_id,
        )
    )
    log = result.scalar_one_or_none()
    if log is None:
        return None
    log.applied = True
    if final is not None:
        diff = compute_correction_diff(log.suggestion or {}, final)
        log.correction_diff = diff or None
    await db.commit()
    await db.refresh(log)
    return log


async def list_logs(
    db: AsyncSession,
    company_id: UUID,
    source_type: str | None = None,
    applied: bool | None = None,
    limit: int = 100,
) -> list[AiInferenceLog]:
    """AI推論証跡を一覧取得する。"""
    conditions = [AiInferenceLog.company_id == company_id]
    if source_type is not None:
        conditions.append(AiInferenceLog.source_type == source_type)
    if applied is not None:
        conditions.append(AiInferenceLog.applied == applied)  # noqa: E712
    result = await db.execute(
        select(AiInferenceLog)
        .where(*conditions)
        .order_by(AiInferenceLog.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_stats(db: AsyncSession, company_id: UUID, limit: int = 1000) -> dict:
    """会社のAI推論精度指標を集計する。"""
    logs = await list_logs(db, company_id, limit=limit)
    return compute_accuracy_stats([
        {"applied": l.applied, "correction_diff": l.correction_diff, "confidence": l.confidence}
        for l in logs
    ])


async def get_calibration(db: AsyncSession, company_id: UUID, limit: int = 1000) -> dict:
    """会社のAI推論の信頼度較正指標を集計する。"""
    logs = await list_logs(db, company_id, limit=limit)
    return compute_calibration_stats([
        {"applied": l.applied, "correction_diff": l.correction_diff, "confidence": l.confidence}
        for l in logs
    ])
