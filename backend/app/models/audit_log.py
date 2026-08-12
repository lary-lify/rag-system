"""
AuditLog ORM model - full operation audit trail.
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        sa.Integer,
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,  # NULL for system actions
    )
    action: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    resource_id: Mapped[int | None] = mapped_column(
        sa.Integer, nullable=True
    )
    detail: Mapped[dict] = mapped_column(sa.JSON, default=dict)
    ip_address: Mapped[str] = mapped_column(sa.String(45), default="")
    user_agent: Mapped[str] = mapped_column(sa.String(512), default="")
    created_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime, server_default=sa.func.now()
    )

    # Relationships
    user = relationship("User", back_populates="audit_logs")

    def __repr__(self):
        return f"<AuditLog id={self.id} action={self.action} type={self.resource_type}>"
