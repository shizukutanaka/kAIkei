import csv
import io
import zipfile
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, require_permission
from app.core.rbac import Permission
from app.models.models import (
    Account,
    AuditLog,
    Company,
    JournalHeader,
    JournalLine,
    MonthlyBalance,
)
from app.schemas.schemas import (
    AuditLogListResponse,
    AuditLogResponse,
    LedgerCheckRequest,
    LedgerCheckResponse,
)
from app.services.ledger_consistency import LedgerConsistencyService

router = APIRouter(tags=["audit"])


@router.get("/logs", response_model=AuditLogListResponse)
async def list_audit_logs(
    company_id: UUID = Query(..., description="会社ID"),  # noqa: B008
    page: int = Query(1, ge=1),  # noqa: B008
    page_size: int = Query(50, ge=1, le=200),  # noqa: B008
    action: str | None = Query(None, description="アクションでフィルタ"),  # noqa: B008
    resource_type: str | None = Query(None, description="リソース種別でフィルタ"),  # noqa: B008
    user_id: UUID | None = Query(None, description="ユーザーIDでフィルタ"),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> AuditLogListResponse:
    """操作証跡ログ一覧を取得する。"""
    conditions = [AuditLog.company_id == company_id]
    if action:
        conditions.append(AuditLog.action == action)
    if resource_type:
        conditions.append(AuditLog.resource_type == resource_type)
    if user_id:
        conditions.append(AuditLog.user_id == user_id)

    count_result = await db.execute(
        select(func.count()).select_from(AuditLog).where(*conditions)
    )
    total = count_result.scalar() or 0

    result = await db.execute(
        select(AuditLog)
        .where(*conditions)
        .order_by(AuditLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = result.scalars().all()
    items = [
        AuditLogResponse(
            log_id=r.log_id,
            user_id=r.user_id,
            action=r.action,
            resource_type=r.resource_type,
            resource_id=r.resource_id,
            method=r.method,
            path=r.path,
            status_code=r.status_code,
            ip_address=r.ip_address,
            user_agent=r.user_agent,
            created_at=r.created_at,
        )
        for r in rows
    ]
    return AuditLogListResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("/ledger-check", response_model=LedgerCheckResponse)
async def ledger_check(
    payload: LedgerCheckRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> LedgerCheckResponse:
    header_result = await db.execute(
        select(JournalHeader).where(
            JournalHeader.company_id == payload.company_id,
            JournalHeader.approval_status == "approved",
            JournalHeader.is_deleted == False,  # noqa: E712
            JournalHeader.transaction_date <= payload.target_date,
        )
    )
    line_result = await db.execute(
        select(JournalLine)
        .join(JournalHeader, JournalHeader.journal_header_id == JournalLine.journal_header_id)
        .where(
            JournalHeader.company_id == payload.company_id,
            JournalHeader.approval_status == "approved",
            JournalHeader.is_deleted == False,  # noqa: E712
            JournalHeader.transaction_date <= payload.target_date,
            JournalLine.is_deleted == False,  # noqa: E712
        )
    )
    balance_result = await db.execute(
        select(MonthlyBalance).where(
            MonthlyBalance.company_id == payload.company_id,
            MonthlyBalance.is_deleted == False,  # noqa: E712
            (MonthlyBalance.year < payload.target_date.year)
            | (
                (MonthlyBalance.year == payload.target_date.year)
                & (MonthlyBalance.month <= payload.target_date.month)
            ),
        )
    )
    result = LedgerConsistencyService.check(
        company_id=payload.company_id,
        target_date=payload.target_date,
        journal_headers=list(header_result.scalars().all()),
        journal_lines=list(line_result.scalars().all()),
        monthly_balances=list(balance_result.scalars().all()),
    )
    return LedgerCheckResponse(
        status=result.status,
        balance_check={
            "headers_checked": result.balance_check.headers_checked,
            "imbalanced_count": result.balance_check.imbalanced_count,
            "total_debit": result.balance_check.total_debit,
            "total_credit": result.balance_check.total_credit,
            "imbalanced_entries": [
                {
                    "journal_header_id": entry.journal_header_id,
                    "debit_sum": entry.debit_sum,
                    "credit_sum": entry.credit_sum,
                    "difference": entry.difference,
                }
                for entry in result.balance_check.imbalanced_entries
            ],
        },
        cache_drift_check={
            "rows_checked": result.cache_drift_check.rows_checked,
            "drift_count": result.cache_drift_check.drift_count,
            "drift_entries": [
                {
                    "account_id": entry.account_id,
                    "year": entry.year,
                    "month": entry.month,
                    "expected_debit": entry.expected_debit,
                    "expected_credit": entry.expected_credit,
                    "cached_debit": entry.cached_debit,
                    "cached_credit": entry.cached_credit,
                }
                for entry in result.cache_drift_check.drift_entries
            ],
        },
    )

@router.get("/export")
async def export_audit_package(
    company_id: UUID = Query(..., description="会社ID"),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> Response:
    """監査データ一括エクスポート（ZIP・総勘定元帳CSV・操作証跡CSV）。"""
    buf = io.BytesIO()

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        gl_csv = io.StringIO()
        gl_writer = csv.writer(gl_csv)
        gl_writer.writerow(["伝票番号", "取引日", "勘定科目コード", "勘定科目名", "借方金額", "貸方金額", "摘要"])

        journal_result = await db.execute(
            select(JournalHeader, JournalLine, Account)
            .join(JournalLine, JournalHeader.journal_header_id == JournalLine.journal_header_id)
            .outerjoin(Account, JournalLine.account_id == Account.account_id)
            .where(JournalHeader.company_id == company_id)
            .order_by(JournalHeader.journal_date, JournalHeader.journal_number)
        )
        for header, line, account in journal_result.all():
            gl_writer.writerow([
                header.journal_number,
                header.journal_date.isoformat() if header.journal_date else "",
                account.account_code if account else "",
                account.account_name if account else "",
                str(line.debit_amount) if line.debit_amount else "0",
                str(line.credit_amount) if line.credit_amount else "0",
                line.description or "",
            ])
        zf.writestr("general_ledger.csv", gl_csv.getvalue())

        audit_csv = io.StringIO()
        audit_writer = csv.writer(audit_csv)
        audit_writer.writerow([
            "ログID", "ユーザーID", "アクション", "リソース種別", "リソースID",
            "メソッド", "パス", "ステータスコード", "IPアドレス", "ユーザーエージェント", "日時"
        ])

        audit_result = await db.execute(
            select(AuditLog)
            .where(AuditLog.company_id == company_id)
            .order_by(AuditLog.created_at.desc())
            .limit(10000)
        )
        for log in audit_result.scalars().all():
            audit_writer.writerow([
                str(log.log_id),
                str(log.user_id) if log.user_id else "",
                log.action,
                log.resource_type,
                log.resource_id or "",
                log.method,
                log.path,
                log.status_code,
                log.ip_address or "",
                log.user_agent or "",
                log.created_at.isoformat() if log.created_at else "",
            ])
        zf.writestr("audit_logs.csv", audit_csv.getvalue())

        company_result = await db.execute(
            select(Company).where(Company.company_id == company_id)
        )
        company = company_result.scalar_one_or_none()
        company_name = company.company_name if company else "Unknown"

        manifest = f"""監査データエクスポート
会社名: {company_name}
会社ID: {company_id}
エクスポート日時: {datetime.now().isoformat()}
内容:
  - general_ledger.csv: 総勘定元帳
  - audit_logs.csv: 操作証跡ログ（最大10000件）
"""
        zf.writestr("MANIFEST.txt", manifest)

    buf.seek(0)
    filename = f"audit_export_{company_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
