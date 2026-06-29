from datetime import date
from decimal import Decimal, InvalidOperation
from io import StringIO
import csv
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, get_current_user, require_permission
from app.core.rbac import Permission
from app.models.models import Account, JournalHeader, JournalLine
from app.schemas.schemas import JournalCreate, JournalListResponse, JournalResponse
from app.services.journal_service import JournalService
from app.services.validation_engine import ValidationError, ValidationEngine

router = APIRouter()


@router.post("", response_model=JournalResponse, status_code=status.HTTP_201_CREATED)
async def create_journal(
    payload: JournalCreate,
    current_user: CurrentUser = Depends(require_permission(Permission.JOURNAL_CREATE)),
    db: AsyncSession = Depends(get_db),
) -> JournalHeader:
    """Create a new journal entry after validation."""
    try:
        ValidationEngine.validate(payload, created_by=current_user.user_id)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail={"code": e.code, "message": e.message, "field": e.field})

    # Use MAX instead of COUNT to avoid full table scan
    max_result = await db.execute(
        select(func.max(JournalHeader.journal_number))
        .where(JournalHeader.company_id == payload.company_id)
    )
    max_num = max_result.scalar()
    if max_num:
        try:
            seq = int(max_num.split("-")[1]) + 1
        except (IndexError, ValueError):
            seq = 1
    else:
        seq = 1
    journal_number = f"JRN-{seq:08d}"

    header = JournalHeader(
        company_id=payload.company_id,
        journal_number=journal_number,
        transaction_date=payload.transaction_date,
        voucher_type=payload.voucher_type,
        summary=payload.summary,
        approval_status="draft",
        created_by=current_user.user_id,
    )
    db.add(header)
    await db.flush()

    for i, line in enumerate(payload.lines, start=1):
        db.add(
            JournalLine(
                journal_header_id=header.journal_header_id,
                line_number=i,
                debit_credit=line.debit_credit,
                account_id=line.account_id,
                sub_account_id=line.sub_account_id,
                department_id=line.department_id,
                tax_rule_id=line.tax_rule_id,
                amount=line.amount,
                tax_amount=line.tax_amount,
                description=line.description,
            )
        )

    await db.flush()
    await db.refresh(header)
    return header


