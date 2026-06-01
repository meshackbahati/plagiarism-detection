from typing import List, Dict, Any, Optional, Tuple
import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

from app.models import Document
from app.services.embedding import EmbeddingService
from app.core.config import settings


class PlagiarismService:
    """
    Plagiarism detection using semantic embeddings.

    Key optimization: chunk embeddings are computed once per document and
    cached in a dict, then reused for all pairwise comparisons within a batch.
    This eliminates the O(N*M) re-encoding that previously happened when each
    document was compared against every other document.
    """

    def __init__(self, db_session: AsyncSession = None):
        self.db_session = db_session
        self.embedding_service = EmbeddingService()

        # Cache: doc_id -> (chunks, embeddings)
        # Populated during batch processing, avoids re-encoding on every comparison
        self._embedding_cache: Dict[str, Tuple[List[str], list]] = {}

    def calculate_similarity(self, embedding_a, embedding_b) -> float:
        """Calculate cosine similarity between two embeddings."""
        if embedding_a is None or embedding_b is None:
            return 0.0

        vec_a = np.array(embedding_a, dtype=np.float32)
        vec_b = np.array(embedding_b, dtype=np.float32)

        norm_a = np.linalg.norm(vec_a)
        norm_b = np.linalg.norm(vec_b)

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return float(np.dot(vec_a, vec_b) / (norm_a * norm_b))

    def precompute_embeddings(self, doc_id: str, text_content: str) -> Tuple[List[str], list]:
        """
        Pre-compute and cache chunk embeddings for a document.
        Call this once per document before running comparisons.
        Returns (chunks, embeddings).
        """
        if doc_id in self._embedding_cache:
            return self._embedding_cache[doc_id]

        chunks, embeddings = self.embedding_service.encode_chunks(text_content)
        self._embedding_cache[doc_id] = (chunks, embeddings)
        return chunks, embeddings

    def compare_cached(
        self,
        doc_a_id: str,
        doc_b_id: str,
    ) -> Dict[str, Any]:
        """
        Compare two documents using pre-cached chunk embeddings.
        Both documents must have been precomputed via precompute_embeddings().
        """
        cache_a = self._embedding_cache.get(doc_a_id)
        cache_b = self._embedding_cache.get(doc_b_id)

        if not cache_a or not cache_b:
            return {"score": 0.0, "matches": []}

        chunks_a, embeddings_a = cache_a
        chunks_b, embeddings_b = cache_b

        if not embeddings_a or not embeddings_b:
            return {"score": 0.0, "matches": []}

        # Batch-encode doc_b embeddings into a matrix for vectorized comparison
        matrix_b = np.array(embeddings_b, dtype=np.float32)  # (M, dim)
        norms_b = np.linalg.norm(matrix_b, axis=1, keepdims=True)
        norms_b = np.where(norms_b == 0, 1, norms_b)  # avoid div-by-zero
        normed_b = matrix_b / norms_b

        matches = []
        total_similarity = 0.0

        for i, emb_a in enumerate(embeddings_a):
            vec_a = np.array(emb_a, dtype=np.float32)
            norm_a = np.linalg.norm(vec_a)
            if norm_a == 0:
                continue
            normed_a = vec_a / norm_a

            # Cosine similarity of chunk_a against ALL chunks in B at once
            similarities = normed_b @ normed_a  # (M,)
            best_idx = int(np.argmax(similarities))
            best_score = float(similarities[best_idx])

            if best_score > 0.75:
                matches.append({
                    "source_chunk": chunks_a[i],
                    "target_chunk": chunks_b[best_idx],
                    "score": round(best_score, 4),
                    "source_index": i,
                    "target_index": best_idx,
                })
                total_similarity += best_score

        overall_score = total_similarity / len(chunks_a) if chunks_a else 0.0

        return {
            "score": round(overall_score, 4),
            "matches": matches,
            "details": {
                "chunks_a": len(chunks_a),
                "chunks_b": len(chunks_b),
            },
        }

    def clear_cache(self):
        """Clear the embedding cache to free memory after batch processing."""
        self._embedding_cache.clear()

    async def find_similar_in_batch(self, document: Document, batch_id: str) -> List[Dict[str, Any]]:
        """
        Find similar documents within the same batch using cached embeddings.
        """
        if not self.db_session:
            raise ValueError("Database session required for batch search")

        query = select(Document).where(
            Document.batch_id == batch_id,
            Document.id != document.id,
        )
        result = await self.db_session.execute(query)
        other_docs = result.scalars().all()

        doc_a_id = str(document.id)
        results = []

        for other_doc in other_docs:
            doc_b_id = str(other_doc.id)
            comparison = self.compare_cached(doc_a_id, doc_b_id)

            if comparison["score"] > 0.1:
                results.append({
                    "document_id": doc_b_id,
                    "filename": other_doc.filename,
                    "similarity": comparison["score"],
                    "matches": comparison["matches"],
                })

        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results

    async def find_similar_across_batches(
        self,
        document: Document,
        exclude_batch_id: Optional[str] = None,
        top_k: int = 10,
        min_similarity: float = 0.3,
    ) -> List[Dict[str, Any]]:
        """
        Find similar documents across ALL batches using pgvector similarity search.
        This enables cross-batch plagiarism detection.

        Uses the document-level embedding stored on Document.embedding and
        pgvector's cosine distance operator for fast nearest-neighbor search.
        """
        if not self.db_session:
            raise ValueError("Database session required")

        if not document.embedding:
            return []

        max_docs = settings.MAX_CROSS_BATCH_DOCS

        # Use pgvector's cosine distance operator (<=>) for efficient search
        query = text("""
            SELECT
                d.id,
                d.filename,
                d.batch_id,
                1 - (d.embedding <=> :embedding::vector) AS similarity
            FROM documents d
            WHERE d.id != :doc_id
              AND d.embedding IS NOT NULL
              AND d.status = 'completed'
              AND (:exclude_batch IS NULL OR d.batch_id != :exclude_batch)
            ORDER BY d.embedding <=> :embedding::vector
            LIMIT :limit
        """)

        result = await self.db_session.execute(query, {
            "doc_id": document.id,
            "embedding": document.embedding,
            "exclude_batch": exclude_batch_id,
            "limit": max_docs,
        })

        rows = result.all()
        results = []
        for row in rows:
            sim = float(row.similarity)
            if sim >= min_similarity:
                results.append({
                    "document_id": str(row.id),
                    "filename": row.filename,
                    "batch_id": str(row.batch_id),
                    "similarity": round(sim, 4),
                    "cross_batch": True,
                })

        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results[:top_k]
