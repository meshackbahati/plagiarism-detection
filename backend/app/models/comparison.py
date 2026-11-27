import uuid
from sqlalchemy import Column, String, Float, ForeignKey, DateTime, func, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSON
from .base import Base

class Comparison(Base):
    __tablename__ = "comparisons"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    doc_a = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False, index=True)
    doc_b = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False, index=True)
    similarity = Column(Float, nullable=False)  # max(lexical, semantic)
    lexical_similarity = Column(Float)  # share of doc_a copied word-for-word from doc_b
    semantic_similarity = Column(Float)  # share of doc_a paraphrased from doc_b (None without model)
    cross_batch = Column(Boolean, default=False)
    matches = Column(JSON, nullable=True) # Store detailed chunk matches
    created_at = Column(DateTime(timezone=True), server_default=func.now())
