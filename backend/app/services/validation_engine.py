from decimal import Decimal
from uuid import UUID

from app.schemas.schemas import JournalCreate


class ValidationError(Exception):
    def __init__(self, code: str, message: str, field: str | None = None):
        self.code = code
        self.message = message
        self.field = field
        super().__init__(f"[{code}] {message}")


class ValidationEngine:
    """Journal validation engine implementing VAL-001 through VAL-005."""

    @staticmethod
    def validate(journal: JournalCreate, created_by: UUID, approver_id: UUID | None = None) -> None:
        """Run all validation rules on a journal entry.

        Raises:
            ValidationError: If any validation rule fails.
        """
        ValidationEngine.val_001_debit_credit_balance(journal)
        ValidationEngine.val_002_required_fields(journal)
        ValidationEngine.val_003_amount_nonzero(journal)
        ValidationEngine.val_004_tax_consistency(journal)
        ValidationEngine.val_005_sod_check(created_by, approver_id)

    @staticmethod
    def val_001_debit_credit_balance(journal: JournalCreate) -> None:
        """VAL-001: Debit total must equal credit total."""
        debit_total = sum(
            (line.amount for line in journal.lines if line.debit_credit == "debit"),
            Decimal("0"),
        )
        credit_total = sum(
            (line.amount for line in journal.lines if line.debit_credit == "credit"),
            Decimal("0"),
        )
        if debit_total != credit_total:
            diff = debit_total - credit_total
            raise ValidationError(
                code="VAL-001",
                message=f"Debit-credit mismatch. Debit: {debit_total}, Credit: {credit_total}, Diff: {diff}",
                field="lines",
            )

    @staticmethod
    def val_002_required_fields(journal: JournalCreate) -> None:
        """VAL-002: All required fields must be present."""
        if not journal.transaction_date:
            raise ValidationError(code="VAL-002", message="transaction_date is required", field="transaction_date")
        if not journal.lines or len(journal.lines) < 2:
            raise ValidationError(code="VAL-002", message="At least 2 journal lines are required", field="lines")
        for i, line in enumerate(journal.lines):
            if not line.account_id:
                raise ValidationError(
                    code="VAL-002", message=f"account_id is required on line {i + 1}", field=f"lines[{i}].account_id"
                )
            if not line.debit_credit:
                raise ValidationError(
                    code="VAL-002", message=f"debit_credit is required on line {i + 1}", field=f"lines[{i}].debit_credit"
                )

    @staticmethod
    def val_003_amount_nonzero(journal: JournalCreate) -> None:
        """VAL-003/005: Amount must not be zero."""
        for i, line in enumerate(journal.lines):
            if line.amount == 0:
                raise ValidationError(
                    code="VAL-005", message=f"Amount must not be zero on line {i + 1}", field=f"lines[{i}].amount"
                )

    @staticmethod
    def val_004_tax_consistency(journal: JournalCreate) -> None:
        """VAL-004: Tax amount must be consistent with the line amount (basic check)."""
        for i, line in enumerate(journal.lines):
            if line.tax_amount < 0:
                raise ValidationError(
                    code="VAL-004",
                    message=f"Tax amount must not be negative on line {i + 1}",
                    field=f"lines[{i}].tax_amount",
                )

    @staticmethod
    def val_005_sod_check(created_by: UUID, approver_id: UUID | None) -> None:
        """VAL-005/SoD: Creator must not be the same as approver."""
        if approver_id is not None and created_by == approver_id:
            raise ValidationError(
                code="SOD-001",
                message="Segregation of Duties violation: creator cannot approve their own journal",
                field="approved_by",
            )
