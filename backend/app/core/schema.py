"""
Idempotent schema setup, run at API start-up (see database_seed.py).

The project has no Alembic migrations yet, and Base.metadata.create_all()
never adds columns to tables that already exist. This module creates the
pgvector extension, creates missing tables, then adds any columns added
since a database was first created, so old installs upgrade in place.
"""

from sqlalchemy import text

from app.models import Base

# (table, column, SQL type) added after the first release.
ADDED_COLUMNS = [
    ("batches", "error", "TEXT"),
    ("documents", "ai_label", "VARCHAR"),
    ("documents", "error", "TEXT"),
    ("documents", "word_count", "INTEGER"),
    ("documents", "extraction_method", "VARCHAR"),
    ("comparisons", "lexical_similarity", "DOUBLE PRECISION"),
    ("comparisons", "semantic_similarity", "DOUBLE PRECISION"),
    ("comparisons", "cross_batch", "BOOLEAN DEFAULT FALSE"),
]

INDEXES = [
    "CREATE INDEX IF NOT EXISTS ix_documents_content_hash ON documents (content_hash)",
    "CREATE INDEX IF NOT EXISTS ix_documents_created_at ON documents (created_at)",
    "CREATE INDEX IF NOT EXISTS ix_batches_created_at ON batches (created_at)",
]


async def ensure_schema(engine) -> None:
    async with engine.begin() as conn:
        # Must exist before create_all: documents.embedding is a vector column.
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
        for table, column, sql_type in ADDED_COLUMNS:
            await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {sql_type}"))
        for stmt in INDEXES:
            await conn.execute(text(stmt))
