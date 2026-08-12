"""
Chunks API: preview chunks, list by document.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.user import User
from app.schemas.common import ChunkListResponse

router = APIRouter()


@router.get("/document/{document_id}", response_model=ChunkListResponse)  # 文档分片列表
async def list_document_chunks(
    document_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    接口说明：分页获取某文档的切片文本列表（用于预览/调试），需具备所属知识库读取权限。
    方法路径：GET /api/chunks/document/{document_id}
    鉴权要求：已登录且拥有该文档所属 KB 的 read 及以上权限
    路径参数：document_id(int,必填)
    请求参数：page(int,默认1), page_size(int 1-100,默认20)
    响应字段：ChunkListResponse{total,page,page_size,chunks[{id,chunk_index,content,token_count}]}
    错误码：401 未登录; 403 无权限; 404 文档不存在
    """
    doc_result = await db.execute(
        select(Document).where(Document.id == document_id, Document.is_deleted == False)
    )
    doc = doc_result.scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "Document not found")

    # Permission check via KB
    from app.api.knowledge_bases import _check_kb_permission
    await _check_kb_permission(db, doc.kb_id, current_user)

    query = select(Chunk).where(
        Chunk.document_id == document_id,
        Chunk.is_deleted == False,
    )
    count_q = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_q)
    total = total_result.scalar() or 0

    offset = (page - 1) * page_size
    result = await db.execute(
        query.order_by(Chunk.chunk_index.asc()).offset(offset).limit(page_size)
    )
    chunk_list = result.scalars().all()

    return ChunkListResponse(
        total=total,
        page=page,
        page_size=page_size,
        chunks=[
            {
                "id": c.id,
                "chunk_index": c.chunk_index,
                "content": c.content,
                "token_count": c.token_count,
            }
            for c in chunk_list
        ],
    )


@router.get("/{chunk_id}")  # 分片详情
async def get_chunk_detail(
    chunk_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    接口说明：获取单个切片的完整详情（文本、序号、token 数、元数据、Milvus 向量 ID 等），需具备所属知识库读取权限。
    方法路径：GET /api/chunks/{chunk_id}
    鉴权要求：已登录且拥有该切片所属 KB 的 read 及以上权限
    路径参数：chunk_id(int,必填)
    响应字段：{id,document_id,kb_id,content,chunk_index,token_count,metadata,milvus_id}
    错误码：401 未登录; 403 无权限; 404 切片不存在/已删除
    """
    result = await db.execute(select(Chunk).where(Chunk.id == chunk_id))
    chunk = result.scalar_one_or_none()
    if not chunk or chunk.is_deleted:
        raise HTTPException(404, "Chunk not found")

    await _check_kb_permission(db, chunk.kb_id, current_user)

    return {
        "id": chunk.id,
        "document_id": chunk.document_id,
        "kb_id": chunk.kb_id,
        "content": chunk.content,
        "chunk_index": chunk.chunk_index,
        "token_count": chunk.token_count,
        "metadata": chunk.chunk_meta,
        "milvus_id": chunk.milvus_id,
    }
