"""
Chunk ORM model - text chunks with full-text index, Milvus ID reference.
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        sa.Integer,
        sa.ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    kb_id: Mapped[int] = mapped_column(
        sa.Integer,
        sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(sa.Text, nullable=False)
    chunk_index: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    token_count: Mapped[int] = mapped_column(sa.Integer, default=0)
    chunk_meta: Mapped[dict] = mapped_column("metadata", sa.JSON, default=dict)
    milvus_id: Mapped[int | None] = mapped_column(
        sa.BigInteger, unique=True, nullable=True
    )

    is_deleted: Mapped[bool] = mapped_column(sa.Boolean, default=0)
    created_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime, server_default=sa.func.now()
    )

    # Relationships
    document = relationship("Document", back_populates="chunks")
    knowledge_base = relationship("KnowledgeBase", back_populates="chunks")

    def __repr__(self):
        return f"<Chunk id={self.id} doc={self.document_id} idx={self.chunk_index}>"
