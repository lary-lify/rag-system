"""
Authentication API: login, register (admin only), token refresh, change password.
"""
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_super_admin
from app.core.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from app.models.audit_log import AuditLog
from app.models.login_log import LoginLog
from app.models.user import User, UserRole
from app.schemas.common import (
    LoginRequest,
    TokenResponse,
    ChangePasswordRequest,
    UserCreate,
)

router = APIRouter()

# Import limiter from core
from app.core.limiter import limiter


@router.post("/login", response_model=TokenResponse)  # 用户登录：校验并签发JWT
@limiter.limit("10/minute")  # 限制每分钟最多10次登录尝试
async def login(
    body: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    接口说明：用户登录，校验用户名与密码后签发 JWT 访问令牌，并写入登录日志(login_logs)与审计日志(audit_logs)。
    方法路径：POST /api/auth/login
    鉴权要求：匿名（无需登录）
    请求参数：body.username(str,必填) 用户名; body.password(str,必填) 密码
    响应字段：access_token(str), token_type("bearer"), expires_in(int,秒), user_info{id,username,real_name,role}
    错误码：401 用户名或密码错误; 403 账户已禁用; 429 登录频率超限(10/min)
    """
    ip = request.client.host if request.client else ""
    ua = request.headers.get("user-agent", "")

    result = await db.execute(select(User).where(User.username == body.username))
    user = result.scalar_one_or_none()

    # Log attempt regardless of outcome
    log = LoginLog(
        user_id=user.id if user else 0,
        ip_address=ip,
        user_agent=ua,
    )

    if user is None or not verify_password(body.password, user.password_hash):
        log.success = False
        log.fail_reason = "Invalid credentials"
        db.add(log)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Username or password incorrect",
        )

    if user.status != "active":
        log.success = False
        log.fail_reason = "Account disabled"
        db.add(log)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )

    log.success = True
    db.add(log)
    await db.commit()

    # Create JWT
    token = create_access_token(
        user_id=user.id, username=user.username, role=user.role.value
    )
    expires_in = settings.JWT_EXPIRE_HOURS * 3600

    # Audit log
    audit = AuditLog(
        user_id=user.id,
        action="login",
        resource_type="user",
        resource_id=user.id,
        detail={"method": "password"},
        ip_address=ip,
        user_agent=ua,
    )
    db.add(audit)
    await db.commit()

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=expires_in,
        user_info={
            "id": user.id,
            "username": user.username,
            "real_name": user.real_name,
            "role": user.role.value,
        },
    )


@router.post("/register")  # 创建用户：仅超管
async def register_user(
    body: UserCreate,
    request: Request,
    current_user: User = Depends(require_super_admin()),
    db: AsyncSession = Depends(get_db),
):
    """
    接口说明：超级管理员创建新用户账号（可指定角色为 super_admin / dept_admin，否则默认为普通用户）。
    方法路径：POST /api/auth/register
    鉴权要求：超级管理员(super_admin)
    请求参数：body.username(str,必填), body.password(str,必填), body.real_name/email/phone/dept_name(选填), body.role(选填)
    响应字段：id, username, role
    错误码：400 用户名已存在; 401 未登录; 403 非超管
    """
    existing = await db.execute(select(User).where(User.username == body.username))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Username already exists")

    role_enum = UserRole(body.role) if body.role in ("super_admin", "dept_admin") else UserRole.user
    new_user = User(
        username=body.username,
        password_hash=hash_password(body.password),
        real_name=body.real_name or body.username,
        email=body.email,
        phone=body.phone,
        dept_name=body.dept_name,
        role=role_enum,
        status="active",
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    return {"id": new_user.id, "username": new_user.username, "role": new_user.role.value}


@router.post("/change-password")  # 修改密码：本人
@limiter.limit("5/minute")  # 限制每分钟最多5次修改密码
async def change_password(
    body: ChangePasswordRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    接口说明：已登录用户修改自己的登录密码（需校验原密码）。
    方法路径：POST /api/auth/change-password
    鉴权要求：已登录任意角色用户
    请求参数：body.old_password(str,必填) 原密码; body.new_password(str,必填) 新密码
    响应字段：detail("Password changed successfully")
    错误码：400 原密码错误; 401 未登录; 429 修改频率超限(5/min)
    """
    if not verify_password(body.old_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Current password incorrect")

    current_user.password_hash = hash_password(body.new_password)
    await db.commit()

    return {"detail": "Password changed successfully"}


@router.get("/me", response_model=dict)  # 当前用户信息
async def get_me(current_user: User = Depends(get_current_user)):
    """
    接口说明：获取当前登录用户的个人资料信息。
    方法路径：GET /api/auth/me
    鉴权要求：已登录任意角色用户
    请求参数：无
    响应字段：id, username, real_name, email, phone, dept_name, role, status, created_at
    错误码：401 未登录
    """
    return {
        "id": current_user.id,
        "username": current_user.username,
        "real_name": current_user.real_name,
        "email": current_user.email,
        "phone": current_user.phone,
        "dept_name": current_user.dept_name,
        "role": current_user.role.value,
        "status": current_user.status.value,
        "created_at": str(current_user.created_at),
    }
