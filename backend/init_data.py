"""
Initial data seeding - creates super admin on first startup.
Run: python init_data.py
Also auto-called from app.main lifespan if user not exists.
"""
from __future__ import annotations

import asyncio
import sys

# Ensure project root is in path
sys.path.insert(0, ".")

from app.core.config import settings
from app.core.database import engine, Base, AsyncSessionLocal
from app.core.security import hash_password
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select


async def create_super_admin(db: AsyncSession | None = None):
    """Create the initial super_admin account from env vars."""
    close_after = False
    if db is None:
        db = AsyncSessionLocal()
        close_after = True

    try:
        # Check if any super_admin already exists
        from app.models.user import User, UserRole

        result = await db.execute(
            select(User).where(User.role == UserRole.super_admin)
        )
        existing = result.scalar_one_or_none()

        if existing:
            print(f"[init] Super admin already exists: {existing.username} (id={existing.id})")
            return existing

        # Validate password is configured
        if not settings.INIT_ADMIN_PASSWORD:
            raise ValueError(
                "INIT_ADMIN_PASSWORD is not set. Please configure it in your .env file.\n"
                "Example: INIT_ADMIN_PASSWORD=your-secure-password-here"
            )

        # Create new super admin
        admin = User(
            username=settings.INIT_ADMIN_USERNAME,
            password_hash=hash_password(settings.INIT_ADMIN_PASSWORD),
            real_name=settings.INIT_ADMIN_REAL_NAME,
            email=settings.INIT_ADMIN_EMAIL,
            role=UserRole.super_admin,
            status="active",
        )
        db.add(admin)
        await db.commit()
        await db.refresh(admin)
        print(f"[init] Super admin created: username={admin.username}")
        return admin
    finally:
        if close_after:
            await db.close()


async def main():
    """Entry point for standalone execution."""
    print(f"[init] Connecting to: {settings.mysql_url_sync}")
    await create_super_admin()
    print("[init] Done.")


if __name__ == "__main__":
    asyncio.run(main())
