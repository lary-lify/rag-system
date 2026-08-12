"""
Conversation ORM model - chat sessions with soft delete.
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        sa.Integer,
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(sa.String(200), default="")
    kb_ids: Mapped[list[int]] = mapped_column(sa.JSON, default=list)
    message_count: Mapped[int] = mapped_column(sa.Integer, default=0)

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
    user = relationship("User", back_populates="conversations")
    messages = relationship(
        "Message", back_populates="conversation", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Conv id={self.id} user={self.user_id} title={self.title}>"
