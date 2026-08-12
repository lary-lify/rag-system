"""
KnowledgeBase ORM model - private / shared mode, soft delete.
"""
from __future__ import annotations

from enum import Enum as PyEnum

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class KBMode(str, PyEnum):
    private = "private"
    shared = "shared"


class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    description: Mapped[str] = mapped_column(sa.Text, default="")
    owner_id: Mapped[int] = mapped_column(
        sa.Integer, sa.ForeignKey("users.id"), nullable=False
    )

    mode: Mapped[KBMode] = mapped_column(
        sa.Enum(KBMode), default=KBMode.private, nullable=False
    )
    embedding_model: Mapped[str] = mapped_column(sa.String(64), default="text-embedding-v3")
    embedding_dimensions: Mapped[int] = mapped_column(sa.Integer, default=1536)
    doc_count: Mapped[int] = mapped_column(sa.Integer, default=0)
    chunk_count: Mapped[int] = mapped_column(sa.Integer, default=0)

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
    owner = relationship("User", back_populates="knowledge_bases")
    documents = relationship("Document", back_populates="knowledge_base")
    chunks = relationship("Chunk", back_populates="knowledge_base")
    permissions = relationship("KBPermission", back_populates="knowledge_base")

    def __repr__(self):
        return f"<KB id={self.id} name={self.name} mode={self.mode}>"
