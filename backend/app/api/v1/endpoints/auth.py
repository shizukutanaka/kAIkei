from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import create_access_token, create_refresh_token, decode_token, hash_password, verify_password
from app.models.models import Tenant, User
from app.schemas.schemas import TokenRefreshRequest, TokenResponse, UserCreate, UserResponse

router = APIRouter()


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


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    result = await db.execute(select(User).where(User.email == payload.email, User.is_deleted == False))  # noqa: E712
    user = result.scalar_one_or_none()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="User is inactive")

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
