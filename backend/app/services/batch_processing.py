"""
Celery task that analyses one uploaded batch.

Pipeline:
  1. Profile every readable document once (fingerprint + chunk embeddings)
     and store a document vector for future cross-batch searches.
  2. Fetch cross-batch candidates once for the whole batch.
  3. Per document: AI detection, within-batch comparison, cross-batch
     comparison, then commit, so progress is visible and one bad document
     never loses the others' results.

Re-running a batch is safe: old comparisons/AI rows for its documents are
deleted first.
"""

import asyncio
import logging
from typing import Dict, List

from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.core.celery import app as celery_app
from app.core.config import settings
from app.models.ai_detection import AIDetection
from app.models.batch import Batch
from app.models.comparison import Comparison
from app.models.document import Document

logger = logging.getLogger(__name__)


@celery_app.task(name="app.services.batch_processing.process_batch", bind=True)
def process_batch(self, batch_id: str, provider: str = "local", ai_threshold: float = 0.5):
    """Process a batch of documents for plagiarism and/or AI detection."""
    try:
        asyncio.run(_process_batch_async(batch_id, provider, ai_threshold))
    except Exception as exc:
        logger.exception("Batch %s crashed", batch_id)
        asyncio.run(_mark_batch_failed(batch_id, f"Processing crashed: {exc}"))
        raise


def _new_engine():
    # A fresh engine per task with NullPool: every task runs in its own
    # asyncio.run() event loop, and pooled asyncpg connections from a
    # previous loop cannot be reused (they fail with "attached to a
    # different loop" on the second task in the same worker process).
    return create_async_engine(settings.DATABASE_URL, poolclass=NullPool)


async def _mark_batch_failed(batch_id: str, message: str):
    engine = _new_engine()
    try:
        async with AsyncSession(engine) as session:
            await session.execute(
                update(Batch).where(Batch.id == batch_id).values(status="failed", error=message[:2000])
            )
            await session.execute(
                update(Document)
                .where(Document.batch_id == batch_id, Document.status.in_(["queued", "processing"]))
                .values(status="failed", error="Batch processing stopped before this document finished.")
            )
            await session.commit()
    finally:
        await engine.dispose()


async def _process_batch_async(batch_id: str, provider: str, ai_threshold: float):
    engine = _new_engine()
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with Session() as session:
            await _run(session, batch_id, provider, ai_threshold)
    finally:
        await engine.dispose()


