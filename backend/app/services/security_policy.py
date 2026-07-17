"""テナントセキュリティポリシーサービス（フェーズ7）。

MFA要否・許可IP帯域（CIDR）・パスワード長・ロックアウト等のテナント単位ポリシーを
管理し、アクセス可否を判定する。

IP帯域判定・パスワード検証などの中核はDB非依存の純粋関数として切り出す。
"""
import ipaddress
import logging
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import TenantSecurityPolicy

logger = logging.getLogger(__name__)


# --- 純粋関数（DB非依存・テスト可能） ---------------------------------------

@dataclass
class SecurityPolicySpec:
    require_mfa: bool = False
    allowed_ip_cidrs: list[str] = field(default_factory=list)
    session_timeout_minutes: int = 60
    password_min_length: int = 8
    max_failed_attempts: int = 5


def ip_allowed(ip: str, cidrs: list[str]) -> bool:
    """IPアドレスが許可帯域に含まれるか判定する。

    許可帯域が空の場合は制限なし（全許可）。不正なCIDRは無視する。
    """
    if not cidrs:
        return True
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for cidr in cidrs:
        try:
            if addr in ipaddress.ip_network(cidr, strict=False):
                return True
        except ValueError:
            logger.warning("Invalid CIDR in security policy: %s", cidr)
            continue
    return False


def validate_password_length(password: str, min_length: int) -> bool:
    """パスワードが最小長を満たすか判定する。"""
    return len(password or "") >= min_length


def is_locked_out(failed_attempts: int, max_failed_attempts: int) -> bool:
    """失敗回数がロックアウト閾値に達したか判定する。"""
    return failed_attempts >= max_failed_attempts


def normalize_cidrs(cidrs: list[str]) -> list[str]:
    """CIDR文字列を正規化し、不正なものを除外する。"""
    normalized: list[str] = []
    for cidr in cidrs or []:
        try:
            normalized.append(str(ipaddress.ip_network(cidr, strict=False)))
        except ValueError:
            logger.warning("Dropping invalid CIDR: %s", cidr)
            continue
    return normalized


# --- 非同期サービス（DB依存） ------------------------------------------------

def _spec_from(policy: TenantSecurityPolicy) -> SecurityPolicySpec:
    return SecurityPolicySpec(
        require_mfa=policy.require_mfa,
        allowed_ip_cidrs=list(policy.allowed_ip_cidrs or []),
        session_timeout_minutes=policy.session_timeout_minutes,
        password_min_length=policy.password_min_length,
        max_failed_attempts=policy.max_failed_attempts,
    )


async def get_policy(db: AsyncSession, tenant_id: UUID) -> TenantSecurityPolicy | None:
    """テナントのセキュリティポリシーを取得する。"""
    result = await db.execute(
        select(TenantSecurityPolicy).where(TenantSecurityPolicy.tenant_id == tenant_id)
    )
    return result.scalar_one_or_none()


async def upsert_policy(
    db: AsyncSession,
    tenant_id: UUID,
    require_mfa: bool | None = None,
    allowed_ip_cidrs: list[str] | None = None,
    session_timeout_minutes: int | None = None,
    password_min_length: int | None = None,
    max_failed_attempts: int | None = None,
) -> TenantSecurityPolicy:
    """テナントのセキュリティポリシーを作成または更新する。"""
    policy = await get_policy(db, tenant_id)
    if allowed_ip_cidrs is not None:
        allowed_ip_cidrs = normalize_cidrs(allowed_ip_cidrs)

    if policy is None:
        policy = TenantSecurityPolicy(
            tenant_id=tenant_id,
            require_mfa=require_mfa if require_mfa is not None else False,
            allowed_ip_cidrs=allowed_ip_cidrs or [],
            session_timeout_minutes=session_timeout_minutes if session_timeout_minutes is not None else 60,
            password_min_length=password_min_length if password_min_length is not None else 8,
            max_failed_attempts=max_failed_attempts if max_failed_attempts is not None else 5,
        )
        db.add(policy)
    else:
        if require_mfa is not None:
            policy.require_mfa = require_mfa
        if allowed_ip_cidrs is not None:
            policy.allowed_ip_cidrs = allowed_ip_cidrs
        if session_timeout_minutes is not None:
            policy.session_timeout_minutes = session_timeout_minutes
        if password_min_length is not None:
            policy.password_min_length = password_min_length
        if max_failed_attempts is not None:
            policy.max_failed_attempts = max_failed_attempts

    await db.commit()
    await db.refresh(policy)
    return policy


async def check_ip_access(db: AsyncSession, tenant_id: UUID, ip: str) -> bool:
    """テナントのポリシーに照らしてIPアクセス可否を判定する。

    ポリシー未設定なら制限なし（許可）。
    """
    policy = await get_policy(db, tenant_id)
    if policy is None:
        return True
    return ip_allowed(ip, list(policy.allowed_ip_cidrs or []))
