"""
Pydantic schemas - request/response models for all APIs.
"""
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.models.user import UserRole, UserStatus
from app.models.kb_permission import PermissionLevel


# ---- Auth ----
class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1)

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
    user_info: dict  # id, username, real_name, role

class RefreshTokenRequest(BaseModel):
    access_token: str

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=6)


# ---- Users ----
class UserCreate(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=6)
    real_name: str = ""
    email: str = ""
    phone: str = ""
    dept_name: str = ""
    role: UserRole = UserRole.user

class UserUpdate(BaseModel):
    real_name: str | None = None
    email: str | None = None
    phone: str | None = None
    dept_name: str | None = None
    status: UserStatus | None = None

class UserInfoResponse(BaseModel):
    id: int
    username: str
    real_name: str
    email: str
    phone: str
    dept_name: str
    role: UserRole
    status: UserStatus
    created_at: datetime

    class Config:
        from_attributes = True

class UserListResponse(BaseModel):
    total: int
    items: list[UserInfoResponse]


# ---- Knowledge Bases ----
class KBCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: str = ""
    mode: str = "private"  # private / shared
    embedding_model: str = "text-embedding-v3"

class KBUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    mode: str | None = None
    embedding_model: str | None = None

class KBPermissionGrant(BaseModel):
    user_id: int | None = None
    username: str | None = None
    permission_level: PermissionLevel = PermissionLevel.read

class KBInfoResponse(BaseModel):
    id: int
    name: str
    description: str
    owner_id: int
    owner_name: str = ""  # populated from query
    mode: str
    embedding_model: str
    embedding_dimensions: int
    doc_count: int
    chunk_count: int
    is_deleted: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class KBListResponse(BaseModel):
    total: int
    items: list[KBInfoResponse]

class PermissionInfoResponse(BaseModel):
    id: int
    kb_id: int
    user_id: int
    username: str = ""
    real_name: str = ""
    permission_level: str
    created_at: datetime

    class Config:
        from_attributes = True


# ---- Documents ----
class ChunkPreviewRequest(BaseModel):
    file_content: bytes  # raw file bytes - sent as base64 in practice
    chunk_strategy: str = "fixed_token"
    chunk_params: dict = {}

class DocumentUploadMeta(BaseModel):
    kb_id: int
    chunk_strategy: str = "fixed_token"
    chunk_params: dict = {}  # {chunk_size, overlap, separators, ...}

class DocumentInfoResponse(BaseModel):
    id: int
    kb_id: int
    filename: str
    original_filename: str
    file_size: int
    file_type: str
    uploader_id: int
    uploader_name: str = ""
    chunk_strategy: str
    chunk_params: dict
    chunk_count: int
    status: str
    error_msg: str
    is_deleted: bool
    created_at: datetime

    class Config:
        from_attributes = True

class DocumentListResponse(BaseModel):
    total: int
    items: list[DocumentInfoResponse]


# ---- Chunks ----
class ChunkPreviewResult(BaseModel):
    total_chunks: int
    chunks: list[dict]  # [{index, content, token_count}]

class ChunkListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    chunks: list[dict]  # simplified for preview


# ---- Conversations / Chat ----
class ConversationCreate(BaseModel):
    title: str = ""
    kb_ids: list[int] = []

class ConversationUpdate(BaseModel):
    title: str | None = None

class ConversationInfoResponse(BaseModel):
    id: int
    user_id: int
    title: str
    kb_ids: list[int]
    message_count: int
    is_deleted: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class ConversationListResponse(BaseModel):
    total: int
    items: list[ConversationInfoResponse]

class ChatRequest(BaseModel):
    conversation_id: int | None = None  # null = create new session
    question: str = Field(..., min_length=1)
    kb_ids: list[int] = []  # override session's kb_ids if provided

class ChatMessageResponse(BaseModel):
    conversation_id: int
    message_id: int
    answer: str
    source_chunks: list[dict]
    input_tokens: int
    output_tokens: int
    total_tokens: int

class MessageHistoryItem(BaseModel):
    id: int
    question: str
    answer: str
    source_chunks: list[dict]
    input_tokens: int
    output_tokens: int
    feedback: int | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class FeedbackRequest(BaseModel):
    feedback: int = Field(..., ge=0, le=1)  # 1=good, 0=bad


# ---- Reports ----
class DateRangeQuery(BaseModel):
    start_date: str = ""  # YYYY-MM-DD
    end_date: str = ""    # YYYY-MM-DD

class CostSummaryResponse(BaseModel):
    period_start: str
    period_end: str
    total_embedding_tokens: int
    total_chat_input_tokens: int
    total_chat_output_tokens: int
    total_estimated_cost: float
    by_user: list[dict]   # [{user_id, username, tokens, cost}]
    by_kb: list[dict]     # [{kb_id, kb_name, tokens, cost}]
    by_day: list[dict]    # [{date, embedding_cost, chat_cost, total_cost}]

class UsageTrendResponse(BaseModel):
    dates: list[str]
    embedding_tokens: list[int]
    chat_input_tokens: list[int]
    chat_output_tokens: list[int]
    costs: list[float]


# ---- Audit ----
class AuditLogResponse(BaseModel):
    id: int
    user_id: int | None
    username: str = ""
    action: str
    resource_type: str
    resource_id: int | None
    detail: dict
    ip_address: str
    user_agent: str
    created_at: datetime

    class Config:
        from_attributes = True

class AuditLogListResponse(BaseModel):
    total: int
    items: list[AuditLogResponse]


# ---- Config (read-only view) ----
class ConfigViewResponse(BaseModel):
    config_items: list[dict]  # [{key, value, description}]