async def _run(session: AsyncSession, batch_id: str, provider: str, ai_threshold: float):
    batch = await session.get(Batch, batch_id)
    if not batch:
        logger.warning("Batch %s not found", batch_id)
        return

    analysis_type = batch.analysis_type or "plagiarism"
    owner_id = batch.user_id
    do_ai = analysis_type in ("ai", "both", "mixed")
    do_plagiarism = analysis_type in ("plagiarism", "both", "mixed")

    rows = (await session.execute(select(Document).where(Document.batch_id == batch_id))).scalars().all()
    # Plain snapshots: ORM objects expire on rollback, and lazy reloads are
    # not allowed in async sessions.
    docs: List[Dict] = [
        {
            "id": d.id,
            "filename": d.filename,
            "text": d.text_content or "",
            "content_hash": d.content_hash,
            "status": d.status,
        }
        for d in rows
    ]
    doc_ids = [d["id"] for d in docs]

    # Idempotent re-runs.
    if doc_ids:
        await session.execute(
            delete(Comparison).where(or_(Comparison.doc_a.in_(doc_ids), Comparison.doc_b.in_(doc_ids)))
        )
        await session.execute(delete(AIDetection).where(AIDetection.document_id.in_(doc_ids)))
    await session.execute(
        update(Batch).where(Batch.id == batch_id).values(status="processing", processed_docs=0, error=None)
    )
    await session.commit()

    # Documents that already failed at upload (unreadable file) stay failed.
    pre_failed = [d for d in docs if d["status"] == "failed"]
    work = [d for d in docs if d["status"] != "failed"]
    for d in list(work):
        if not d["text"].strip():
            await _fail_doc(session, d["id"], "No readable text was found in this file.")
            pre_failed.append(d)
            work.remove(d)

    processed = len(pre_failed)
    failed = len(pre_failed)
    await _set_progress(session, batch_id, processed)

    # ── Phase 1: profiles + document vectors ──
    plagiarism = None
    profiles = {}
    candidates = []
    if do_plagiarism and work:
        from app.services.plagiarism import PlagiarismService

        plagiarism = PlagiarismService(session)
        vectors = []
        for d in work:
            try:
                prof = plagiarism.profile(str(d["id"]), d["text"], d["filename"], d["content_hash"])
                profiles[d["id"]] = prof
                vec = plagiarism.document_vector(prof)
                if vec:
                    vectors.append(vec)
                    await session.execute(update(Document).where(Document.id == d["id"]).values(embedding=vec))
            except Exception as exc:
                logger.exception("Profiling failed for %s", d["id"])
                d["error"] = f"Could not prepare document for comparison: {exc}"
        await session.commit()

        # ── Phase 2: cross-batch candidates, fetched once ──
        try:
            candidates = await plagiarism.cross_batch_candidates(
                str(batch_id), vectors, [d["content_hash"] for d in work], owner_id=owner_id
            )
        except Exception:
            logger.exception("Cross-batch search failed for batch %s", batch_id)
            await session.rollback()
            candidates = []

    ai_service = None
    if do_ai:
        from app.services.ai_detection import AIDetectionService

        ai_service = AIDetectionService()

    # ── Phase 3: per-document analysis ──
    for d in work:
        doc_id = d["id"]
        try:
            if d.get("error"):
                raise RuntimeError(d["error"])
            await session.execute(update(Document).where(Document.id == doc_id).values(status="processing"))
            values = {"status": "completed", "error": None}

            if ai_service:
                ai = await asyncio.to_thread(ai_service.detect, d["text"], provider, ai_threshold)
                if ai.get("label") == "Error":
                    raise RuntimeError(ai.get("details", {}).get("error", "AI detection failed"))
                values.update(
                    ai_score=ai.get("score", 0.0),
                    is_ai_generated=ai.get("is_ai", False),
                    ai_confidence=ai.get("confidence", 0.0),
                    ai_provider=str(ai.get("provider", "unknown")),
                    ai_label=ai.get("label"),
                )
                session.add(AIDetection(
                    document_id=doc_id,
                    model_version=ai.get("details", {}).get("model", "unknown"),
                    probability=ai.get("score", 0.0),
                    meta_data={
                        "provider": str(ai.get("provider", "unknown")),
                        "confidence": ai.get("confidence", 0.0),
                        "label": ai.get("label", "unknown"),
                        "statistics": ai.get("details", {}).get("statistics", {}),
                        "warning": ai.get("details", {}).get("warning"),
                    },
                ))

            if plagiarism and doc_id in profiles:
                me = profiles[doc_id]
                # Within this batch.
                for other in work:
                    if other["id"] == doc_id or other["id"] not in profiles:
                        continue
                    res = plagiarism.compare(me, profiles[other["id"]])
                    if plagiarism.is_reportable(res):
                        session.add(_comparison(doc_id, other["id"], res, cross_batch=False))
                # Against earlier batches.
                for cand in candidates:
                    cand_prof = plagiarism.profile(
                        cand["id"], cand["text_content"], cand["filename"], cand["content_hash"],
                        with_embeddings=cand["semantic"],
                    )
                    res = plagiarism.compare(me, cand_prof)
                    if plagiarism.is_reportable(res):
                        session.add(_comparison(doc_id, cand["id"], res, cross_batch=True))

            await session.execute(update(Document).where(Document.id == doc_id).values(**values))
            await session.commit()
        except Exception as exc:
            logger.exception("Document %s failed", doc_id)
            await session.rollback()
            await _fail_doc(session, doc_id, str(exc) or exc.__class__.__name__)
            failed += 1

        processed += 1
        await _set_progress(session, batch_id, processed)

    total = len(docs)
    if total == 0 or failed == total:
        status = "failed"
    elif failed:
        status = "completed_with_errors"
    else:
        status = "completed"
    await session.execute(
        update(Batch).where(Batch.id == batch_id).values(status=status, processed_docs=processed)
    )
    await session.commit()
    if plagiarism:
        plagiarism.clear_cache()


def _comparison(doc_a, doc_b, res: Dict, cross_batch: bool) -> Comparison:
    return Comparison(
        doc_a=doc_a,
        doc_b=doc_b,
        similarity=res["similarity"],
        lexical_similarity=res.get("lexical_similarity"),
        semantic_similarity=res.get("semantic_similarity"),
        cross_batch=cross_batch,
        matches=res.get("matches", []),
    )


async def _fail_doc(session: AsyncSession, doc_id, message: str):
    await session.execute(
        update(Document).where(Document.id == doc_id).values(status="failed", error=message[:2000])
    )
    await session.commit()


async def _set_progress(session: AsyncSession, batch_id, processed: int):
    await session.execute(update(Batch).where(Batch.id == batch_id).values(processed_docs=processed))
    await session.commit()
