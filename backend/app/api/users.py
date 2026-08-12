"""
Users API: CRUD for user management (super_admin / dept_admin).
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_dept_admin_or_above, require_super_admin
from app.core.security import hash_password
from app.models.audit_log import AuditLog
from app.models.user import User, UserRole, UserStatus
from app.schemas.common import (
    UserInfoResponse,
    UserListResponse,
    UserCreate,
    UserUpdate,
)

router = APIRouter()


@router.get("", response_model=UserListResponse)  # 用户列表：分页/筛选（部门管理员限本部门）
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    role: str | None = None,
    dept_name: str | None = None,
    keyword: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    接口说明：分页查询用户列表，支持按角色/部门/关键字(用户名/姓名/邮箱)过滤；部门管理员仅能查看本部门的用户。
    方法路径：GET /api/users
    鉴权要求：已登录任意角色用户（普通用户实际可见列表为空）
    请求参数：page(int,默认1), page_size(int 1-100,默认20), role(str,选填), dept_name(str,选填), keyword(str,选填)
    响应字段：UserListResponse{total, items[UserInfoResponse]}
    错误码：401 未登录; 403 越权访问其他部门
    """
    query = select(User).where(User.is_deleted is not True if hasattr(User, 'is_deleted') else True)
    count_q = select(func.count(User.id))

    # Role filter: regular users see nothing (handled by permission), dept_admin sees own dept
    if current_user.role == UserRole.dept_admin:
        query = query.where(User.dept_name == current_user.dept_name)
        count_q = count_q.where(User.dept_name == current_user.dept_name)

    if role:
        query = query.where(User.role == role)
        count_q = count_q.where(User.role == role)
    if dept_name:
        query = query.where(User.dept_name == dept_name)
        count_q = count_q.where(User.dept_name == dept_name)
    if keyword:
        # Escape special LIKE characters to prevent SQL injection
        escaped_keyword = keyword.replace("%", "\\%").replace("_", "\\_")
        like_pattern = f"%{escaped_keyword}%"
        query = query.where(
            User.username.ilike(like_pattern) | User.real_name.ilike(like_pattern) | User.email.ilike(like_pattern)
        )
        count_q = count_q.where(
            User.username.ilike(like_pattern) | User.real_name.ilike(like_pattern) | User.email.ilike(like_pattern)
        )

    total_result = await db.execute(count_q)
    total = total_result.scalar() or 0

    offset = (page - 1) * page_size
    result = await db.execute(query.order_by(User.id.desc()).offset(offset).limit(page_size))
    users = result.scalars().all()

    return UserListResponse(
        total=total,
        items=[UserInfoResponse.model_validate(u) for u in users],
    )


@router.get("/{user_id}", response_model=UserInfoResponse)  # 用户详情
async def get_user(
    user_id: int,
    current_user: User = Depends(require_dept_admin_or_above()),
    db: AsyncSession = Depends(get_db),
):
    """
    接口说明：获取指定用户的详细信息；部门管理员仅能查看本部门用户。
    方法路径：GET /api/users/{user_id}
    鉴权要求：部门管理员及以上(require_dept_admin_or_above)
    路径参数：user_id(int,必填) 用户ID
    响应字段：UserInfoResponse{id,username,real_name,email,phone,dept_name,role,status,...}
    错误码：401 未登录; 403 越权(非本部门或越级); 404 用户不存在
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    # Dept admin can only view same-dept users
    if current_user.role == UserRole.dept_admin:
        if user.dept_name != current_user.dept_name:
            raise HTTPException(status_code=403, detail="Cannot view users from other departments")

    return UserInfoResponse.model_validate(user)


@router.put("/{user_id}")  # 更新用户
async def update_user(
    user_id: int,
    body: UserUpdate,
    request: Request,
    current_user: User = Depends(require_dept_admin_or_above()),
    db: AsyncSession = Depends(get_db),
):
    """
    接口说明：更新指定用户信息（姓名/邮箱/电话/部门/状态/角色等）；部门管理员仅能编辑本部门非管理员用户，且不可将角色提升为管理员。
    方法路径：PUT /api/users/{user_id}
    鉴权要求：部门管理员及以上
    路径参数：user_id(int,必填)
    请求参数：body(UserUpdate,选填字段) real_name/email/phone/dept_name/status/role 等
    响应字段：detail("User updated"), id
    错误码：401 未登录; 403 越权(编辑管理员/跨部门/提权); 404 用户不存在
    """
    ip = request.client.host if request.client else ""
    ua = request.headers.get("user-agent", "")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    # Dept admin can only edit same-dept non-admin users
    if current_user.role == UserRole.dept_admin:
        if user.role in (UserRole.super_admin, UserRole.dept_admin):
            raise HTTPException(status_code=403, detail="Cannot edit admin users")
        if user.dept_name != current_user.dept_name:
            raise HTTPException(status_code=403, detail="Cannot edit users from other departments")
        # Dept admin cannot change role to admin
        if body.role and body.role in ("super_admin", "dept_admin"):
            raise HTTPException(status_code=403, detail="Cannot assign admin roles")

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(user, key, value)

    audit = AuditLog(
        user_id=current_user.id,
        action="update",
        resource_type="user",
        resource_id=user_id,
        detail=update_data,
        ip_address=ip,
        user_agent=ua,
    )
    db.add(audit)
    await db.commit()

    return {"detail": "User updated", "id": user.id}


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)  # 删除用户：仅超管
async def delete_user(
    user_id: int,
    request: Request,
    current_user: User = Depends(require_super_admin()),
    db: AsyncSession = Depends(get_db),
):
    """
    接口说明：删除用户（软禁用，将 status 置为 disabled 而非物理删除，以保留引用关系），并写入审计日志。
    方法路径：DELETE /api/users/{user_id}
    鉴权要求：超级管理员(super_admin)
    路径参数：user_id(int,必填)
    响应字段：无(204 No Content)
    错误码：401 未登录; 403 非超管; 400 不可删除超级管理员; 404 用户不存在
    """
    ip = request.client.host if request.client else ""
    ua = request.headers.get("user-agent", "")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role == UserRole.super_admin:
        raise HTTPException(status_code=400, detail="Cannot delete super admin")

    # Soft disable instead of hard delete to preserve references
    user.status = UserStatus.disabled

    audit = AuditLog(
        user_id=current_user.id,
        action="delete",
        resource_type="user",
        resource_id=user_id,
        detail={"username": user.username},
        ip_address=ip,
        user_agent=ua,
    )
    db.add(audit)
    await db.commit()
