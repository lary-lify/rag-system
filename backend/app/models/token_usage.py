"""
TokenUsage ORM model - multi-dimensional billing records.
"""
from __future__ import annotations

from enum import Enum as PyEnum

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TokenType(str, PyEnum):
    embedding = "embedding"
    chat = "chat"
    chunking = "chunking"  # AI-assisted chunking LLM calls


class TokenUsage(Base):
    __tablename__ = "token_usage"

    id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True, autoincrement=True)
    type: Mapped[TokenType] = mapped_column(
        sa.Enum(TokenType), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        sa.Integer,
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    kb_id: Mapped[int | None] = mapped_column(
        sa.Integer,
        sa.ForeignKey("knowledge_bases.id", ondelete="SET NULL"),
        nullable=True,
    )
    document_id: Mapped[int | None] = mapped_column(
        sa.Integer,
        sa.ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    conversation_id: Mapped[int | None] = mapped_column(
        sa.Integer,
        sa.ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
    )
    message_id: Mapped[int | None] = mapped_column(
        sa.Integer, nullable=True  # no FK to messages - avoid cascade loops
    )

    input_tokens: Mapped[int] = mapped_column(sa.Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(sa.Integer, default=0)
    estimated_cost: Mapped[float] = mapped_column(
        sa.Numeric(12, 6), default=0.000000
    )

    created_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime, server_default=sa.func.now()
    )

    def __repr__(self):
        return f"<TokUsage id={self.id} type={self.type} cost={self.estimated_cost}>"
