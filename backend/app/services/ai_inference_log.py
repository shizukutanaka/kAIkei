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
# 較正指標のビン数。Guo et al. 2017 は10〜15を用いるが、ここでは20とする。
# 10ビンだと最上位ビンが[0.90,1.00)となり自動コミット閾値0.95を内包してしまい、
# 閾値の前後で生じる逆方向の較正ずれが相殺されて見えなくなる。20ビンなら0.95が
# ビン境界に一致し、閾値の直前直後を分離して評価できる。
CALIBRATION_BINS = 20


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
        {"applied_total", "ece", "bands": [...], "ece_binned", "ece_adaptive",
         "signed_gap", "auto_commit": {...}}。

    注意: `ece` はバンド(low/medium/high)単位の粗い指標で、幅の広いビン内で逆方向の
    誤差が相殺されるため過小評価されうる。閾値の妥当性判断には `ece_binned` /
    `ece_adaptive` と、特に `auto_commit.observed_accuracy` を参照すること
    （詳細は `_fine_grained_calibration` のドキュメント）。
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
    result = {"applied_total": total, "ece": round(ece, 4) if total else 0.0, "bands": bands}
    result.update(_fine_grained_calibration(applied))
    return result


def _is_correct(log: dict) -> bool:
    """AI提案がそのまま確定した（修正差分なし）なら正答とみなす。"""
    return not log.get("correction_diff")


def _ece_from_groups(groups: list[list[dict]], total: int) -> tuple[float, float]:
    """ビン群から (ECE, 符号付き平均ギャップ) を返す。

    符号付きギャップは 平均信頼度 − 実正答率。正なら自信過剰（危険側）。
    """
    ece = 0.0
    signed = 0.0
    for rows in groups:
        n = len(rows)
        if not n:
            continue
        acc = sum(1 for r in rows if _is_correct(r)) / n
        conf = sum(float(r.get("confidence", 0)) for r in rows) / n
        ece += (n / total) * abs(conf - acc)
        signed += (n / total) * (conf - acc)
    return ece, signed


def _fine_grained_calibration(applied: list[dict], bins: int = CALIBRATION_BINS) -> dict:
    """細分ビンによるECEと、自動コミット閾値の安全性指標を算出する。

    バンド(low/medium/high)は幅が広く、特に high=[0.90,1.01) は自動コミット閾値0.95を
    内包する。幅の広いビンでは**ビン内で逆方向の誤差が相殺**され、実際には閾値付近が
    ずれていてもECEがほぼ0と報告されうる（例: 信頼度0.91で実正答99%、0.99で実正答91%が
    混在すると平均は0.95/0.95で一致しギャップ0になる）。
    そのため以下を併せて算出する:

    - ece_binned: 等幅10ビンのECE（Guo et al. 2017 の標準的な算出方法）。
    - ece_adaptive: 等件数ビンのECE。信頼度分布は高値側に偏るため等幅では特定ビンに
      標本が集中して分解能を失う。等件数ビンはこれを避ける（Nixon et al. 2019）。
    - signed_gap: 平均信頼度−実正答率の加重平均。**正の値は自信過剰**を意味する。
    - auto_commit: 自動コミット対象（信頼度>=閾値）の実正答率。閾値の妥当性を直接検証する。
    """
    total = len(applied)
    if not total:
        return {
            "ece_binned": 0.0,
            "ece_adaptive": 0.0,
            "signed_gap": 0.0,
            "auto_commit": {
                "threshold": float(AUTO_COMMIT_THRESHOLD),
                "count": 0,
                "observed_accuracy": None,
                "avg_confidence": None,
                "signed_gap": None,
                "overconfident": False,
            },
        }

    # 等幅ビン（Guo et al. 2017）
    width_groups: list[list[dict]] = [[] for _ in range(bins)]
    for log in applied:
        conf = float(log.get("confidence", 0))
        idx = min(int(conf * bins), bins - 1)
        width_groups[idx].append(log)
    ece_binned, signed_gap = _ece_from_groups(width_groups, total)

    # 等件数ビン（Nixon et al. 2019）
    ordered = sorted(applied, key=lambda l: float(l.get("confidence", 0)))
    k = min(bins, total)
    size, remainder = divmod(total, k)
    mass_groups: list[list[dict]] = []
    start = 0
    for i in range(k):
        end = start + size + (1 if i < remainder else 0)
        mass_groups.append(ordered[start:end])
        start = end
    ece_adaptive, _ = _ece_from_groups(mass_groups, total)

    # 自動コミット閾値の安全性（この領域は人手確認なしで確定されるため最重要）
    at_threshold = [
        l for l in applied
        if Decimal(str(l.get("confidence", 0))) >= AUTO_COMMIT_THRESHOLD
    ]
    if at_threshold:
        n = len(at_threshold)
        acc = sum(1 for l in at_threshold if _is_correct(l)) / n
        conf = sum(float(l.get("confidence", 0)) for l in at_threshold) / n
        auto_commit = {
            "threshold": float(AUTO_COMMIT_THRESHOLD),
            "count": n,
            "observed_accuracy": round(acc, 4),
            "avg_confidence": round(conf, 4),
            "signed_gap": round(conf - acc, 4),
            # 実正答率が閾値を下回る＝自動コミットが想定より誤りを含む（要調整）
            "overconfident": acc < float(AUTO_COMMIT_THRESHOLD),
        }
    else:
        auto_commit = {
            "threshold": float(AUTO_COMMIT_THRESHOLD),
            "count": 0,
            "observed_accuracy": None,
            "avg_confidence": None,
            "signed_gap": None,
            "overconfident": False,
        }

    return {
        "ece_binned": round(ece_binned, 4),
        "ece_adaptive": round(ece_adaptive, 4),
        "signed_gap": round(signed_gap, 4),
        "auto_commit": auto_commit,
    }


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
