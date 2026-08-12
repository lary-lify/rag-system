"""
Document ORM model - uploaded file metadata with soft delete.
"""
from __future__ import annotations

from enum import Enum as PyEnum

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class DocumentStatus(str, PyEnum):
    pending = "pending"
    parsing = "parsing"
    embedding = "embedding"
    completed = "completed"
    failed = "failed"


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    kb_id: Mapped[int] = mapped_column(
        sa.Integer,
        sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
    )
    filename: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    file_size: Mapped[int] = mapped_column(sa.BigInteger, default=0)
    file_type: Mapped[str] = mapped_column(sa.String(16), nullable=False)

    uploader_id: Mapped[int] = mapped_column(
        sa.Integer,
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_strategy: Mapped[str] = mapped_column(sa.String(32), default="fixed_token")
    chunk_params: Mapped[dict] = mapped_column(sa.JSON, default=dict)
    chunk_count: Mapped[int] = mapped_column(sa.Integer, default=0)

    status: Mapped[DocumentStatus] = mapped_column(
        sa.Enum(DocumentStatus), default=DocumentStatus.pending, nullable=False
    )
    error_msg: Mapped[str] = mapped_column(sa.Text, default="")

    is_deleted: Mapped[bool] = mapped_column(sa.Boolean, default=0)
    deleted_at: Mapped[sa.DateTime | None] = mapped_column(sa.DateTime, nullable=True)
    created_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime, server_default=sa.func.now()
    )
    updated_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )

    # Relationships
    knowledge_base = relationship("KnowledgeBase", back_populates="documents")
    uploader = relationship("User", back_populates="documents")
    chunks = relationship("Chunk", back_populates="document")

    def __repr__(self):
        return f"<Doc id={self.id} file={self.original_filename} status={self.status}>"