@router.get("", response_model=JournalListResponse)
async def list_journals(
    company_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: CurrentUser = Depends(require_permission(Permission.JOURNAL_READ)),
    db: AsyncSession = Depends(get_db),
) -> JournalListResponse:
    """List journals for a company with pagination."""
    offset = (page - 1) * page_size
    result = await db.execute(
        select(JournalHeader)
        .where(JournalHeader.company_id == company_id, JournalHeader.is_deleted == False)  # noqa: E712
        .order_by(JournalHeader.transaction_date.desc(), JournalHeader.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    items = result.scalars().all()

    count_result = await db.execute(
        select(func.count())
        .select_from(JournalHeader)
        .where(JournalHeader.company_id == company_id, JournalHeader.is_deleted == False)  # noqa: E712
    )
    total = count_result.scalar() or 0

    return JournalListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{journal_header_id}", response_model=JournalResponse)
async def get_journal(
    journal_header_id: UUID,
    current_user: CurrentUser = Depends(require_permission(Permission.JOURNAL_READ)),
    db: AsyncSession = Depends(get_db),
) -> JournalHeader:
    result = await db.execute(
        select(JournalHeader).where(
            JournalHeader.journal_header_id == journal_header_id,
            JournalHeader.is_deleted == False,  # noqa: E712
        )
    )
    journal = result.scalar_one_or_none()
    if not journal:
        raise HTTPException(status_code=404, detail="Journal not found")
    return journal


@router.put("/{journal_header_id}/void", response_model=JournalResponse)
async def void_journal(
    journal_header_id: UUID,
    current_user: CurrentUser = Depends(require_permission(Permission.JOURNAL_VOID)),
    db: AsyncSession = Depends(get_db),
) -> JournalHeader:
    result = await db.execute(
        select(JournalHeader).where(
            JournalHeader.journal_header_id == journal_header_id,
            JournalHeader.is_deleted == False,  # noqa: E712
        )
    )
    journal = result.scalar_one_or_none()
    if not journal:
        raise HTTPException(status_code=404, detail="Journal not found")
    if journal.is_voided:
        raise HTTPException(status_code=409, detail="Journal is already voided")

    journal.is_voided = True
    await db.flush()
    await db.refresh(journal)
    return journal


@router.put("/{journal_header_id}/approve", response_model=JournalResponse)
async def approve_journal(
    journal_header_id: UUID,
    current_user: CurrentUser = Depends(require_permission(Permission.JOURNAL_APPROVE)),
    db: AsyncSession = Depends(get_db),
) -> JournalHeader:
    """Approve a journal entry (SoD check enforced)."""
    try:
        return await JournalService.approve_journal(db, journal_header_id, current_user.user_id)
    except ValidationError as e:
        raise HTTPException(status_code=403, detail={"code": e.code, "message": e.message})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{journal_header_id}/post", response_model=JournalResponse)
async def post_journal(
    journal_header_id: UUID,
    current_user: CurrentUser = Depends(require_permission(Permission.JOURNAL_POST)),
    db: AsyncSession = Depends(get_db),
) -> JournalHeader:
    """Post an approved journal entry and update monthly balances."""
    try:
        return await JournalService.post_journal(db, journal_header_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# Journal CSV Export (標準フォーマット: Freee/MoneyForward互換)
# ---------------------------------------------------------------------------

@router.get("/export/csv", response_class=PlainTextResponse)
async def export_journals_csv(
    company_id: UUID,
    start_date: date = Query(..., description="開始日"),
    end_date: date = Query(..., description="終了日"),
    current_user: CurrentUser = Depends(require_permission(Permission.JOURNAL_READ)),
    db: AsyncSession = Depends(get_db),
) -> str:
    """仕訳CSVを標準フォーマット（Freee/MoneyForward互換）で出力する。

    ヘッダー: 取引No,取引日,借方勘目,借方補助勘目,貸方勘目,貸方補助勘目,摘要,金額,税区分
    複式仕訳を1行1取引に展開（借方・貸方のペアを1行に出力）。
    """
    result = await db.execute(
        select(JournalHeader, Account, JournalLine)
        .join(JournalLine, JournalHeader.journal_header_id == JournalLine.journal_header_id)
        .join(Account, JournalLine.account_id == Account.account_id)
        .where(
            JournalHeader.company_id == company_id,
            JournalHeader.is_deleted == False,  # noqa: E712
            JournalHeader.is_voided == False,  # noqa: E712
            JournalLine.is_deleted == False,  # noqa: E712
            JournalHeader.transaction_date >= start_date,
            JournalHeader.transaction_date <= end_date,
        )
        .order_by(JournalHeader.transaction_date, JournalHeader.journal_number, JournalLine.line_number)
    )
    rows = result.all()

    # Group lines by journal header
    headers_map: dict[UUID, dict] = {}
    for header, account, line in rows:
        if header.journal_header_id not in headers_map:
            headers_map[header.journal_header_id] = {
                "number": header.journal_number,
                "date": header.transaction_date.isoformat(),
                "summary": header.summary or "",
                "debit_lines": [],
                "credit_lines": [],
            }
        entry = {
            "account_code": account.account_code,
            "account_name": account.account_name,
            "amount": str(line.amount),
            "description": line.description or "",
        }
        if line.debit_credit == "debit":
            headers_map[header.journal_header_id]["debit_lines"].append(entry)
        else:
            headers_map[header.journal_header_id]["credit_lines"].append(entry)

    lines = ["取引No,取引日,借方勘目,借方補助勘目,貸方勘目,貸方補助勘目,摘要,金額,税区分"]
    for h_id, data in headers_map.items():
        for d in data["debit_lines"]:
            for c in data["credit_lines"]:
                lines.append(
                    f"{data['number']},{data['date']},{d['account_name']},"
                    f",{c['account_name']},,{data['summary']},{d['amount']},対象外"
                )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Journal CSV Import (Freee/MoneyForward互換フォーマット)
# ---------------------------------------------------------------------------

@router.post("/import/csv")
async def import_journals_csv(
    company_id: UUID,
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(require_permission(Permission.JOURNAL_CREATE)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Freee/MoneyForward互換のCSVファイルから仕訳を一括インポートする。

    期待するCSVヘッダー: 取引日,借方勘目,貸方勘目,摘要,金額
    （借方補助勘目,貸方補助勘目,税区分は任意）
    """
    content = await file.read()
    text = content.decode("utf-8-sig")  # BOM対応

    reader = csv.DictReader(StringIO(text))
    # Normalize header names (strip whitespace, handle variations)
    fieldnames = [f.strip() for f in reader.fieldnames or []]

    # Map common header variations
    header_map = {}
    for fn in fieldnames:
        fn_lower = fn.lower().replace(" ", "")
        if fn_lower in ("取引日", "日付", "date", "取引no"):
            if fn_lower != "取引no":
                header_map["date"] = fn
        elif fn_lower in ("借方勘目", "借方科目", "debitaccount"):
            header_map["debit_account"] = fn
        elif fn_lower in ("借方補助勘目", "借方補助科目", "debitsub"):
            header_map["debit_sub"] = fn
        elif fn_lower in ("貸方勘目", "貸方科目", "creditaccount"):
            header_map["credit_account"] = fn
        elif fn_lower in ("貸方補助勘目", "貸方補助科目", "creditsub"):
            header_map["credit_sub"] = fn
        elif fn_lower in ("摘要", "備考", "summary", "description"):
            header_map["summary"] = fn
        elif fn_lower in ("金額", "amount"):
            header_map["amount"] = fn

    required = ["date", "debit_account", "credit_account", "amount"]
    missing = [r for r in required if r not in header_map]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"CSVヘッダーに必須項目が不足しています: {', '.join(missing)}"
        )

    # Load all accounts for this company (by name and code)
    acct_result = await db.execute(
        select(Account).where(
            Account.company_id == company_id,
            Account.is_deleted == False,  # noqa: E712
            Account.is_active == True,  # noqa: E712
        )
    )
    accounts = acct_result.scalars().all()
    acct_by_name = {a.account_name: a for a in accounts}
    acct_by_code = {a.account_code: a for a in accounts}

    # Get next journal number
    max_result = await db.execute(
        select(func.max(JournalHeader.journal_number))
        .where(JournalHeader.company_id == company_id)
    )
    max_num = max_result.scalar()
    seq = int(max_num.split("-")[1]) + 1 if max_num else 1

    imported = 0
    errors: list[str] = []

    for i, row in enumerate(reader, start=2):  # row 1 is header
        try:
            raw_date = row[header_map["date"]].strip()
            debit_name = row[header_map["debit_account"]].strip()
            credit_name = row[header_map["credit_account"]].strip()
            summary = row.get(header_map.get("summary", ""), "").strip() if header_map.get("summary") else ""
            amount_str = row[header_map["amount"]].strip().replace(",", "").replace("¥", "")

            if not raw_date or not debit_name or not credit_name or not amount_str:
                errors.append(f"行{i}: 必須項目が空です")
                continue

            amount = Decimal(amount_str)
            txn_date = date.fromisoformat(raw_date)

            # Find accounts by name or code
            debit_acct = acct_by_name.get(debit_name) or acct_by_code.get(debit_name)
            credit_acct = acct_by_name.get(credit_name) or acct_by_code.get(credit_name)

            if not debit_acct:
                errors.append(f"行{i}: 借方勘定科目「{debit_name}」が見つかりません")
                continue
            if not credit_acct:
                errors.append(f"行{i}: 貸方勘定科目「{credit_name}」が見つかりません")
                continue

            journal_number = f"JRN-{seq:08d}"
            seq += 1

            header = JournalHeader(
                company_id=company_id,
                journal_number=journal_number,
                transaction_date=txn_date,
                voucher_type="import",
                summary=summary,
                approval_status="draft",
                source_type="csv_import",
                created_by=current_user.user_id,
            )
            db.add(header)
            await db.flush()

            db.add(JournalLine(
                journal_header_id=header.journal_header_id,
                line_number=1,
                debit_credit="debit",
                account_id=debit_acct.account_id,
                amount=amount,
                description=summary,
            ))
            db.add(JournalLine(
                journal_header_id=header.journal_header_id,
                line_number=2,
                debit_credit="credit",
                account_id=credit_acct.account_id,
                amount=amount,
                description=summary,
            ))

            imported += 1
        except (InvalidOperation, ValueError) as e:
            errors.append(f"行{i}: {str(e)}")
            continue

    await db.flush()

    return {
        "imported": imported,
        "errors": errors,
        "total_rows": i,
    }


# ---------------------------------------------------------------------------
# General Ledger (総勘定元帳)
# ---------------------------------------------------------------------------

@router.get("/general-ledger")
async def get_general_ledger(
    company_id: UUID,
    start_date: date = Query(..., description="開始日"),
    end_date: date = Query(..., description="終了日"),
    account_code: str | None = Query(None, description="科目コード（指定時は該当科目のみ）"),
    current_user: CurrentUser = Depends(require_permission(Permission.JOURNAL_READ)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """総勘定元帳を取得する。

    指定期間の取引を科目ごとに集計し、期首残高・借方発生・貸方発生・期末残高を返す。
    """
    # Build query
    query = (
        select(
            Account.account_id,
            Account.account_code,
            Account.account_name,
            Account.account_type,
            Account.debit_credit,
            JournalHeader.transaction_date,
            JournalHeader.journal_number,
            JournalHeader.summary,
            JournalLine.debit_credit,
            JournalLine.amount,
            JournalLine.description,
        )
        .join(JournalLine, Account.account_id == JournalLine.account_id)
        .join(JournalHeader, JournalLine.journal_header_id == JournalHeader.journal_header_id)
        .where(
            Account.company_id == company_id,
            Account.is_deleted == False,  # noqa: E712
            JournalHeader.is_deleted == False,  # noqa: E712
            JournalHeader.is_voided == False,  # noqa: E712
            JournalLine.is_deleted == False,  # noqa: E712
            JournalHeader.transaction_date >= start_date,
            JournalHeader.transaction_date <= end_date,
        )
        .order_by(Account.account_code, JournalHeader.transaction_date, JournalHeader.journal_number)
    )

    if account_code:
        query = query.where(Account.account_code == account_code)

    result = await db.execute(query)
    rows = result.all()

    # Get opening balances (transactions before start_date)
    opening_query = (
        select(
            Account.account_id,
            Account.account_code,
            Account.account_name,
            Account.account_type,
            Account.debit_credit,
            func.coalesce(
                func.sum(
                    case(
                        (JournalLine.debit_credit == "debit", JournalLine.amount),
                        else_=Decimal("0"),
                    )
                ), 0
            ).label("opening_debit"),
            func.coalesce(
                func.sum(
                    case(
                        (JournalLine.debit_credit == "credit", JournalLine.amount),
                        else_=Decimal("0"),
                    )
                ), 0
            ).label("opening_credit"),
        )
        .outerjoin(
            JournalLine,
            (JournalLine.account_id == Account.account_id) & (JournalLine.is_deleted == False),  # noqa: E712
        )
        .outerjoin(
            JournalHeader,
            (JournalHeader.journal_header_id == JournalLine.journal_header_id)
            & (JournalHeader.company_id == company_id)
            & (JournalHeader.transaction_date < start_date)
            & (JournalHeader.is_deleted == False)  # noqa: E712
            & (JournalHeader.is_voided == False),  # noqa: E712
        )
        .where(
            Account.company_id == company_id,
            Account.is_deleted == False,  # noqa: E712
            Account.is_active == True,  # noqa: E712
        )
        .group_by(
            Account.account_id,
            Account.account_code,
            Account.account_name,
            Account.account_type,
            Account.debit_credit,
        )
        .order_by(Account.account_code)
    )

    if account_code:
        opening_query = opening_query.where(Account.account_code == account_code)

    opening_result = await db.execute(opening_query)
    opening_rows = opening_result.all()

    # Build opening balance map
    opening_map: dict[UUID, dict] = {}
    for row in opening_rows:
        op_debit = Decimal(row.opening_debit) if row.opening_debit else Decimal("0")
        op_credit = Decimal(row.opening_credit) if row.opening_credit else Decimal("0")
        balance = op_debit - op_credit
        if row.debit_credit == "credit":
            balance = -balance
        opening_map[row.account_id] = {
            "account_code": row.account_code,
            "account_name": row.account_name,
            "account_type": row.account_type,
            "opening_balance": balance,
            "entries": [],
            "total_debit": Decimal("0"),
            "total_credit": Decimal("0"),
        }

    # Add current period entries
    for row in rows:
        if row.account_id not in opening_map:
            opening_map[row.account_id] = {
                "account_code": row.account_code,
                "account_name": row.account_name,
                "account_type": row.account_type,
                "opening_balance": Decimal("0"),
                "entries": [],
                "total_debit": Decimal("0"),
                "total_credit": Decimal("0"),
            }
        entry = {
            "date": row.transaction_date.isoformat(),
            "journal_number": row.journal_number,
            "summary": row.summary or "",
            "debit_credit": row.debit_credit,
            "amount": str(row.amount),
            "description": row.description or "",
        }
        opening_map[row.account_id]["entries"].append(entry)
        if row.debit_credit == "debit":
            opening_map[row.account_id]["total_debit"] += Decimal(row.amount)
        else:
            opening_map[row.account_id]["total_credit"] += Decimal(row.amount)

    # Build response
    accounts_list = []
    for acct_id, data in opening_map.items():
        opening = data["opening_balance"]
        total_debit = data["total_debit"]
        total_credit = data["total_credit"]
        # Calculate closing balance
        if data["account_type"] in ("asset", "expense"):
            closing = opening + total_debit - total_credit
        else:
            closing = opening - total_debit + total_credit

        accounts_list.append({
            "account_code": data["account_code"],
            "account_name": data["account_name"],
            "account_type": data["account_type"],
            "opening_balance": str(opening),
            "total_debit": str(total_debit),
            "total_credit": str(total_credit),
            "closing_balance": str(closing),
            "entries": data["entries"],
        })

    return {
        "start_date": str(start_date),
        "end_date": str(end_date),
        "accounts": accounts_list,
    }


@router.get("/general-ledger/export", response_class=PlainTextResponse)
async def export_general_ledger_csv(
    company_id: UUID,
    start_date: date = Query(..., description="開始日"),
    end_date: date = Query(..., description="終了日"),
    account_code: str | None = Query(None, description="科目コード"),
    current_user: CurrentUser = Depends(require_permission(Permission.JOURNAL_READ)),
    db: AsyncSession = Depends(get_db),
) -> str:
    """総勘定元帳をCSV形式で出力する。"""
    # Reuse the general ledger logic
    result = await get_general_ledger(
        company_id=company_id,
        start_date=start_date,
        end_date=end_date,
        account_code=account_code,
        current_user=current_user,
        db=db,
    )

    lines = ["科目コード,科目名,取引日,伝票No,摘要,借方金額,貸方金額,残高"]

    for acct in result["accounts"]:
        running_balance = Decimal(acct["opening_balance"])
        # Opening balance line
        lines.append(f"{acct['account_code']},{acct['account_name']},,,,期首残高,,{running_balance}")

        for entry in acct["entries"]:
            amt = Decimal(entry["amount"])
            if entry["debit_credit"] == "debit":
                running_balance += amt
                lines.append(
                    f"{acct['account_code']},{acct['account_name']},"
                    f"{entry['date']},{entry['journal_number']},{entry['summary']},"
                    f"{amt},,{running_balance}"
                )
            else:
                running_balance -= amt
                lines.append(
                    f"{acct['account_code']},{acct['account_name']},"
                    f"{entry['date']},{entry['journal_number']},{entry['summary']},"
                    f",,{amt},{running_balance}"
                )

        lines.append(f"{acct['account_code']},{acct['account_name']},,,,期末残高,,{running_balance}")
        lines.append("")

    return "\n".join(lines)
