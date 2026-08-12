"""
Audit API: operation log viewing + export.
"""
import csv
import io
import json

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_dept_admin_or_above
from app.models.audit_log import AuditLog
from app.models.user import User
from app.schemas.common import AuditLogListResponse, AuditLogResponse

router = APIRouter()


@router.get("", response_model=AuditLogListResponse)  # 审计日志查询：多条件
async def list_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    action: str | None = None,
    resource_type: str | None = None,
    user_id: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    current_user: User = Depends(require_dept_admin_or_above()),
    db: AsyncSession = Depends(get_db),
):
    """
    接口说明：分页查询审计日志，支持按操作类型/资源类型/用户/时间范围过滤；部门管理员仅能查看本部门用户的日志。
    方法路径：GET /api/audit
    鉴权要求：部门管理员及以上
    请求参数：page(int,默认1), page_size(int 1-100,默认20), action(str,选填), resource_type(str,选填),
              user_id(int,选填), start_date(str,选填), end_date(str,选填)
    响应字段：AuditLogListResponse{total, items[AuditLogResponse]}
    错误码：401 未登录; 403 权限不足
    """
    query = select(AuditLog)

    # Dept admin: only see logs from same-dept users
    if current_user.role.value == "dept_admin":
        from app.models.user import User as UserModel
        dept_user_ids = await db.execute(
            select(UserModel.id).where(UserModel.dept_name == current_user.dept_name)
        )
        dept_ids = [r[0] for r in dept_user_ids.fetchall()]
        query = query.where(AuditLog.user_id.in_(dept_ids))

    if action:
        query = query.where(AuditLog.action == action)
    if resource_type:
        query = query.where(AuditLog.resource_type == resource_type)
    if user_id:
        query = query.where(AuditLog.user_id == user_id)

    count_q = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_q)
    total = total_result.scalar() or 0

    offset = (page - 1) * page_size
    result = await db.execute(
        query.order_by(AuditLog.created_at.desc()).offset(offset).limit(page_size)
    )
    logs = result.scalars().all()

    items = []
    # Batch-resolve user IDs and KB names for detail enrichment
    all_user_ids = set()
    all_kb_ids = set()
    for log in logs:
        if log.user_id:
            all_user_ids.add(log.user_id)
        if isinstance(log.detail, dict):
            if log.detail.get("target_user_id"):
                all_user_ids.add(log.detail["target_user_id"])
            if log.detail.get("kb_id"):
                all_kb_ids.add(log.detail["kb_id"])
        # resource_id holds target user_id for revoke_permission
        if log.action == "revoke_permission" and log.resource_id:
            all_user_ids.add(log.resource_id)

    user_map = {}
    if all_user_ids:
        ures = await db.execute(select(User.id, User.username).where(User.id.in_(all_user_ids)))
        user_map = {r[0]: r[1] for r in ures.fetchall()}

    kb_map = {}
    if all_kb_ids:
        from app.models.knowledge_base import KnowledgeBase
        kres = await db.execute(select(KnowledgeBase.id, KnowledgeBase.name).where(KnowledgeBase.id.in_(all_kb_ids)))
        kb_map = {r[0]: r[1] for r in kres.fetchall()}

    for log in logs:
        item = AuditLogResponse.model_validate(log)
        if log.user_id:
            item.username = user_map.get(log.user_id, "")

        # Enrich detail with resolved names
        if isinstance(log.detail, dict):
            detail = dict(log.detail)
            # For revoke_permission, resource_id holds target user_id
            if log.action == "revoke_permission" and "target_user_id" not in detail and log.resource_id:
                detail["target_user_id"] = log.resource_id
            if "target_user_id" in detail and "target_username" not in detail:
                detail["target_username"] = user_map.get(detail["target_user_id"], "")
            if "kb_id" in detail and "kb_name" not in detail:
                detail["kb_name"] = kb_map.get(detail["kb_id"], "")
            item.detail = detail

        items.append(item)

    return AuditLogListResponse(total=total, items=items)


@router.get("/export")  # 审计日志导出：CSV
async def export_audit_logs(
    action: str | None = None,
    resource_type: str | None = None,
    current_user: User = Depends(require_dept_admin_or_above()),
    db: AsyncSession = Depends(get_db),
):
    """
    接口说明：将审计日志导出为 CSV 文件（最多 10000 条），支持按操作类型/资源类型过滤；部门管理员仅导出本部门日志。
    方法路径：GET /api/audit/export
    鉴权要求：部门管理员及以上
    请求参数：action(str,选填), resource_type(str,选填)
    响应格式：text/csv 附件（Content-Disposition: attachment; filename=audit_logs.csv）
    错误码：401 未登录; 403 权限不足
    """
    query = select(AuditLog)

    # Dept admin: only export same-dept logs
    if current_user.role.value == "dept_admin":
        from app.models.user import User as UserModel
        dept_user_ids = await db.execute(
            select(UserModel.id).where(UserModel.dept_name == current_user.dept_name)
        )
        dept_ids = [r[0] for r in dept_user_ids.fetchall()]
        query = query.where(AuditLog.user_id.in_(dept_ids))

    if action:
        query = query.where(AuditLog.action == action)
    if resource_type:
        query = query.where(AuditLog.resource_type == resource_type)

    result = await db.execute(
        query.order_by(AuditLog.created_at.desc()).limit(10000)  # max export limit
    )
    logs = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "User ID", "Username", "Action", "Resource Type",
                     "Resource ID", "Detail", "IP Address", "User Agent", "Created At"])

    for log in logs:
        username = ""
        if log.user_id:
            ures = await db.execute(select(User).where(User.id == log.user_id))
            u = ures.scalar_one_or_none()
            username = u.username if u else ""

        writer.writerow([
            log.id, log.user_id or "", username, log.action, log.resource_type,
            log.resource_id or "", json.dumps(log.detail) if isinstance(log.detail, dict) else log.detail,
            log.ip_address, (log.user_agent or "")[:200], str(log.created_at),
        ])

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit_logs.csv"},
    )

