import uuid
from sqlalchemy import Column, String, Integer, DateTime, func, UUID, ForeignKey, Float
from .base import Base

class Batch(Base):
    __tablename__ = "batches"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    name = Column(String)
    total_docs = Column(Integer)
    processed_docs = Column(Integer, default=0)
    status = Column(String)
    analysis_type = Column(String, default="plagiarism")  # plagiarism, ai, or both
    ai_provider = Column(String, default="local")  # AI detection provider
    ai_threshold = Column(Float, default=0.5)  # AI detection threshold
    created_at = Column(DateTime(timezone=True), server_default=func.now())
