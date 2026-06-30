from fastapi import APIRouter

from app.api.v1.endpoints import (
    ai,
    approvals,
    attendance,
    audit,
    auth,
    bank,
    bonus,
    budgets,
    companies,
    expenses,
    fixed_assets,
    integrations,
    invoices,
    journals,
    knowledge,
    masters,
    notifications,
    partners,
    payroll,
    rbac,
    reports,
    tax_returns,
    year_end,
)

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(rbac.router, prefix="/rbac", tags=["RBAC"])
api_router.include_router(companies.router, prefix="/companies", tags=["Companies"])
api_router.include_router(journals.router, prefix="/journals", tags=["Journals"])
api_router.include_router(approvals.router, prefix="/approvals", tags=["Approvals"])
api_router.include_router(masters.router, prefix="/masters", tags=["Masters"])
api_router.include_router(reports.router, prefix="/reports", tags=["Reports"])
api_router.include_router(budgets.router, prefix="/budgets", tags=["Budgets"])
api_router.include_router(bank.router, prefix="/bank", tags=["Bank"])
api_router.include_router(ai.router, prefix="/ai", tags=["AI"])
api_router.include_router(integrations.router, prefix="/integrations", tags=["Integrations"])
api_router.include_router(knowledge.router, prefix="/knowledge", tags=["Knowledge"])
api_router.include_router(fixed_assets.router, prefix="/fixed-assets", tags=["Fixed Assets"])
api_router.include_router(payroll.router, prefix="/payroll", tags=["Payroll"])
api_router.include_router(partners.router, prefix="/partners", tags=["Partners"])
api_router.include_router(bonus.router, prefix="/bonus", tags=["Bonus"])
api_router.include_router(year_end.router, prefix="/year-end", tags=["Year-End Adjustment"])
api_router.include_router(attendance.router, prefix="/attendance", tags=["Attendance"])
api_router.include_router(expenses.router, prefix="/expenses", tags=["Expenses"])
api_router.include_router(invoices.router, prefix="/invoices", tags=["Invoices"])
api_router.include_router(tax_returns.router, prefix="/tax-returns", tags=["Tax Returns"])
api_router.include_router(audit.router, prefix="/audit", tags=["Audit"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["Notifications"])
