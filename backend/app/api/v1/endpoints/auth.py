import time

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, get_current_user
from app.core.security import create_access_token, create_refresh_token, decode_token, hash_password, verify_password
from app.models.models import Tenant, User
from app.schemas.schemas import TokenRefreshRequest, TokenResponse, UserCreate, UserResponse
from app.services import mfa as mfa_service

router = APIRouter()

MFA_REQUIRED_DETAIL = "MFA code required"


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: UserCreate, db: AsyncSession = Depends(get_db)) -> User:
    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    tenant_result = await db.execute(select(Tenant).where(Tenant.tenant_code == payload.tenant_code))
    tenant = tenant_result.scalar_one_or_none()
    if not tenant:
        tenant = Tenant(tenant_name=payload.tenant_code, tenant_code=payload.tenant_code)
        db.add(tenant)
        await db.flush()

    user = User(
        tenant_id=tenant.tenant_id,
        email=payload.email,
        password_hash=hash_password(payload.password),
        display_name=payload.display_name,
        role="admin",
    )
    db.add(user)
    await db.flush()
    return user


class LoginRequest(BaseModel):
    email: str
    password: str
    mfa_code: str | None = None


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    result = await db.execute(select(User).where(User.email == payload.email, User.is_deleted == False))  # noqa: E712
    user = result.scalar_one_or_none()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="User is inactive")

    if user.mfa_enabled and user.mfa_secret:
        if not payload.mfa_code:
            raise HTTPException(status_code=401, detail=MFA_REQUIRED_DETAIL)
        # TOTP を優先し、一致しなければバックアップコード（単回使用）で復旧を許可する。
        totp_ok = await mfa_service.verify_and_consume_totp(db, user, payload.mfa_code, int(time.time()))
        if not totp_ok and not await mfa_service.consume_backup_code(db, user, payload.mfa_code):
            raise HTTPException(status_code=401, detail="Invalid MFA code")

    access_token = create_access_token(
        subject=str(user.user_id),
        extra_claims={"tenant_id": str(user.tenant_id), "role": user.role},
    )
    refresh_token = create_refresh_token(subject=str(user.user_id))
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(payload: TokenRefreshRequest) -> TokenResponse:
    decoded = decode_token(payload.refresh_token)
    if not decoded or decoded.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    user_id = decoded.get("sub")
    access_token = create_access_token(subject=user_id)
    new_refresh = create_refresh_token(subject=user_id)
    return TokenResponse(access_token=access_token, refresh_token=new_refresh)


class MfaSetupRequest(BaseModel):
    current_code: str | None = None


class MfaSetupResponse(BaseModel):
    secret: str
    otpauth_uri: str


class MfaCodeRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=8)


class MfaStatusResponse(BaseModel):
    mfa_enabled: bool


@router.get("/mfa/status", response_model=MfaStatusResponse)
async def mfa_status(
    current_user: CurrentUser = Depends(get_current_user),
) -> MfaStatusResponse:
    """自ユーザーのMFA有効状態を返す。"""
    return MfaStatusResponse(mfa_enabled=current_user.mfa_enabled)


@router.post("/mfa/setup", response_model=MfaSetupResponse)
async def mfa_setup(
    payload: MfaSetupRequest = MfaSetupRequest(),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MfaSetupResponse:
    """TOTP秘密鍵を発行する（認証アプリ登録用。enableで有効化するまで未適用）。

    MFAが既に有効なアカウントで秘密鍵を再発行（ローテーション）する場合は、
    現在のTOTPコード（current_code）の検証が必要（盗まれたアクセストークン
    だけでMFAを無効化できてしまうことを防ぐため）。
    """
    try:
        result = await mfa_service.setup_mfa(
            db, current_user.user_id, payload.current_code, int(time.time())
        )
    except mfa_service.MfaReauthRequired:
        raise HTTPException(status_code=403, detail="Current MFA code required to re-setup") from None
    if result is None:
        raise HTTPException(status_code=404, detail="User not found")
    secret, otpauth_uri = result
    return MfaSetupResponse(secret=secret, otpauth_uri=otpauth_uri)


@router.post("/mfa/enable", response_model=MfaStatusResponse)
async def mfa_enable(
    payload: MfaCodeRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MfaStatusResponse:
    """認証アプリのコードを検証してMFAを有効化する。"""
    ok = await mfa_service.enable_mfa(db, current_user.user_id, payload.code, int(time.time()))
    if not ok:
        raise HTTPException(status_code=400, detail="Invalid MFA code (setup required first)")
    return MfaStatusResponse(mfa_enabled=True)


class MfaBackupCodesResponse(BaseModel):
    codes: list[str]
    remaining: int


class MfaBackupCodesStatusResponse(BaseModel):
    remaining: int


@router.get("/mfa/backup-codes/status", response_model=MfaBackupCodesStatusResponse)
async def mfa_backup_codes_status(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MfaBackupCodesStatusResponse:
    """未使用のバックアップコード残数を返す。"""
    result = await db.execute(select(User).where(User.user_id == current_user.user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return MfaBackupCodesStatusResponse(remaining=mfa_service.count_unused_backup_codes(user.mfa_backup_codes))


@router.post("/mfa/backup-codes", response_model=MfaBackupCodesResponse)
async def mfa_regenerate_backup_codes(
    payload: MfaCodeRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MfaBackupCodesResponse:
    """現在のTOTPコードを検証し、バックアップコードを再生成する（平文は一度だけ返す）。

    TOTP認証器を紛失した際のログイン復旧手段。既存のバックアップコードは無効化される。
    """
    codes = await mfa_service.regenerate_backup_codes(
        db, current_user.user_id, payload.code, int(time.time())
    )
    if codes is None:
        raise HTTPException(status_code=400, detail="Invalid MFA code or MFA not enabled")
    return MfaBackupCodesResponse(codes=codes, remaining=len(codes))


@router.post("/mfa/disable", response_model=MfaStatusResponse)
async def mfa_disable(
    payload: MfaCodeRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MfaStatusResponse:
    """コードを検証してMFAを無効化し、秘密鍵を破棄する。"""
    ok = await mfa_service.disable_mfa(db, current_user.user_id, payload.code, int(time.time()))
    if not ok:
        raise HTTPException(status_code=400, detail="Invalid MFA code")
    return MfaStatusResponse(mfa_enabled=False)
