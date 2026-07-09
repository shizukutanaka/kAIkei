"""監査・リスク検知エンジン（フェーズ6）。

仕訳を対象に、丸め金額・休日起票・バックデート・職務分掌（SoD）違反・高額・
重複などのリスクをルールベースで検知し、監査検知ログとして記録する。

検知ルールの中核はDB非依存の純粋関数として切り出し、単体テスト可能にしている。
"""
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import AuditDetectionLog, JournalHeader, JournalLine

logger = logging.getLogger(__name__)

# 既定の閾値。
HIGH_AMOUNT_THRESHOLD = Decimal("1000000")   # 高額判定（¥1,000,000以上）
ROUND_AMOUNT_MIN = Decimal("100000")         # 丸め金額判定の下限
ROUND_AMOUNT_MODULUS = Decimal("100000")     # この倍数なら「丸め」とみなす
BACKDATED_MAX_LAG_DAYS = 30                   # 起票日から遡る許容日数

RISK_ORDER = {"low": 0, "medium": 1, "high": 2}
VALID_STATUSES = {"open", "confirmed", "dismissed"}


@dataclass
class JournalSnapshot:
    """検知ルールの入力となる仕訳の正規化スナップショット。"""
    journal_header_id: str
    transaction_date: date
    created_on: date
    total_amount: Decimal
    created_by: str | None = None
    approved_by: str | None = None
    summary: str = ""
    counterparty: str = ""


@dataclass
class DetectionFinding:
    """1件の検知結果。"""
    category: str
    risk_level: str
    message: str
    details: dict = field(default_factory=dict)


# --- 純粋なルール関数（DB非依存・テスト可能） ------------------------------

def detect_high_amount(
    snapshot: JournalSnapshot, threshold: Decimal = HIGH_AMOUNT_THRESHOLD
) -> DetectionFinding | None:
    """高額仕訳を検知する。"""
    if snapshot.total_amount >= threshold:
        return DetectionFinding(
            category="high_amount",
            risk_level="high",
            message=f"高額仕訳です（{snapshot.total_amount}）。",
            details={"total_amount": str(snapshot.total_amount), "threshold": str(threshold)},
        )
    return None


def detect_round_amount(
    snapshot: JournalSnapshot,
    minimum: Decimal = ROUND_AMOUNT_MIN,
    modulus: Decimal = ROUND_AMOUNT_MODULUS,
) -> DetectionFinding | None:
    """概算・恣意性を示唆する丸め金額を検知する。"""
    amount = snapshot.total_amount
    if amount >= minimum and modulus > 0 and amount % modulus == 0:
        return DetectionFinding(
            category="round_amount",
            risk_level="medium",
            message=f"金額が{modulus}の倍数（丸め金額）です（{amount}）。",
            details={"total_amount": str(amount), "modulus": str(modulus)},
        )
    return None


def detect_weekend_entry(snapshot: JournalSnapshot) -> DetectionFinding | None:
    """土日付けの取引を検知する。"""
    if snapshot.transaction_date.weekday() >= 5:  # 5=土, 6=日
        weekday_name = "土曜日" if snapshot.transaction_date.weekday() == 5 else "日曜日"
        return DetectionFinding(
            category="weekend_entry",
            risk_level="low",
            message=f"取引日が休日（{weekday_name}）です。",
            details={"transaction_date": snapshot.transaction_date.isoformat()},
        )
    return None


def detect_backdated(
    snapshot: JournalSnapshot, max_lag_days: int = BACKDATED_MAX_LAG_DAYS
) -> DetectionFinding | None:
    """起票日から大きく遡った取引日（バックデート）を検知する。"""
    lag = (snapshot.created_on - snapshot.transaction_date).days
    if lag > max_lag_days:
        return DetectionFinding(
            category="backdated",
            risk_level="medium",
            message=f"取引日が起票日より{lag}日前です（許容{max_lag_days}日）。",
            details={
                "transaction_date": snapshot.transaction_date.isoformat(),
                "created_on": snapshot.created_on.isoformat(),
                "lag_days": lag,
            },
        )
    return None


def detect_sod_conflict(snapshot: JournalSnapshot) -> DetectionFinding | None:
    """起票者と承認者が同一（職務分掌違反）を検知する。"""
    if snapshot.created_by and snapshot.approved_by and snapshot.created_by == snapshot.approved_by:
        return DetectionFinding(
            category="sod_conflict",
            risk_level="high",
            message="起票者と承認者が同一です（職務分掌違反）。",
            details={"user_id": snapshot.created_by},
        )
    return None


def detect_duplicate(
    snapshot: JournalSnapshot, others: list[JournalSnapshot]
) -> DetectionFinding | None:
    """同額・同日・同取引先の重複仕訳を検知する。"""
    for other in others:
        if other.journal_header_id == snapshot.journal_header_id:
            continue
        if (
            other.total_amount == snapshot.total_amount
            and other.transaction_date == snapshot.transaction_date
            and (other.counterparty or "") == (snapshot.counterparty or "")
        ):
            return DetectionFinding(
                category="duplicate",
                risk_level="medium",
                message="同額・同日・同取引先の重複仕訳の可能性があります。",
                details={
                    "duplicate_of": other.journal_header_id,
                    "total_amount": str(snapshot.total_amount),
                    "transaction_date": snapshot.transaction_date.isoformat(),
                },
            )
    return None


