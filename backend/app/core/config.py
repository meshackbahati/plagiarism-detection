from pydantic_settings import BaseSettings
from typing import Optional
import os


class Settings(BaseSettings):
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql+asyncpg://user:password@db:5432/plagiarism_db")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-insecure-secret-change-me")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # Storage settings
    STORAGE_TYPE: str = os.getenv("STORAGE_TYPE", "local")  # s3 or local
    S3_ENDPOINT_URL: Optional[str] = os.getenv("S3_ENDPOINT_URL")
    S3_ACCESS_KEY: Optional[str] = os.getenv("S3_ACCESS_KEY")
    S3_SECRET_KEY: Optional[str] = os.getenv("S3_SECRET_KEY")
    S3_BUCKET_NAME: str = os.getenv("S3_BUCKET_NAME", "plagiarism-uploads")
    
    # AI Detection settings
    USE_EXTERNAL_AI_DETECTION: bool = os.getenv("USE_EXTERNAL_AI_DETECTION", "false").lower() == "true"
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
    TOGETHER_API_KEY: Optional[str] = os.getenv("TOGETHER_API_KEY")

    # Resource management
    LIGHTWEIGHT_MODE: bool = os.getenv("LIGHTWEIGHT_MODE", "false").lower() == "true"
    MODEL_UNLOAD_TIMEOUT: int = int(os.getenv("MODEL_UNLOAD_TIMEOUT", "300"))  # seconds idle before unloading
    MAX_CROSS_BATCH_DOCS: int = int(os.getenv("MAX_CROSS_BATCH_DOCS", "500"))  # max docs for cross-batch search
    
    # Celery settings
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://redis:6379/0")
    CELERY_BROKER_URL: str = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
    CELERY_RESULT_BACKEND: str = os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/0")


settings = Settings()

if settings.ENVIRONMENT.lower() == "production" and settings.SECRET_KEY in {
    "dev-insecure-secret-change-me",
    "your-super-secret-key-change-in-production",
}:
    raise ValueError("SECRET_KEY must be set to a strong unique value in production.")
