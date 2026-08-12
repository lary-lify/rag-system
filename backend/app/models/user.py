"""
User ORM model - accounts with 3 roles: super_admin / dept_admin / user
"""
from __future__ import annotations

from enum import Enum as PyEnum

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class UserRole(str, PyEnum):
    super_admin = "super_admin"
    dept_admin = "dept_admin"
    user = "user"


class UserStatus(str, PyEnum):
    active = "active"
    disabled = "disabled"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(sa.String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    real_name: Mapped[str] = mapped_column(sa.String(64), default="")
    email: Mapped[str] = mapped_column(sa.String(128), default="")
    phone: Mapped[str] = mapped_column(sa.String(32), default="")
    dept_name: Mapped[str] = mapped_column(sa.String(128), default="")

    role: Mapped[UserRole] = mapped_column(
        sa.Enum(UserRole), default=UserRole.user, nullable=False
    )
    status: Mapped[UserStatus] = mapped_column(
        sa.Enum(UserStatus), default=UserStatus.active, nullable=False
    )
    created_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime, server_default=sa.func.now()
    )

    # Runtime-only attributes (set by dependency)
    _request_ip: str = ""
    _request_ua: str = ""

    # Relationships (lazy-loaded)
    knowledge_bases = relationship("KnowledgeBase", back_populates="owner")
    documents = relationship("Document", back_populates="uploader")
    conversations = relationship("Conversation", back_populates="user")
    login_logs = relationship("LoginLog", back_populates="user")
    audit_logs = relationship("AuditLog", back_populates="user")

    def __repr__(self):
        return f"<User id={self.id} username={self.username} role={self.role}>"
