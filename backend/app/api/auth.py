from typing import AsyncGenerator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi_users import FastAPIUsers
from fastapi_users.authentication import AuthenticationBackend, BearerTransport, JWTStrategy
from fastapi_users.db import SQLAlchemyUserDatabase
from fastapi_users.manager import BaseUserManager, UUIDIDMixin
from fastapi_users.password import PasswordHelper
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_db
from app.models.user import User
from app.schemas import UserCreate, UserRead


bearer_transport = BearerTransport(tokenUrl="auth/jwt/login")


def get_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(secret=settings.SECRET_KEY, lifetime_seconds=3600)


auth_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)


class UserManager(UUIDIDMixin, BaseUserManager[User, UUID]):
    reset_password_token_secret = settings.SECRET_KEY
    verification_token_secret = settings.SECRET_KEY

    async def on_after_register(self, user: User, request=None) -> None:
        # Intentionally no sensitive token logging.
        return None

    async def on_after_forgot_password(self, user: User, token: str, request=None) -> None:
        # Hook present for future integration with an email provider.
        return None

    async def on_after_request_verify(self, user: User, token: str, request=None) -> None:
        # Hook present for future integration with an email provider.
        return None


async def get_user_db(session: AsyncSession = Depends(get_db)) -> AsyncGenerator[SQLAlchemyUserDatabase, None]:
    yield SQLAlchemyUserDatabase(session, User)


password_helper = PasswordHelper(CryptContext(schemes=["argon2"], deprecated="auto"))


async def get_user_manager(user_db: SQLAlchemyUserDatabase = Depends(get_user_db)) -> AsyncGenerator[UserManager, None]:
    yield UserManager(user_db, password_helper=password_helper)


fastapi_users = FastAPIUsers[User, UUID](get_user_manager, [auth_backend])
current_user = fastapi_users.current_user(active=True)


async def admin_user(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Admin privileges required.",
        )
    return user


async def mod_or_admin_user(user: User = Depends(current_user)) -> User:
    if user.role not in ["admin", "moderator"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Admin or moderator privileges required.",
        )
    return user


router = APIRouter()
router.include_router(
    fastapi_users.get_auth_router(auth_backend),
    prefix="/jwt",
    tags=["auth"],
)
router.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    prefix="",
    tags=["auth"],
)
router.include_router(
    fastapi_users.get_reset_password_router(),
    tags=["auth"],
)
