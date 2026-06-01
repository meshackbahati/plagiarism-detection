import uuid
from sqlalchemy import Column, Float, ForeignKey, String, DateTime, func, UUID
from .base import Base

class Result(Base):
    __tablename__ = "results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    file_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False, index=True)
    matched_file_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False, index=True)
    score = Column(Float, nullable=False)
    type = Column(String, nullable=False)  # 'text_similarity', 'image_similarity', 'ai_detection'
    created_at = Column(DateTime(timezone=True), server_default=func.now())
