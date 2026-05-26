from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from app.api.auth import get_current_user
from app.models.user import User
from app.schemas import UserRead
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_db


router = APIRouter()


@router.get("/me", response_model=UserRead)
async def get_current_user_info(user: User = Depends(get_current_user)):
    """Get current authenticated user"""
    return user


@router.get("/{user_id}", response_model=UserRead)
async def get_user_by_id(
    user_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get user by ID (admin or self only)"""
    # Check if current user is admin or requesting own profile
    if current_user.id != user_id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Fetch the actual user from database
    from sqlalchemy import select
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return user

@router.get("/me/dashboard")
async def get_user_dashboard(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get dashboard statistics for current user"""
    from app.models import Batch, Document
    from sqlalchemy import select, func
    
    # Count user's batches
    batch_count = await db.scalar(
        select(func.count(Batch.id)).where(Batch.user_id == current_user.id)
    )
    
    # Count user's documents
    doc_count = await db.scalar(
        select(func.count(Document.id))
        .join(Batch, Document.batch_id == Batch.id)
        .where(Batch.user_id == current_user.id)
    )
    
    return {
        "data": {
            "num_batches": batch_count or 0,
            "num_documents": doc_count or 0
        }
    }


# Include authentication routes from fastapi_users
# These would typically be registered separately, but for now we'll define the router
# The actual auth routes (login, register, etc.) are handled by fastapi_users
