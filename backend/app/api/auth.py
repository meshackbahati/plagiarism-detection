from typing import AsyncGenerator
from uuid import UUID
import os

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from passlib.context import CryptContext

from app.core.db import get_db
from app.models.user import User

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

async def get_current_user(db: AsyncSession = Depends(get_db)) -> User:
    """
    Bypass authentication for local tool use.
    Always returns the admin user. If no user exists, it creates one.
    """
    admin_email = os.getenv("ADMIN_EMAIL", "admin@example.com")
    result = await db.execute(select(User).where(User.email == admin_email))
    user = result.scalar_one_or_none()

    if not user:
        # Check if any user exists at all
        result = await db.execute(select(User).limit(1))
        user = result.scalar_one_or_none()

    if not user:
        # Create a default admin user if none exists (Auto-bootstrap)
        admin_password = os.getenv("ADMIN_PASSWORD", "AdminPass123!")
        user = User(
            email=admin_email,
            hashed_password=pwd_context.hash(admin_password),
            role="admin",
            is_active=True,
            is_superuser=True,
            is_verified=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    return user

# Mock the fastapi_users.current_user() behavior
def current_user(*args, **kwargs):
    return get_current_user

async def admin_user(user: User = Depends(get_current_user)) -> User:
    # In a local tool, everyone is an admin
    return user

async def mod_or_admin_user(user: User = Depends(get_current_user)) -> User:
    # In a local tool, everyone is a moderator/admin
    return user

# Router for backward compatibility
router = APIRouter()
