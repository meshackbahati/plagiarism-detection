import uuid
from sqlalchemy import Column, ForeignKey, String, DateTime, func, UUID
from pgvector.sqlalchemy import Vector
from .base import Base

class Embedding(Base):
    __tablename__ = "embeddings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    file_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False, index=True)
    vector = Column(Vector(384), nullable=False)
    type = Column(String, nullable=False)  # 'text' or 'image'
    created_at = Column(DateTime(timezone=True), server_default=func.now())