def run_rules(
    snapshot: JournalSnapshot,
    others: list[JournalSnapshot] | None = None,
    high_amount_threshold: Decimal = HIGH_AMOUNT_THRESHOLD,
    backdated_max_lag_days: int = BACKDATED_MAX_LAG_DAYS,
) -> list[DetectionFinding]:
    """1件の仕訳に全ルールを適用し、検知結果を返す。"""
    others = others or []
    findings = [
        detect_high_amount(snapshot, high_amount_threshold),
        detect_round_amount(snapshot),
        detect_weekend_entry(snapshot),
        detect_backdated(snapshot, backdated_max_lag_days),
        detect_sod_conflict(snapshot),
        detect_duplicate(snapshot, others),
    ]
    return [f for f in findings if f is not None]


def highest_risk(findings: list[DetectionFinding]) -> str | None:
    """検知結果中の最も高いリスクレベルを返す。"""
    if not findings:
        return None
    return max((f.risk_level for f in findings), key=lambda r: RISK_ORDER.get(r, -1))


# --- 非同期サービス（DB依存） ------------------------------------------------

def _snapshot_from(header: JournalHeader, lines: list[JournalLine]) -> JournalSnapshot:
    debit_total = sum(
        (l.amount for l in lines if l.debit_credit == "debit" and not l.is_deleted),
        Decimal("0"),
    )
    counterparty = ""
    for line in lines:
        if line.description:
            counterparty = line.description
            break
    return JournalSnapshot(
        journal_header_id=str(header.journal_header_id),
        transaction_date=header.transaction_date,
        created_on=header.created_at.date() if header.created_at else header.transaction_date,
        total_amount=debit_total,
        created_by=str(header.created_by) if header.created_by else None,
        approved_by=str(header.approved_by) if header.approved_by else None,
        summary=header.summary or "",
        counterparty=counterparty or (header.summary or ""),
    )


async def scan_company(
    db: AsyncSession,
    tenant_id: UUID,
    company_id: UUID,
    high_amount_threshold: Decimal = HIGH_AMOUNT_THRESHOLD,
    backdated_max_lag_days: int = BACKDATED_MAX_LAG_DAYS,
    limit: int = 500,
) -> dict:
    """会社の仕訳をスキャンし、検知結果をaudit_detection_logsへ記録する。

    既に検知済み（同一journal_header_id×category）はスキップして重複記録を避ける。
    """
    result = await db.execute(
        select(JournalHeader)
        .where(
            JournalHeader.company_id == company_id,
            JournalHeader.is_deleted == False,  # noqa: E712
            JournalHeader.is_voided == False,  # noqa: E712
        )
        .order_by(JournalHeader.transaction_date.desc())
        .limit(limit)
    )
    headers = list(result.scalars().all())

    snapshots: list[JournalSnapshot] = []
    for header in headers:
        line_result = await db.execute(
            select(JournalLine).where(JournalLine.journal_header_id == header.journal_header_id)
        )
        snapshots.append(_snapshot_from(header, list(line_result.scalars().all())))

    existing_result = await db.execute(
        select(AuditDetectionLog.journal_header_id, AuditDetectionLog.category).where(
            AuditDetectionLog.company_id == company_id
        )
    )
    existing = {(str(jh) if jh else None, cat) for jh, cat in existing_result.all()}

    created = 0
    for snapshot in snapshots:
        findings = run_rules(
            snapshot, snapshots, high_amount_threshold, backdated_max_lag_days
        )
        for finding in findings:
            if (snapshot.journal_header_id, finding.category) in existing:
                continue
            db.add(AuditDetectionLog(
                tenant_id=tenant_id,
                company_id=company_id,
                journal_header_id=UUID(snapshot.journal_header_id),
                risk_level=finding.risk_level,
                category=finding.category,
                message=finding.message,
                details=finding.details,
                status="open",
            ))
            existing.add((snapshot.journal_header_id, finding.category))
            created += 1

    if created:
        await db.commit()

    return {"scanned": len(snapshots), "detections_created": created}


async def list_detections(
    db: AsyncSession,
    company_id: UUID,
    status: str | None = None,
    risk_level: str | None = None,
    limit: int = 100,
) -> list[AuditDetectionLog]:
    """監査検知ログを一覧取得する。"""
    conditions = [AuditDetectionLog.company_id == company_id]
    if status is not None:
        conditions.append(AuditDetectionLog.status == status)
    if risk_level is not None:
        conditions.append(AuditDetectionLog.risk_level == risk_level)
    result = await db.execute(
        select(AuditDetectionLog)
        .where(*conditions)
        .order_by(AuditDetectionLog.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def update_status(
    db: AsyncSession,
    company_id: UUID,
    detection_id: UUID,
    new_status: str,
    reviewed_by: UUID,
) -> AuditDetectionLog | None:
    """検知ログの確認状態を更新する（confirmed / dismissed）。"""
    if new_status not in VALID_STATUSES:
        raise ValueError(f"Invalid status: {new_status}")
    result = await db.execute(
        select(AuditDetectionLog).where(
            AuditDetectionLog.audit_detection_log_id == detection_id,
            AuditDetectionLog.company_id == company_id,
        )
    )
    log = result.scalar_one_or_none()
    if log is None:
        return None
    log.status = new_status
    log.reviewed_by = reviewed_by
    log.reviewed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(log)
    return log
