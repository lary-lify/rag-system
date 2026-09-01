"""
LoginLog ORM model - login audit trail.
"""
from __future__ import annotations

from typing import Optional

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class LoginLog(Base):
    __tablename__ = "login_logs"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        sa.Integer,
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    ip_address: Mapped[str] = mapped_column(sa.String(45), default="")
    user_agent: Mapped[str] = mapped_column(sa.String(512), default="")
    success: Mapped[bool] = mapped_column(sa.Boolean, default=1)
    fail_reason: Mapped[str] = mapped_column(sa.String(128), default="")
    created_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime, server_default=sa.func.now()
    )

    # Relationships
    user = relationship("User", back_populates="login_logs")

    def __repr__(self):
        return f"<LoginLog id={self.id} user={self.user_id} success={self.success}>"
