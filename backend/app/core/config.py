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

    # Upload / extraction limits
    MAX_UPLOAD_BYTES: int = int(os.getenv("MAX_UPLOAD_BYTES", str(200 * 1024 * 1024)))
    MAX_FILES_PER_BATCH: int = int(os.getenv("MAX_FILES_PER_BATCH", "500"))
    MAX_PDF_PAGES: int = int(os.getenv("MAX_PDF_PAGES", "1000"))
    MAX_OCR_PAGES: int = int(os.getenv("MAX_OCR_PAGES", "100"))
    ARCHIVE_MAX_FILES: int = int(os.getenv("ARCHIVE_MAX_FILES", "500"))
    ARCHIVE_MAX_FILE_BYTES: int = int(os.getenv("ARCHIVE_MAX_FILE_BYTES", str(50 * 1024 * 1024)))
    ARCHIVE_MAX_TOTAL_BYTES: int = int(os.getenv("ARCHIVE_MAX_TOTAL_BYTES", str(500 * 1024 * 1024)))

    # Plagiarism tuning
    SHINGLE_SIZE: int = int(os.getenv("SHINGLE_SIZE", "5"))  # words per fingerprint shingle
    MIN_MATCH_WORDS: int = int(os.getenv("MIN_MATCH_WORDS", "8"))  # shortest copied passage reported
    SEMANTIC_MATCH_THRESHOLD: float = float(os.getenv("SEMANTIC_MATCH_THRESHOLD", "0.82"))
    MIN_REPORTED_SIMILARITY: float = float(os.getenv("MIN_REPORTED_SIMILARITY", "0.05"))
    # "user": compare only against the same account's earlier uploads.
    # "all": shared corpus (e.g. a whole school); other accounts' file names
    # and text are redacted in results and reports.
    CROSS_BATCH_SCOPE: str = os.getenv("CROSS_BATCH_SCOPE", "user").lower()
    CROSS_BATCH_CANDIDATES: int = int(os.getenv("CROSS_BATCH_CANDIDATES", "20"))
    
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
