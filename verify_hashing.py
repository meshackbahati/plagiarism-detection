from passlib.context import CryptContext
import asyncio

async def test_hashing():
    pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")
    password = "ChangeThisAdminPassword123!"
    hashed = pwd_context.hash(password)
    print(f"Hashed: {hashed}")

    # Verify
    is_valid = pwd_context.verify(password, hashed)
    print(f"Verification successful: {is_valid}")

    # Test with bcrypt to see if it handles legacy (it shouldn't if we only set argon2)
    # but the CryptContext is what we use in seeder and auth now.

if __name__ == "__main__":
    asyncio.run(test_hashing())
