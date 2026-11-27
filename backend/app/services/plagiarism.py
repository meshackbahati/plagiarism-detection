"""
Plagiarism detection: lexical fingerprints + semantic embeddings.

Two complementary signals:
1. Lexical (always on, no model): shared word n-grams find verbatim and
   lightly edited copying, with the exact copied passages as evidence.
2. Semantic (when the embedding model is loaded): sentence-level chunk
   embeddings catch paraphrasing that changes the words but keeps meaning.

similarity = max(lexical coverage, semantic coverage). Both are "share of
this document that matches the other one", so the number reads the same
way whichever signal produced it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

import numpy as np
from sqlalchemy import bindparam, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from app.models import Batch, Document
from app.services.embedding import EmbeddingService, TextChunk, chunk_text
from app.services.fingerprint import Fingerprint, build_fingerprint, compare_fingerprints


@dataclass
class DocProfile:
    doc_id: str
    filename: str
    fingerprint: Fingerprint
    chunks: List[TextChunk]
    matrix: Optional[np.ndarray]  # (n_chunks, dim), L2-normalised, or None
    content_hash: Optional[str] = None


class PlagiarismService:
    def __init__(self, db_session: AsyncSession = None, use_embeddings: bool = True):
        self.db_session = db_session
        self.embedding_service = EmbeddingService()
        self.use_embeddings = use_embeddings
        self._profiles: Dict[str, DocProfile] = {}

    @property
    def semantic_available(self) -> bool:
        return bool(self.use_embeddings and self.embedding_service.model)

    # ── Profiles (computed once per document per run) ──

    def profile(
        self,
        doc_id: str,
        text_content: str,
        filename: str = "",
        content_hash: Optional[str] = None,
        with_embeddings: bool = True,
    ) -> DocProfile:
        cached = self._profiles.get(doc_id)
        if cached and (cached.matrix is not None or not with_embeddings or not self.semantic_available):
            return cached
        fingerprint = cached.fingerprint if cached else build_fingerprint(text_content, settings.SHINGLE_SIZE)
        chunks = cached.chunks if cached else chunk_text(text_content)
        matrix = None
        if with_embeddings and self.semantic_available:
            matrix = self.embedding_service.embed_chunks(chunks)
        prof = DocProfile(doc_id, filename, fingerprint, chunks, matrix, content_hash)
        self._profiles[doc_id] = prof
        return prof

    def document_vector(self, prof: DocProfile) -> Optional[List[float]]:
        return EmbeddingService.document_vector(prof.matrix, prof.chunks)

    def clear_cache(self):
        self._profiles.clear()

    # ── Pairwise comparison ──

    def compare(self, a: DocProfile, b: DocProfile) -> Dict:
        """How much of document A is found in document B."""
        if a.content_hash and a.content_hash == b.content_hash and a.fingerprint.word_count:
            return {
                "similarity": 1.0,
                "lexical_similarity": 1.0,
                "semantic_similarity": 1.0 if a.matrix is not None else None,
                "matches": [{
                    "type": "exact",
                    "source_chunk": "Identical file content.",
                    "target_chunk": "Identical file content.",
                    "score": 1.0,
                    "words": a.fingerprint.word_count,
                }],
            }

        lex = compare_fingerprints(
            a.fingerprint, b.fingerprint, settings.SHINGLE_SIZE, settings.MIN_MATCH_WORDS
        )
        matches = list(lex["passages"])
        semantic_score = None

        if a.matrix is not None and b.matrix is not None and len(a.chunks) and len(b.chunks):
            sims = a.matrix @ b.matrix.T  # cosine, since rows are normalised
            best_idx = sims.argmax(axis=1)
            best = sims[np.arange(len(a.chunks)), best_idx]
            threshold = settings.SEMANTIC_MATCH_THRESHOLD
            total_words = sum(c.words for c in a.chunks) or 1
            matched_words = 0
            exact_spans = [p["source_span"] for p in lex["passages"] if "source_span" in p]
            for i, score in enumerate(best):
                if score < threshold:
                    continue
                chunk = a.chunks[i]
                matched_words += chunk.words
                # Skip chunks already shown as exact copies.
                overlap = sum(
                    max(0, min(chunk.end, e) - max(chunk.start, s)) for s, e in exact_spans
                )
                if overlap > 0.5 * (chunk.end - chunk.start):
                    continue
                target = b.chunks[int(best_idx[i])]
                matches.append({
                    "type": "semantic",
                    "source_chunk": chunk.text[:700],
                    "target_chunk": target.text[:700],
                    "score": round(float(score), 4),
                    "words": chunk.words,
                    "source_span": [chunk.start, chunk.end],
                    "target_span": [target.start, target.end],
                })
            semantic_score = round(matched_words / total_words, 4)

        similarity = max(lex["coverage"], semantic_score or 0.0)
        return {
            "similarity": round(similarity, 4),
            "lexical_similarity": lex["coverage"],
            "semantic_similarity": semantic_score,
            "matches": matches[:60],
        }

    def is_reportable(self, result: Dict) -> bool:
        return result["similarity"] >= settings.MIN_REPORTED_SIMILARITY or any(
            m["type"] == "exact" for m in result["matches"]
        )

    # ── Cross-batch candidate search ──

    async def cross_batch_candidates(
        self,
        exclude_batch_id: str,
        doc_vectors: Sequence[List[float]],
        content_hashes: Sequence[str],
        owner_id=None,
    ) -> List[Dict]:
        """
        Previously analysed documents worth comparing against this batch:
        - nearest neighbours of each new document by pgvector cosine distance
        - any document with an identical content hash
        - the most recent MAX_CROSS_BATCH_DOCS documents (lexical check only)

        Returns dicts with id, filename, batch_id, text_content, content_hash
        and `semantic` (True if picked by vector search).
        """
        if not self.db_session:
            raise ValueError("Database session required")

        found: Dict[str, Dict] = {}
        # Only search the uploader's own documents unless a shared corpus is
        # explicitly enabled (CROSS_BATCH_SCOPE=all).
        scoped = settings.CROSS_BATCH_SCOPE != "all" and owner_id is not None

        def add(row, semantic: bool):
            key = str(row.id)
            if key in found:
                found[key]["semantic"] = found[key]["semantic"] or semantic
                return
            found[key] = {
                "id": key,
                "created_at": row.created_at,
                "filename": row.filename,
                "batch_id": str(row.batch_id),
                "text_content": row.text_content or "",
                "content_hash": row.content_hash,
                "semantic": semantic,
            }

        # 1. Vector nearest neighbours. CAST(... AS vector) instead of
        #    ":param::vector": SQLAlchemy does not treat ":name::type" as a
        #    bind parameter, which broke this query before.
        if doc_vectors:
            knn = text(
                """
                SELECT d.id, d.filename, d.batch_id, d.text_content, d.content_hash, d.created_at
                FROM documents d
                JOIN batches b ON b.id = d.batch_id
                WHERE d.embedding IS NOT NULL
                  AND (:owner IS NULL OR b.user_id = :owner)
                  AND d.status = 'completed'
                  AND d.batch_id <> :exclude_batch
                ORDER BY d.embedding <=> CAST(:embedding AS vector)
                LIMIT :limit
                """
            ).bindparams(
                bindparam("exclude_batch"), bindparam("embedding"), bindparam("limit"),
                bindparam("owner", type_=PG_UUID(as_uuid=True)),
            )
            for vec in doc_vectors:
                rows = await self.db_session.execute(knn, {
                    "exclude_batch": exclude_batch_id,
                    "embedding": "[" + ",".join(f"{x:.7f}" for x in vec) + "]",
                    "limit": settings.CROSS_BATCH_CANDIDATES,
                    "owner": owner_id if scoped else None,
                })
                for row in rows:
                    add(row, True)

        cols = (Document.id, Document.filename, Document.batch_id, Document.text_content,
                Document.content_hash, Document.created_at)

        def owned(stmt):
            if scoped:
                stmt = stmt.join(Batch, Batch.id == Document.batch_id).where(Batch.user_id == owner_id)
            return stmt

        # 2. Identical files uploaded before.
        hashes = [h for h in content_hashes if h]
        if hashes:
            rows = await self.db_session.execute(
                owned(select(*cols)).where(
                    Document.content_hash.in_(hashes),
                    Document.batch_id != exclude_batch_id,
                    Document.status == "completed",
                )
            )
            for row in rows:
                add(row, False)

        # 3. Recent corpus for lexical copy checks (works without any model).
        if settings.MAX_CROSS_BATCH_DOCS > 0:
            rows = await self.db_session.execute(
                owned(select(*cols))
                .where(Document.batch_id != exclude_batch_id, Document.status == "completed")
                .order_by(Document.created_at.desc())
                .limit(settings.MAX_CROSS_BATCH_DOCS)
            )
            for row in rows:
                add(row, False)

        # The same file uploaded in several earlier batches would show up as
        # many identical matches. Keep only its first upload (the original).
        by_hash: Dict[str, Dict] = {}
        result: List[Dict] = []
        for cand in sorted(found.values(), key=lambda c: (c["created_at"] is None, c["created_at"])):
            h = cand["content_hash"]
            if h and h in by_hash:
                by_hash[h]["semantic"] = by_hash[h]["semantic"] or cand["semantic"]
                continue
            if h:
                by_hash[h] = cand
            result.append(cand)
        return result
