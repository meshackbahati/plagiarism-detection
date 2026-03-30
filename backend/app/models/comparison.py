import uuid
from sqlalchemy import Column, String, Float, ForeignKey, DateTime, Integer
from sqlalchemy.dialects.postgresql import UUID, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from .base import Base

class Comparison(Base):
    __tablename__ = "comparisons"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    doc_a = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False)
    doc_b = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False)
    similarity = Column(Float, nullable=False)
    matches = Column(JSON, nullable=True) # Store detailed chunk matches
    created_at = Column(DateTime, default=datetime.utcnow)
