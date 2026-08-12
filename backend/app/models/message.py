"""
Message ORM model - Q&A message records with token counts.
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        sa.Integer,
        sa.ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        sa.Integer,
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    question: Mapped[str] = mapped_column(sa.Text, nullable=False)
    answer: Mapped[str] = mapped_column(sa.Text, default="")
    source_chunks: Mapped[list[dict]] = mapped_column(sa.JSON, default=list)

    input_tokens: Mapped[int] = mapped_column(sa.Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(sa.Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(
        sa.Integer, default=0
    )  # generated as input + output

    # Feedback fields
    feedback: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)  # 1=good, 0=bad
    feedback_time: Mapped[sa.DateTime | None] = mapped_column(sa.DateTime, nullable=True)

    created_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime, server_default=sa.func.now()
    )

    # Relationships
    conversation = relationship("Conversation", back_populates="messages")
    user = relationship("User")

    def __repr__(self):
        return f"<Msg id={self.id} conv={self.conversation_id} tokens_in={self.input_tokens}>"
