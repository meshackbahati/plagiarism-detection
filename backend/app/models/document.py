import uuid
from sqlalchemy import Column, String, Text, DateTime, func, UUID, Float, Boolean, ForeignKey
from pgvector.sqlalchemy import Vector
from .base import Base

class Document(Base):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    batch_id = Column(UUID(as_uuid=True), ForeignKey("batches.id"), index=True)
    filename = Column(String, nullable=False)
    content_hash = Column(String)
    mime_type = Column(String)
    text_content = Column(Text)
    embedding = Column(Vector(384))  # Assuming sentence-transformers/all-MiniLM-L6-v2 embedding dim
    storage_path = Column(String)
    uploaded_by = Column(UUID(as_uuid=True))
    status = Column(String, default="queued", index=True)  # queued, processing, completed, failed
    ai_score = Column(Float, default=0.0)  # AI detection confidence score
    is_ai_generated = Column(Boolean, default=False)  # Is the text AI-generated?
    ai_confidence = Column(Float, default=0.0)  # AI detection confidence level
    ai_provider = Column(String)  # AI detection provider used
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
