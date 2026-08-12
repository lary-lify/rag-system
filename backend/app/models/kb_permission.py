"""
KBPermission ORM model - per-user, per-KB access control.
"""
from __future__ import annotations

from enum import Enum as PyEnum

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class PermissionLevel(str, PyEnum):
    read = "read"
    upload = "upload"
    admin = "admin"


class KBPermission(Base):
    __tablename__ = "kb_permissions"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    kb_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    permission_level: Mapped[PermissionLevel] = mapped_column(
        sa.Enum(PermissionLevel), default=PermissionLevel.read, nullable=False
    )
    created_by: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    created_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime, server_default=sa.func.now()
    )

    # Relationships
    knowledge_base = relationship("KnowledgeBase", back_populates="permissions")
    user = relationship("User")

    def __repr__(self):
        return f"<KBPerm kb={self.kb_id} user={self.user_id} level={self.permission_level}>"
