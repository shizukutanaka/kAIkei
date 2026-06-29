from fastapi import APIRouter

from app.api.v1.endpoints import ai, approvals, auth, bonus, companies, fixed_assets, integrations, journals, knowledge, masters, partners, payroll, rbac, reports

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(rbac.router, prefix="/rbac", tags=["RBAC"])
api_router.include_router(companies.router, prefix="/companies", tags=["Companies"])
api_router.include_router(journals.router, prefix="/journals", tags=["Journals"])
api_router.include_router(approvals.router, prefix="/approvals", tags=["Approvals"])
api_router.include_router(masters.router, prefix="/masters", tags=["Masters"])
api_router.include_router(reports.router, prefix="/reports", tags=["Reports"])
api_router.include_router(ai.router, prefix="/ai", tags=["AI"])
api_router.include_router(integrations.router, prefix="/integrations", tags=["Integrations"])
api_router.include_router(knowledge.router, prefix="/knowledge", tags=["Knowledge"])
api_router.include_router(fixed_assets.router, prefix="/fixed-assets", tags=["Fixed Assets"])
api_router.include_router(payroll.router, prefix="/payroll", tags=["Payroll"])
api_router.include_router(partners.router, prefix="/partners", tags=["Partners"])
api_router.include_router(bonus.router, prefix="/bonus", tags=["Bonus"])
