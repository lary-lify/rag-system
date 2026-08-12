"""
Conversations API + SSE streaming chat endpoint.
"""
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.audit_log import AuditLog
from app.models.user import User
from app.models.conversation import Conversation
from app.schemas.common import (
    ConversationCreate,
    ConversationUpdate,
    ConversationInfoResponse,
    ConversationListResponse,
    ChatRequest,
    MessageHistoryItem,
    FeedbackRequest,
)
from app.services.llm_service import stream_chat_response

router = APIRouter()

# Import limiter from core
from app.core.limiter import limiter


# ---- Conversation CRUD ----

@router.post("", status_code=201)  # 创建会话
async def create_conversation(
    body: ConversationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    接口说明：创建新对话，记录标题与关联的知识库ID列表(kb_ids)。
    方法路径：POST /api/conversations
    鉴权要求：已登录任意角色用户（对话归属当前用户）
    请求参数：body.title(str,选填), body.kb_ids(list[int],选填)
    响应字段：{id}
    错误码：401 未登录
    """
    conv = Conversation(
        user_id=current_user.id,
        title=body.title or "New Chat",
        kb_ids=body.kb_ids,
    )
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    return {"id": conv.id}


@router.get("", response_model=ConversationListResponse)  # 会话列表
async def list_conversations(
    page: int = 1,
    page_size: int = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    接口说明：分页查询当前用户自己的对话列表（按更新时间倒序）。
    方法路径：GET /api/conversations
    鉴权要求：已登录任意角色用户（仅返回本人对话）
    请求参数：page(int,默认1), page_size(int,默认20)
    响应字段：ConversationListResponse{total, items[ConversationInfoResponse]}
    错误码：401 未登录
    """
    query = select(Conversation).where(
        Conversation.user_id == current_user.id,
        Conversation.is_deleted == False,
    )
    count_q = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_q)
    total = total_result.scalar() or 0

    offset = (page - 1) * page_size
    result = await db.execute(
        query.order_by(Conversation.updated_at.desc()).offset(offset).limit(page_size)
    )
    convs = result.scalars().all()

    return ConversationListResponse(
        total=total,
        items=[ConversationInfoResponse.model_validate(c) for c in convs],
    )


@router.get("/{conv_id}", response_model=ConversationInfoResponse)  # 会话详情
async def get_conversation(
    conv_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    接口说明：获取单个对话的详细信息（仅限创建者本人）。
    方法路径：GET /api/conversations/{conv_id}
    鉴权要求：已登录且为对话创建者
    路径参数：conv_id(int,必填)
    响应字段：ConversationInfoResponse{id,title,kb_ids,message_count,created_at,updated_at}
    错误码：401 未登录; 404 对话不存在/无权限
    """
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conv_id,
            Conversation.user_id == current_user.id,
            Conversation.is_deleted == False,
        )
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(404, "Conversation not found")
    return ConversationInfoResponse.model_validate(conv)


@router.put("/{conv_id}")  # 更新会话：重命名
async def update_conversation(
    conv_id: int,
    body: ConversationUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    接口说明：更新对话信息（如标题、关联知识库列表），仅限创建者本人。
    方法路径：PUT /api/conversations/{conv_id}
    鉴权要求：已登录且为对话创建者
    路径参数：conv_id(int,必填)
    请求参数：body(ConversationUpdate,选填字段) title/kb_ids
    响应字段：detail("Updated")
    错误码：401 未登录; 404 对话不存在/无权限
    """
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conv_id,
            Conversation.user_id == current_user.id,
        )
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(404, "Conversation not found")

    update_data = body.model_dump(exclude_unset=True)
    for k, v in update_data.items():
        setattr(conv, k, v)
    await db.commit()
    return {"detail": "Updated"}


