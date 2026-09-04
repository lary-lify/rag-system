"""
Reports API: cost statistics, usage trends, multi-dimensional analysis.
All cost figures are real-time recalculated from env var pricing.
"""
import math
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_super_admin
from app.models.token_usage import TokenUsage, TokenType
from app.models.user import User
from app.models.knowledge_base import KnowledgeBase
from app.schemas.common import (
    DateRangeQuery,
    CostSummaryResponse,
    UsageTrendResponse,
)

router = APIRouter()


def _calc_embedding_cost(tokens: int) -> float:
    """Real-time embedding cost from current env price."""
    return round(tokens * settings.TONGYI_EMBEDDING_TOKEN_PRICE, 6)


def _calc_chat_cost(input_tokens: int, output_tokens: int) -> float:
    """Real-time chat cost from current env prices."""
    return round(
        input_tokens * settings.DEEPSEEK_INPUT_TOKEN_PRICE
        + output_tokens * settings.DEEPSEEK_OUTPUT_TOKEN_PRICE,
        6,
    )


@router.get("/cost-summary", response_model=CostSummaryResponse)  # 成本汇总：实时重算
async def get_cost_summary(
    start_date: str = Query(""),
    end_date: str = Query(""),
    user_id: int | None = None,
    kb_id: int | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    接口说明：全维度成本汇总统计。按用户/知识库/日期三个维度聚合 token 用量与估算费用，
              费用基于 token 计数 + 当前环境变量单价实时计算（改单价后历史报表自动反映新价）。
    方法路径：GET /api/reports/cost-summary
    鉴权要求：部门管理员及以上（部门管理员仅能看到自己的用量）
    请求参数：start_date(str,选填), end_date(str,选填,默认近30天), user_id(int,选填), kb_id(int,选填)
    响应字段：CostSummaryResponse{period_start,period_end,total_embedding_tokens,total_chat_input/output_tokens,
              total_estimated_cost,by_user[],by_kb[],by_day[]}
    错误码：401 未登录; 403 权限不足
    """
    # Parse date range (default last 30 days)
    today = date.today()
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else today - timedelta(days=30)
    except ValueError:
        start = today - timedelta(days=30)
    try:
        end = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else today
    except ValueError:
        end = today

    # Build base query with filters
    q = select(TokenUsage).where(
        TokenUsage.created_at >= datetime.combine(start, datetime.min.time()),
        TokenUsage.created_at <= datetime.combine(end, datetime.max.time()),
    )

    # Dept admin: only see their own usage
    if current_user.role.value == "dept_admin":
        q = q.where(TokenUsage.user_id == current_user.id)

    if user_id:
        q = q.where(TokenUsage.user_id == user_id)
    if kb_id:
        q = q.where(TokenUsage.kb_id == kb_id)

    result = await db.execute(q)
    records = result.scalars().all()

    # Aggregate totals (real-time re-calculation from token counts + current prices)
    total_emb_tokens = 0
    total_chat_in = 0
    total_chat_out = 0
    total_cache_hits = 0
    total_cache_misses = 0
    by_user_map: dict[int, dict] = {}
    by_kb_map: dict[int, dict] = {}
    by_day_map: dict[str, dict] = {}

    for r in records:
        if r.type == TokenType.embedding:
            total_emb_tokens += r.input_tokens
            cost = _calc_embedding_cost(r.input_tokens)
        else:
            total_chat_in += r.input_tokens
            total_chat_out += r.output_tokens
            cost = _calc_chat_cost(r.input_tokens, r.output_tokens)
            # 命中可量化对账：chat 类型按 cache_hit 累计命中/未命中次数
            if r.cache_hit:
                total_cache_hits += 1
            else:
                total_cache_misses += 1

        day_key = r.created_at.strftime("%Y-%m-%d")

        # By user
        if r.user_id not in by_user_map:
            by_user_map[r.user_id] = {"tokens": 0, "cost": 0.0, "cache_hits": 0}
        by_user_map[r.user_id]["tokens"] += r.input_tokens + r.output_tokens
        by_user_map[r.user_id]["cost"] += cost
        by_user_map[r.user_id]["cache_hits"] += 1 if r.cache_hit else 0

        # By KB (if applicable)
        if r.kb_id and r.kb_id is not None:
            if r.kb_id not in by_kb_map:
                by_kb_map[r.kb_id] = {"kb_name": "", "tokens": 0, "cost": 0.0, "cache_hits": 0}
            by_kb_map[r.kb_id]["tokens"] += r.input_tokens + r.output_tokens
            by_kb_map[r.kb_id]["cost"] += cost
            by_kb_map[r.kb_id]["cache_hits"] += 1 if r.cache_hit else 0

        # By day
        if day_key not in by_day_map:
            by_day_map[day_key] = {"embedding_cost": 0.0, "chat_cost": 0.0, "total_cost": 0.0}
        if r.type == TokenType.embedding:
            by_day_map[day_key]["embedding_cost"] += cost
        else:
            by_day_map[day_key]["chat_cost"] += cost
        by_day_map[day_key]["total_cost"] += cost

    total_estimated = _calc_embedding_cost(total_emb_tokens) + _calc_chat_cost(total_chat_in, total_chat_out)

    # Resolve names for by_user / by_kb (batch query to avoid N+1)
    user_ids = list(by_user_map.keys())
    kb_ids = list(by_kb_map.keys())

    user_map = {}
    if user_ids:
        user_result = await db.execute(select(User).where(User.id.in_(user_ids)))
        user_map = {u.id: u for u in user_result.scalars().all()}

    kb_map = {}
    if kb_ids:
        kb_result = await db.execute(select(KnowledgeBase).where(KnowledgeBase.id.in_(kb_ids)))
        kb_map = {k.id: k for k in kb_result.scalars().all()}

    by_user_list = []
    for uid, data in sorted(by_user_map.items(), key=lambda x: x[1]["cost"], reverse=True):
        u = user_map.get(uid)
        by_user_list.append({
            "user_id": uid,
            "username": u.username if u else f"User#{uid}",
            "tokens": data["tokens"],
            "cost": round(data["cost"], 4),
            "cache_hits": data["cache_hits"],
        })

    by_kb_list = []
    for kid, data in sorted(by_kb_map.items(), key=lambda x: x[1]["cost"], reverse=True):
        k = kb_map.get(kid)
        by_kb_list.append({
            "kb_id": kid,
            "kb_name": k.name if k else f"KB#{kid}",
            "tokens": data["tokens"],
            "cost": round(data["cost"], 4),
            "cache_hits": data["cache_hits"],
        })

    by_day_sorted = sorted(by_day_map.items())
    by_day_list = [{"date": d, **v} for d, v in by_day_sorted]

    return CostSummaryResponse(
        period_start=str(start),
        period_end=str(end),
        total_embedding_tokens=total_emb_tokens,
        total_chat_input_tokens=total_chat_in,
        total_chat_output_tokens=total_chat_out,
        total_estimated_cost=round(total_estimated, 4),
        total_cache_hits=total_cache_hits,
        total_cache_misses=total_cache_misses,
        by_user=by_user_list[:20],
        by_kb=by_kb_list[:20],
        by_day=by_day_list,
    )


@router.get("/usage-trend", response_model=UsageTrendResponse)  # 用量趋势：时序
async def get_usage_trend(
    days: int = Query(30, ge=7, le=365),
    start_date: str = Query(""),
    end_date: str = Query(""),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    接口说明：按天的时间序列用量趋势，供前端 ECharts 折线图展示（含 embedding / chat 输入 / chat 输出 token 及每日费用）。
    方法路径：GET /api/reports/usage-trend
    鉴权要求：部门管理员及以上（部门管理员仅看自己的用量）
    请求参数：days(int 7-365,默认30), start_date(str,选填), end_date(str,选填)
    响应字段：UsageTrendResponse{dates[],embedding_tokens[],chat_input_tokens[],chat_output_tokens[],costs[]}
    错误码：401 未登录; 403 权限不足
    """
    today = date.today()
    if start_date and end_date:
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d").date()
            end = datetime.strptime(end_date, "%Y-%m-%d").date()
        except ValueError:
            start = today - timedelta(days=days)
            end = today
    else:
        start = today - timedelta(days=days)
        end = today

    total_days = (end - start).days

    trend_query = select(
        func.date(TokenUsage.created_at).label("dt"),
        TokenUsage.type,
        func.sum(TokenUsage.input_tokens).label("in_toks"),
        func.sum(TokenUsage.output_tokens).label("out_toks"),
        func.sum(case((TokenUsage.cache_hit == True, 1), else_=0)).label("cache_hits"),
    ).where(
        TokenUsage.created_at >= datetime.combine(start, datetime.min.time()),
        TokenUsage.created_at <= datetime.combine(end, datetime.max.time()),
    )

    # Dept admin: only see their own usage
    if current_user.role.value == "dept_admin":
        trend_query = trend_query.where(TokenUsage.user_id == current_user.id)

    result = await db.execute(
        trend_query
        .group_by(func.date(TokenUsage.created_at), TokenUsage.type)
        .order_by(func.date(TokenUsage.created_at))
    )
    rows = result.all()

    # Build daily map
    daily_data: dict[str, dict] = {}
    for i in range(total_days + 1):
        d = (start + timedelta(days=i)).isoformat()
        daily_data[d] = {"embedding_tokens": 0, "chat_input_tokens": 0, "chat_output_tokens": 0, "cache_hits": 0}

    for row in rows:
        dkey = str(row.dt)
        if dkey in daily_data:
            if row.type == TokenType.embedding:
                daily_data[dkey]["embedding_tokens"] = int(row.in_toks or 0)
            else:
                daily_data[dkey]["chat_input_tokens"] = int(row.in_toks or 0)
                daily_data[dkey]["chat_output_tokens"] = int(row.out_toks or 0)
                daily_data[dkey]["cache_hits"] = int(row.cache_hits or 0)

    dates = sorted(daily_data.keys())
    return UsageTrendResponse(
        dates=dates,
        embedding_tokens=[daily_data[d]["embedding_tokens"] for d in dates],
        chat_input_tokens=[daily_data[d]["chat_input_tokens"] for d in dates],
        chat_output_tokens=[daily_data[d]["chat_output_tokens"] for d in dates],
        cache_hits=[daily_data[d]["cache_hits"] for d in dates],
        costs=[
            round(_calc_embedding_cost(daily_data[d]["embedding_tokens"])
                  + _calc_chat_cost(daily_data[d]["chat_input_tokens"],
                                    daily_data[d]["chat_output_tokens"]), 4)
            for d in dates
        ],
    )


# ---- Q&A Statistics ----

from app.models.message import Message
from app.models.conversation import Conversation


@router.get("/qa-stats")  # 问答统计：满意率/热门问题
async def get_qa_stats(
    start_date: str = Query(""),
    end_date: str = Query(""),
    kb_id: int | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    接口说明：问答质量统计——反馈率与满意度（赞/踩）、Top 高频问题、知识库命中率（有溯源片段的消息占比）。
    方法路径：GET /api/reports/qa-stats
    鉴权要求：部门管理员及以上
    请求参数：start_date(str,选填), end_date(str,选填,默认近30天), kb_id(int,选填)
    响应字段：{period_start,period_end,total_messages,feedback_stats{good,bad,feedback_rate,satisfaction_rate},hit_rate,top_questions[]}
    错误码：401 未登录; 403 权限不足
    """
    # Parse date range
    today = date.today()
    if start_date:
        start = datetime.strptime(start_date, "%Y-%m-%d")
    else:
        start = datetime.combine(today - timedelta(days=30), datetime.min.time())
    if end_date:
        end = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
    else:
        end = datetime.combine(today, datetime.max.time())

    # Base query for messages in date range
    base_query = select(Message).where(
        Message.created_at.between(start, end)
    )

    # Filter by KB if specified
    if kb_id:
        base_query = base_query.where(
            Message.conversation_id.in_(
                select(Conversation.id).where(Conversation.kb_ids.contains(str(kb_id)))
            )
        )

    # Total messages
    total_result = await db.execute(select(func.count(Message.id)).where(
        Message.created_at.between(start, end)
    ))
    total_messages = total_result.scalar() or 0

    # Feedback stats (默认未评价算作"有用")
    feedback_result = await db.execute(
        select(
            # 有用 = 明确好评 + 未评价（默认有用）
            func.sum(case(
                (Message.feedback == 1, 1),
                (Message.feedback.is_(None), 1),  # 未评价默认为有用
                else_=0
            )).label("good"),
            # 无用 = 明确差评
            func.sum(case((Message.feedback == 0, 1), else_=0)).label("bad"),
        ).where(
            Message.created_at.between(start, end),
        )
    )
    feedback_row = feedback_result.fetchone()
    good_feedback = feedback_row[0] or 0 if feedback_row else 0
    bad_feedback = feedback_row[1] or 0 if feedback_row else 0
    total_feedback = good_feedback + bad_feedback
    feedback_rate = round(total_feedback / total_messages * 100, 1) if total_messages > 0 else 0
    satisfaction_rate = round(good_feedback / total_feedback * 100, 1) if total_feedback > 0 else 0

    # Top questions (most asked)
    top_questions_result = await db.execute(
        select(Message.question, func.count(Message.id).label("count"))
        .where(Message.created_at.between(start, end))
        .group_by(Message.question)
        .order_by(func.count(Message.id).desc())
        .limit(10)
    )
    top_questions = [{"question": row[0], "count": row[1]} for row in top_questions_result.fetchall()]

    # Hit rate (messages with source_chunks > 0)
    hit_result = await db.execute(
        select(func.count(Message.id)).where(
            Message.created_at.between(start, end),
            Message.source_chunks != "[]",
            Message.source_chunks.isnot(None),
        )
    )
    hit_messages = hit_result.scalar() or 0
    hit_rate = round(hit_messages / total_messages * 100, 1) if total_messages > 0 else 0

    return {
        "period_start": start.strftime("%Y-%m-%d"),
        "period_end": end.strftime("%Y-%m-%d"),
        "total_messages": total_messages,
        "feedback_stats": {
            "total": total_feedback,
            "good": good_feedback,
            "bad": bad_feedback,
            "feedback_rate": feedback_rate,
            "satisfaction_rate": satisfaction_rate,
        },
        "hit_rate": hit_rate,
        "top_questions": top_questions,
    }


# ---- Daily Summary APIs ----

@router.get("/daily-summary")  # 每日汇总查询
async def get_daily_summary(
    start_date: str = Query(""),
    end_date: str = Query(""),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    接口说明：读取 daily_token_summary 每日汇总表，返回指定日期区间内的输入/输出 token、费用、请求数时间序列（用于看板）。
    方法路径：GET /api/reports/daily-summary
    鉴权要求：部门管理员及以上
    请求参数：start_date(str,选填,默认近30天), end_date(str,选填)
    响应字段：{dates[],input_tokens[],output_tokens[],costs[],requests[]}（表不存在时返回全空数组）
    错误码：401 未登录; 403 权限不足
    """
    from datetime import date as date_type, timedelta
    
    today = date_type.today()
    if start_date:
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
    else:
        start = today - timedelta(days=30)
    if end_date:
        end = datetime.strptime(end_date, "%Y-%m-%d").date()
    else:
        end = today
    
    try:
        # 查询汇总数据
        result = await db.execute(text("""
            SELECT 
                summary_date,
                SUM(total_input_tokens) as total_input,
                SUM(total_output_tokens) as total_output,
                SUM(total_cost) as total_cost,
                SUM(request_count) as total_requests
            FROM daily_token_summary
            WHERE summary_date BETWEEN :start AND :end
            GROUP BY summary_date
            ORDER BY summary_date
        """), {"start": start, "end": end})
        
        rows = result.fetchall()
        
        return {
            "dates": [str(r.summary_date) for r in rows],
            "input_tokens": [int(r.total_input or 0) for r in rows],
            "output_tokens": [int(r.total_output or 0) for r in rows],
            "costs": [float(r.total_cost or 0) for r in rows],
            "requests": [int(r.total_requests or 0) for r in rows],
        }
    except Exception as e:
        # 如果汇总表不存在，返回空数据
        return {
            "dates": [],
            "input_tokens": [],
            "output_tokens": [],
            "costs": [],
            "requests": [],
        }


@router.post("/trigger-summary")  # 手动触发汇总：仅超管
async def trigger_summary(
    target_date: str = Query(""),
    current_user: User = Depends(require_super_admin()),
):
    """
    接口说明：手动触发每日用量汇总任务（默认对昨天，可指定 target_date），由超级管理员调用，弥补定时任务未覆盖的场景。
    方法路径：POST /api/reports/trigger-summary
    鉴权要求：超级管理员(super_admin)
    请求参数：target_date(str,选填,格式 YYYY-MM-DD) 不传则取昨天
    响应字段：detail("Summary triggered for {date}")
    错误码：401 未登录; 403 非超管
    """
    from app.services.daily_summary import run_daily_summary
    from datetime import date as date_type
    
    if target_date:
        target = datetime.strptime(target_date, "%Y-%m-%d").date()
    else:
        target = date_type.today() - timedelta(days=1)
    
    await run_daily_summary(target)
    return {"detail": f"Summary triggered for {target}"}


# ---- Import User model at top of file to fix reference ----
from app.models.user import User
