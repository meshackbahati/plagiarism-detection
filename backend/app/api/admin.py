from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update
from passlib.context import CryptContext

from app.api.auth import admin_user
from app.models.user import User
from app.core.db import get_db
from uuid import UUID
from typing import List

router = APIRouter(prefix="/admin", tags=["admin"])
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


class AdminCreateUserRequest(BaseModel):
    email: str
    password: str
    role: str = "user"


class AdminUpdateRoleRequest(BaseModel):
    role: str

@router.get("/users", response_model=List[dict])
async def list_users(
    current_user: User = Depends(admin_user),
    db: AsyncSession = Depends(get_db)
):
    """List all users (admin only)"""
    result = await db.execute(select(User))
    users = result.scalars().all()
    
    return [{
        "id": str(user.id),
        "email": user.email,
        "role": user.role,
        "is_active": user.is_active,
        "created_at": user.created_at
    } for user in users]


@router.post("/users", response_model=dict)
async def create_user(
    user_create: AdminCreateUserRequest,
    current_user: User = Depends(admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new user (admin only)"""
    # Check if user already exists
    result = await db.execute(select(User).filter(User.email == user_create.email))
    existing_user = result.scalar_one_or_none()
    
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email already exists"
        )
    
    # Create user using FastAPI-Users manager
    try:
        if user_create.role not in ["user", "moderator", "admin"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid role. Valid roles: user, moderator, admin"
            )

        user = User(
            email=user_create.email,
            hashed_password=pwd_context.hash(user_create.password),
            role=user_create.role,
            is_active=True,
            is_superuser=(user_create.role == "admin"),
            is_verified=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

        return {
            "id": str(user.id),
            "email": user.email,
            "role": user.role,
            "is_active": user.is_active,
            "created_at": user.created_at
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.put("/users/{user_id}", response_model=dict)
async def update_user_role(
    user_id: UUID,
    payload: AdminUpdateRoleRequest,
    current_user: User = Depends(admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Update user role (admin only)"""
    role = payload.role
    if role not in ["user", "moderator", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid role. Valid roles: user, moderator, admin"
        )
    
    # Get the user to update
    result = await db.execute(select(User).filter(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Prevent demoting oneself
    if user.id == current_user.id and role != "admin":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admin cannot change their own role"
        )
    
    # Update user role
    await db.execute(
        update(User)
        .where(User.id == user_id)
        .values(role=role, is_superuser=(role == "admin"))
    )
    await db.commit()
    
    # Refresh user data
    await db.refresh(user)
    
    return {
        "id": str(user.id),
        "email": user.email,
        "role": user.role,
        "is_active": user.is_active,
        "created_at": user.created_at
    }


@router.delete("/users/{user_id}", response_model=dict)
async def delete_user(
    user_id: UUID,
    current_user: User = Depends(admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a user (admin only) - Soft delete by deactivation"""
    result = await db.execute(select(User).filter(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Prevent deleting oneself
    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admin cannot delete themselves"
        )
    
    # Soft delete by deactivating
    await db.execute(
        update(User)
        .where(User.id == user_id)
        .values(is_active=False)
    )
    await db.commit()
    
    return {"message": f"User {user.email} deactivated successfully"}


@router.get("/stats", response_model=dict)
async def get_system_stats(
    current_user: User = Depends(admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Get system statistics (admin only)"""
    # Count total users
    result = await db.execute(select(User))
    all_users = result.scalars().all()
    
    total_users = len(all_users)
    active_users = len([u for u in all_users if u.is_active])
    admin_users = len([u for u in all_users if u.role == "admin"])
    moderator_users = len([u for u in all_users if u.role == "moderator"])
    regular_users = len([u for u in all_users if u.role == "user"])
    
    return {
        "total_users": total_users,
        "active_users": active_users,
        "inactive_users": total_users - active_users,
        "admins": admin_users,
        "moderators": moderator_users,
        "regular_users": regular_users,
        "system_access": True
    }