@router.delete("/{conv_id}")  # 删除会话：软删
async def delete_conversation(
    conv_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    接口说明：软删除对话（置 is_deleted=True），并写入审计日志，仅限创建者本人。
    方法路径：DELETE /api/conversations/{conv_id}
    鉴权要求：已登录且为对话创建者
    路径参数：conv_id(int,必填)
    响应字段：detail("Deleted")
    错误码：401 未登录; 404 对话不存在/无权限
    """
    ip = request.client.host if request.client else ""
    ua = request.headers.get("user-agent", "")

    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conv_id,
            Conversation.user_id == current_user.id,
        )
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(404, "Conversation not found")

    conv.is_deleted = True
    audit = AuditLog(
        user_id=current_user.id,
        action="delete",
        resource_type="conversation",
        resource_id=conv_id,
        detail={"title": conv.title},
        ip_address=ip,
        user_agent=ua,
    )
    db.add(audit)
    await db.commit()
    return {"detail": "Deleted"}


# ---- Message History ----

@router.get("/{conv_id}/messages", response_model=list[MessageHistoryItem])  # 会话消息历史
async def get_messages(
    conv_id: int,
    page: int = 1,
    page_size: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    接口说明：分页获取某对话的消息历史（按时间正序），需为对话创建者本人。
    方法路径：GET /api/conversations/{conv_id}/messages
    鉴权要求：已登录且为对话创建者
    路径参数：conv_id(int,必填)
    请求参数：page(int,默认1), page_size(int,默认50)
    响应字段：list[MessageHistoryItem]{id,conversation_id,question,answer,source_chunks,input_tokens,output_tokens,feedback,...}
    错误码：401 未登录; 404 对话不存在/无权限
    """
    # Verify ownership
    await get_conversation(conv_id, current_user, db)

    from app.models.message import Message
    query = select(Message).where(Message.conversation_id == conv_id)
    offset = (page - 1) * page_size
    result = await db.execute(
        query.order_by(Message.created_at.asc()).offset(offset).limit(page_size)
    )
    msgs = result.scalars().all()

    return [MessageHistoryItem.model_validate(m) for m in msgs]


@router.post("/{conv_id}/messages/{msg_id}/feedback")  # 消息反馈：点赞/点踩
async def set_message_feedback(
    conv_id: int,
    msg_id: int,
    body: FeedbackRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    接口说明：对一条问答消息标记赞/踩反馈（满意度统计用），需为该对话创建者本人。
    方法路径：POST /api/conversations/{conv_id}/messages/{msg_id}/feedback
    鉴权要求：已登录且为对话创建者
    路径参数：conv_id(int,必填), msg_id(int,必填)
    请求参数：body.feedback(int,必填) 1=赞 / 0=踩
    响应字段：detail("Feedback recorded"), feedback
    错误码：401 未登录; 404 消息不存在/无权限
    """
    import logging
    logger = logging.getLogger(__name__)

    from app.models.message import Message
    from datetime import datetime, timezone

    logger.info(f"[feedback] conv_id={conv_id}, msg_id={msg_id}, feedback={body.feedback}")

    result = await db.execute(
        select(Message).where(
            Message.id == msg_id,
            Message.conversation_id == conv_id,
            Message.user_id == current_user.id,
        )
    )
    msg = result.scalar_one_or_none()
    if not msg:
        raise HTTPException(404, "Message not found")

    msg.feedback = body.feedback
    msg.feedback_time = datetime.now(timezone.utc)
    await db.commit()

    logger.info(f"[feedback] Success: msg_id={msg_id}, feedback={body.feedback}")
    return {"detail": "Feedback recorded", "feedback": msg.feedback}


# ---- SSE Streaming Chat (Core Feature) ----

@router.post("/chat")  # SSE流式问答：查询改写→向量检索→LLM流式
@limiter.limit("30/minute")  # 限制每分钟最多30次聊天请求
async def chat_sse(
    body: ChatRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    接口说明：核心 SSE 流式问答接口。流程为「查询改写(LLM) → 向量检索 Milvus → 召回切片 → 拼接上下文+多轮记忆 → DeepSeek 流式生成 → 前端打字机渲染 → 计费采集」。
    方法路径：POST /api/conversations/chat
    鉴权要求：已登录任意角色用户
    请求参数：body.conversation_id(int,选填) 不传则自动新建; body.question(str,必填); body.kb_ids(list[int],选填)
    响应格式：Server-Sent Events 流，事件依次为：
      - data: {"type":"conversation_id","value":N}
      - data: {"type":"chunk","content":"..."}        # 逐 token 流式回答
      - data: {"type":"source_chunks","chunks":[...]} # 溯源片段
      - data: {"type":"done","message_id":N,"input_tokens":N,"output_tokens":N,"total_tokens":N}
      - event: done  (结束信号，前端用于停止打字机)
    错误码：401 未登录; 404 对话不存在; 429 对话频率超限(30/min)
    备注：前端使用 EventSource/流式读取渲染；支持中途停止生成。
    """
    ip = request.client.host if request.client else ""
    ua = request.headers.get("user-agent", "")

    # Resolve or create conversation
    conv_id = body.conversation_id
    kb_ids = body.kb_ids

    if conv_id:
        conv_result = await db.execute(
            select(Conversation).where(
                Conversation.id == conv_id,
                Conversation.user_id == current_user.id,
                Conversation.is_deleted == False,
            )
        )
        conv = conv_result.scalar_one_or_none()
        if not conv:
            raise HTTPException(404, "Conversation not found")
        # Override KB IDs if provided in this request
        if kb_ids:
            conv.kb_ids = kb_ids
    else:
        conv = Conversation(
            user_id=current_user.id,
            title=body.question[:50] + ("..." if len(body.question) > 50 else ""),
            kb_ids=kb_ids,
        )
        db.add(conv)
        await db.commit()
        await db.refresh(conv)

    async def _event_generator():
        import logging
        logger = logging.getLogger(__name__)

        full_answer = ""
        input_tokens = 0
        output_tokens = 0
        source_chunks_data = []

        # Create fresh db session (the endpoint's db session is closed when StreamingResponse starts)
        from app.core.database import AsyncSessionLocal
        async with AsyncSessionLocal() as sse_db:
            try:
                # Send conversation ID first
                yield f"data: {json.dumps({'type': 'conversation_id', 'value': conv.id})}\n\n"

                # Stream LLM response via DeepSeek
                async for chunk_data in stream_chat_response(
                    question=body.question,
                    user_id=current_user.id,
                    conversation_id=conv.id,
                    kb_ids=conv.kb_ids,
                    db=sse_db,
                ):
                    chunk_type = chunk_data["type"]

                    if chunk_type == "token":
                        token_text = chunk_data["content"]
                        full_answer += token_text
                        yield f"data: {json.dumps({'type': 'chunk', 'content': token_text})}\n\n"

                    elif chunk_type == "source":
                        source_chunks_data = chunk_data.get("chunks", [])
                        yield f"data: {json.dumps({'type': 'source_chunks', 'chunks': source_chunks_data})}\n\n"

                    elif chunk_type == "usage":
                        input_tokens = chunk_data.get("input_tokens", 0)
                        output_tokens = chunk_data.get("output_tokens", 0)

            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'detail': str(e)})}\n\n"
                return

            # Save message record to DB
            total_tokens = input_tokens + output_tokens
            from app.models.message import Message
            msg = Message(
                conversation_id=conv.id,
                user_id=current_user.id,
                question=body.question,
                answer=full_answer,
                source_chunks=source_chunks_data,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
            sse_db.add(msg)
            conv.message_count += 1
            await sse_db.commit()

            # Record token usage for billing
            try:
                from app.models.token_usage import TokenUsage, TokenType
                from app.core.config import settings

                # Calculate cost
                chat_cost = round(
                    input_tokens * settings.DEEPSEEK_INPUT_TOKEN_PRICE +
                    output_tokens * settings.DEEPSEEK_OUTPUT_TOKEN_PRICE,
                    6
                )

                tok_record = TokenUsage(
                    type=TokenType.chat,
                    user_id=current_user.id,
                    conversation_id=conv.id,
                    message_id=msg.id,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    estimated_cost=chat_cost,
                )
                sse_db.add(tok_record)
                await sse_db.commit()
                logger.info(f"[billing] Chat tokens recorded: {input_tokens} in + {output_tokens} out, cost=¥{chat_cost}")
            except Exception as e:
                logger.warning(f"[billing] Failed to record token usage: {e}")

        # Final done signal with complete stats
        yield f"data: {json.dumps({'type': 'done', 'message_id': msg.id, 'input_tokens': input_tokens, 'output_tokens': output_tokens, 'total_tokens': total_tokens})}\n\n"
        yield "event: done\ndata: finished\n\n"

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
