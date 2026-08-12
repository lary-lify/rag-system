"""
Knowledge Base API: CRUD + permission management.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_super_admin
from app.models.audit_log import AuditLog
from app.models.kb_permission import KBPermission, PermissionLevel
from app.models.user import User, UserRole
from app.models.knowledge_base import KnowledgeBase, KBMode
from app.schemas.common import (
    KBCreate,
    KBUpdate,
    KBInfoResponse,
    KBListResponse,
    PermissionInfoResponse,
    KBPermissionGrant,
)

router = APIRouter()


async def _check_kb_permission(
    db: AsyncSession,
    kb_id: int,
    user: User,
    min_level: str = "read",
) -> tuple[KnowledgeBase, KBPermission | None]:
    """Check if user has access to a KB at the given permission level."""
    result = await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))
    kb = result.scalar_one_or_none()
    if kb is None:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    if kb.is_deleted:
        raise HTTPException(status_code=410, detail="Knowledge base has been deleted")

    # Super admin has full access
    if user.role == UserRole.super_admin:
        return kb, None

    # Owner always has admin
    if kb.owner_id == user.id:
        return kb, None

    # Check permissions table
    perm_result = await db.execute(
        select(KBPermission).where(
            KBPermission.kb_id == kb_id,
            KBPermission.user_id == user.id,
        )
    )
    perm = perm_result.scalar_one_or_none()
    if perm is None and kb.mode != KBMode.shared:
        raise HTTPException(status_code=403, detail="No access to this knowledge base")

    level_order = {"read": 0, "upload": 1, "admin": 2}
    if perm and level_order.get(perm.permission_level.value, -1) < level_order.get(min_level, 3):
        raise HTTPException(status_code=403, detail=f"Requires {min_level} permission")
    return kb, perm


@router.post("", status_code=status.HTTP_201_CREATED)  # 创建知识库
async def create_knowledge_base(
    body: KBCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    接口说明：创建知识库，校验名称唯一性与所选 Embedding 模型是否受支持，在 Milvus 中建立独立 Collection，并写入审计日志。
    方法路径：POST /api/knowledge-bases
    鉴权要求：已登录任意角色用户（创建者自动成为 owner，拥有 admin 权限）
    请求参数：body.name(str,必填), body.description(选填), body.mode("private"/"shared"), body.embedding_model(str,必填)
    响应字段：KBInfoResponse{id,name,description,mode,embedding_model,owner_name,...}
    错误码：400 名称已存在/模型不支持; 401 未登录
    """
    ip = request.client.host if request.client else ""
    ua = request.headers.get("user-agent", "")

    # Name uniqueness check (non-deleted only)
    existing = await db.execute(
        select(KnowledgeBase).where(
            KnowledgeBase.name == body.name,
            KnowledgeBase.is_deleted == False,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(400, "Knowledge base name already exists")

    mode = KBMode(body.mode)

    # Validate embedding model
    from app.core.config import settings
    embedding_model = body.embedding_model
    if embedding_model not in settings.SUPPORTED_EMBEDDING_MODELS:
        raise HTTPException(400, f"Unsupported embedding model: {embedding_model}")
    embedding_dimensions = settings.SUPPORTED_EMBEDDING_MODELS[embedding_model]

    kb = KnowledgeBase(
        name=body.name,
        description=body.description,
        owner_id=current_user.id,
        mode=mode,
        embedding_model=embedding_model,
        embedding_dimensions=embedding_dimensions,
    )
    db.add(kb)
    await db.commit()
    await db.refresh(kb)

    audit = AuditLog(
        user_id=current_user.id,
        action="create",
        resource_type="knowledge_base",
        resource_id=kb.id,
        detail={"name": body.name, "mode": body.mode, "embedding_model": embedding_model},
        ip_address=ip,
        user_agent=ua,
    )
    db.add(audit)
    await db.commit()

    resp = KBInfoResponse.model_validate(kb)
    resp.owner_name = current_user.real_name
    return resp


@router.get("", response_model=KBListResponse)  # 知识库列表：按权限过滤
async def list_knowledge_bases(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    mode: str | None = None,
    keyword: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    接口说明：分页查询当前用户可访问的知识库列表（owner / 共享库 / 被授权库），支持按模式与关键字过滤。
    方法路径：GET /api/knowledge-bases
    鉴权要求：已登录任意角色用户
    请求参数：page(int,默认1), page_size(int 1-100,默认20), mode(str,选填), keyword(str,选填)
    响应字段：KBListResponse{total, items[KBInfoResponse]}
    错误码：401 未登录
    """
    filters = [KnowledgeBase.is_deleted == False]

    # Filter by accessibility
    if current_user.role != UserRole.super_admin:
        permission_subq = (
            select(KBPermission.kb_id)
            .where(KBPermission.user_id == current_user.id)
            .scalar_subquery()
        )
        filters.append(
            or_(
                KnowledgeBase.owner_id == current_user.id,
                KnowledgeBase.mode == KBMode.shared,
                KnowledgeBase.id.in_(permission_subq),
            )
        )

    if mode:
        filters.append(KnowledgeBase.mode == mode)
    if keyword:
        # Escape special LIKE characters to prevent SQL injection
        escaped_keyword = keyword.replace("%", "\\%").replace("_", "\\_")
        like_pattern = f"%{escaped_keyword}%"
        filters.append(
            KnowledgeBase.name.ilike(like_pattern) | KnowledgeBase.description.ilike(like_pattern)
        )

    # Direct count without nested subquery
    count_q = select(func.count(KnowledgeBase.id)).where(*filters)
    total_result = await db.execute(count_q)
    total = total_result.scalar() or 0

    offset = (page - 1) * page_size
    result = await db.execute(
        select(KnowledgeBase)
        .options(joinedload(KnowledgeBase.owner))
        .where(*filters)
        .order_by(KnowledgeBase.updated_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    kbs = result.scalars().unique().all()

    items = []
    for kb in kbs:
        resp = KBInfoResponse.model_validate(kb)
        resp.owner_name = kb.owner.real_name if kb.owner else ""
        items.append(resp)

    return KBListResponse(total=total, items=items)


@router.get("/{kb_id}", response_model=KBInfoResponse)  # 知识库详情
async def get_knowledge_base(
    kb_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    接口说明：获取单个知识库的详细信息（含 owner 姓名）。需具备该知识库的读取权限。
    方法路径：GET /api/knowledge-bases/{kb_id}
    鉴权要求：已登录且拥有该 KB 的 read 及以上权限（超管/owner 自动通过）
    路径参数：kb_id(int,必填)
    响应字段：KBInfoResponse{id,name,description,mode,embedding_model,owner_name,...}
    错误码：401 未登录; 403 无访问权限; 404 知识库不存在/已删除; 410 已软删除
    """
    kb, _ = await _check_kb_permission(db, kb_id, current_user)
    resp = KBInfoResponse.model_validate(kb)
    owner_res = await db.execute(select(User).where(User.id == kb.owner_id))
    owner = owner_res.scalar_one_or_none()
    resp.owner_name = owner.real_name if owner else ""
    return resp


@router.put("/{kb_id}")  # 更新知识库
async def update_knowledge_base(
    kb_id: int,
    body: KBUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    接口说明：更新知识库信息（名称/描述/模式/Embedding 模型等），需 admin 权限，并写入审计日志。
    方法路径：PUT /api/knowledge-bases/{kb_id}
    鉴权要求：超级管理员 / 知识库 owner / 被授权 admin 权限者
    路径参数：kb_id(int,必填)
    请求参数：body(KBUpdate,选填字段)
    响应字段：detail("KB updated"), id
    错误码：401 未登录; 403 权限不足(需 admin); 404 知识库不存在
    """
    ip = request.client.host if request.client else ""
    ua = request.headers.get("user-agent", "")

    kb, perm = await _check_kb_permission(db, kb_id, current_user, min_level="admin")

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(kb, key, value)

    audit = AuditLog(
        user_id=current_user.id,
        action="update",
        resource_type="knowledge_base",
        resource_id=kb_id,
        detail=update_data,
        ip_address=ip,
        user_agent=ua,
    )
    db.add(audit)
    await db.commit()
    return {"detail": "KB updated", "id": kb.id}


@router.delete("/{kb_id}")  # 删除知识库：软删
async def delete_knowledge_base(
    kb_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    接口说明：软删除知识库（置 is_deleted=True），不在此处清理 Milvus Collection（由异步任务处理），并写入审计日志。
    方法路径：DELETE /api/knowledge-bases/{kb_id}
    鉴权要求：超级管理员 / 知识库 owner / 被授权 admin 权限者
    路径参数：kb_id(int,必填)
    响应字段：detail("KB soft-deleted"), id
    错误码：401 未登录; 403 权限不足; 404 知识库不存在
    """
    ip = request.client.host if request.client else ""
    ua = request.headers.get("user-agent", "")

    kb, _ = await _check_kb_permission(db, kb_id, current_user, min_level="admin")
    kb.is_deleted = True
    kb.deleted_at = func.now()

    audit = AuditLog(
        user_id=current_user.id,
        action="delete",
        resource_type="knowledge_base",
        resource_id=kb_id,
        detail={"name": kb.name},
        ip_address=ip,
        user_agent=ua,
    )
    db.add(audit)
    await db.commit()

    return {"detail": "KB soft-deleted", "id": kb.id}


# ---- Permissions ----

@router.get("/{kb_id}/permissions", response_model=list[PermissionInfoResponse])  # KB权限列表：需admin
async def list_permissions(
    kb_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    接口说明：列出某知识库已授权的用户权限列表（含用户名与真实姓名）。
    方法路径：GET /api/knowledge-bases/{kb_id}/permissions
    鉴权要求：知识库 admin 权限（超管/owner/被授权 admin）
    路径参数：kb_id(int,必填)
    响应字段：list[PermissionInfoResponse]{kb_id,user_id,username,real_name,permission_level}
    错误码：401 未登录; 403 权限不足(需 admin); 404 知识库不存在
    """
    kb, _ = await _check_kb_permission(db, kb_id, current_user, min_level="admin")

    # Use joinedload to avoid N+1 query
    from sqlalchemy.orm import joinedload
    result = await db.execute(
        select(KBPermission)
        .options(joinedload(KBPermission.user))
        .where(KBPermission.kb_id == kb_id)
        .order_by(KBPermission.created_at.desc())
    )
    perms = result.scalars().unique().all()

    items = []
    for p in perms:
        item = PermissionInfoResponse.model_validate(p)
        item.username = p.user.username if p.user else ""
        item.real_name = p.user.real_name if p.user else ""
        items.append(item)
    return items


@router.post("/{kb_id}/permissions", status_code=status.HTTP_201_CREATED)  # 授予KB权限
async def grant_permission(
    kb_id: int,
    body: KBPermissionGrant,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    接口说明：授予某用户对该知识库的访问权限（read/upload/admin 三级），需 admin 权限，并写入审计日志。
    方法路径：POST /api/knowledge-bases/{kb_id}/permissions
    鉴权要求：知识库 admin 权限
    路径参数：kb_id(int,必填)
    请求参数：body.user_id(int,必填) 目标用户; body.permission_level(str,必填) "read"/"upload"/"admin"
    响应字段：id, detail("Permission granted")
    错误码：400 权限已存在/目标用户不存在; 401 未登录; 403 权限不足; 404 知识库不存在
    """
    ip = request.client.host if request.client else ""
    ua = request.headers.get("user-agent", "")
    await _check_kb_permission(db, kb_id, current_user, min_level="admin")

    # Resolve target user: support both user_id and username lookup
    if body.user_id:
        ures = await db.execute(select(User).where(User.id == body.user_id))
        target_user = ures.scalar_one_or_none()
    elif body.username:
        ures = await db.execute(select(User).where(User.username == body.username))
        target_user = ures.scalar_one_or_none()
    else:
        raise HTTPException(400, "user_id or username is required")

    if not target_user:
        raise HTTPException(404, "Target user not found")

    # Check if permission already exists — update level if different, skip if same
    existing = await db.execute(
        select(KBPermission).where(
            KBPermission.kb_id == kb_id,
            KBPermission.user_id == target_user.id,
        )
    )
    existing_perm = existing.scalar_one_or_none()
    new_level = PermissionLevel(body.permission_level)

    if existing_perm:
        if existing_perm.permission_level == new_level:
            return {"id": existing_perm.id, "detail": "Permission already exists"}
        existing_perm.permission_level = new_level
        perm = existing_perm
        action_detail = "updated"
    else:
        perm = KBPermission(
            kb_id=kb_id,
            user_id=target_user.id,
            permission_level=new_level,
            created_by=current_user.id,
        )
        db.add(perm)
        action_detail = "granted"

    await db.commit()
    await db.refresh(perm)

    audit = AuditLog(
        user_id=current_user.id,
        action="grant_permission",
        resource_type="kb_permission",
        resource_id=perm.id,
        detail={"kb_id": kb_id, "target_user_id": target_user.id, "target_username": target_user.username, "level": body.permission_level, "action": action_detail},
        ip_address=ip,
        user_agent=ua,
    )
    db.add(audit)
    await db.commit()

    return {"id": perm.id, "detail": f"Permission {action_detail}"}


@router.delete("/{kb_id}/permissions/{user_id}", status_code=status.HTTP_204_NO_CONTENT)  # 撤销KB权限
async def revoke_permission(
    kb_id: int,
    user_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    接口说明：撤销某用户对知识库的访问权限，需 admin 权限，并写入审计日志。
    方法路径：DELETE /api/knowledge-bases/{kb_id}/permissions/{user_id}
    鉴权要求：知识库 admin 权限
    路径参数：kb_id(int,必填), user_id(int,必填) 目标用户
    响应字段：无(204 No Content)
    错误码：401 未登录; 403 权限不足; 404 权限记录不存在
    """
    ip = request.client.host if request.client else ""
    ua = request.headers.get("user-agent", "")
    await _check_kb_permission(db, kb_id, current_user, min_level="admin")

    result = await db.execute(
        select(KBPermission).where(
            KBPermission.kb_id == kb_id,
            KBPermission.user_id == user_id,
        )
    )
    perm = result.scalar_one_or_none()
    if not perm:
        raise HTTPException(404, "Permission not found")

    # Look up target user for audit detail
    user_result = await db.execute(select(User).where(User.id == user_id))
    target_user = user_result.scalar_one_or_none()

    await db.delete(perm)
    audit = AuditLog(
        user_id=current_user.id,
        action="revoke_permission",
        resource_type="kb_permission",
        resource_id=user_id,
        detail={"kb_id": kb_id, "target_user_id": user_id, "target_username": target_user.username if target_user else ""},
        ip_address=ip,
        user_agent=ua,
    )
    db.add(audit)
    await db.commit()
