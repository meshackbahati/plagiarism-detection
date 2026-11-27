import asyncio
import os
import sys
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from app.core.config import settings
from app.models import User
from passlib.context import CryptContext

# Password hashing context
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

async def get_async_session():
    """Create async database session"""
    engine = create_async_engine(settings.DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session

async def get_user_by_email(session: AsyncSession, email: str) -> User:
    """Get user by email"""
    result = await session.execute(select(User).filter(User.email == email))
    return result.scalar_one_or_none()

async def create_user(
    session: AsyncSession,
    email: str,
    password: str,
    role: str = "user",
    is_active: bool = True,
    is_verified: bool = False,
    is_superuser: bool = False,
) -> User:
    """Create a new user"""
    hashed_password = pwd_context.hash(password)
    user = User(
        email=email,
        hashed_password=hashed_password,
        role=role,
        is_active=is_active,
        is_verified=is_verified,
        is_superuser=is_superuser,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user

async def seed_database():
    """Seed the database with initial admin and sample users"""
    print("Seeding database...")
    
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        
        # Create extension, tables and any newly added columns
        from app.core.schema import ensure_schema
        await ensure_schema(engine)
        
        # Create session
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        
        async with async_session() as session:
            # Create admin user if not exists
            admin_email = os.getenv("ADMIN_EMAIL", "admin@example.com")
            admin_password = os.getenv("ADMIN_PASSWORD", "AdminPass123!")
            
            existing_admin = await get_user_by_email(session, admin_email)
            if not existing_admin:
                admin_user = await create_user(
                    session,
                    admin_email,
                    admin_password,
                    "admin",
                    is_active=True,
                    is_verified=True,
                    is_superuser=True,
                )
                print(f"Created admin user: {admin_user.email}")
            else:
                print(f"Admin user already exists: {existing_admin.email}")
            
            # Optional sample users for local demos only.
            create_sample_users = os.getenv("CREATE_SAMPLE_USERS", "false").lower() == "true"
            if create_sample_users:
                sample_users = [
                    {"email": "user1@example.com", "password": "UserPass123!", "role": "user"},
                    {"email": "user2@example.com", "password": "UserPass123!", "role": "user"},
                    {"email": "moderator@example.com", "password": "ModPass123!", "role": "moderator"},
                ]

                for user_data in sample_users:
                    existing_user = await get_user_by_email(session, user_data["email"])
                    if not existing_user:
                        user = await create_user(
                            session,
                            user_data["email"],
                            user_data["password"],
                            user_data["role"],
                            is_active=True,
                            is_verified=True,
                        )
                        print(f"Created user: {user.email} with role: {user.role}")
                    else:
                        print(f"User already exists: {existing_user.email}")
            
            await session.commit()  # Ensure all transactions are committed
            print("Database seeding completed!")
            
    except Exception as e:
        # A broken schema means every upload will fail, so stop start-up
        # loudly instead of serving a half-working API.
        print(f"Error during database seeding: {str(e)}")
        raise
    finally:
        await engine.dispose()

def main():
    """Main function to run the seeding script"""
    try:
        asyncio.run(seed_database())
    except Exception:
        sys.exit(1)

if __name__ == "__main__":
    main()
