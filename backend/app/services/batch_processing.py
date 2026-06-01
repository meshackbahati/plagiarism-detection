from app.core.celery import app as celery_app
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.models.batch import Batch
from app.models.document import Document
from app.models.comparison import Comparison
import asyncio

engine = create_async_engine(settings.DATABASE_URL, echo=False)
SessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@celery_app.task(
    name='app.services.batch_processing.process_batch',
    bind=True,
    max_retries=2,
    default_retry_delay=30,
)
def process_batch(self, batch_id: str, provider: str = "local", ai_threshold: float = 0.5):
    """Process a batch of documents for plagiarism and/or AI detection."""
    asyncio.run(_process_batch_async(batch_id, provider, ai_threshold))


async def _process_batch_async(batch_id: str, provider: str, ai_threshold: float):
    async with SessionLocal() as session:
        # Get batch and documents
        batch = await session.get(Batch, batch_id)
        if not batch:
            print(f"Batch {batch_id} not found")
            return

        batch.status = "processing"
        await session.commit()

        # Get all documents in this batch
        from sqlalchemy import select
        result = await session.execute(
            select(Document).where(Document.batch_id == batch_id)
        )
        documents = result.scalars().all()

        analysis_type = batch.analysis_type or "plagiarism"

        # Use the shared model manager (lazy-loads models on first use)
        from app.services.embedding import EmbeddingService
        from app.services.ai_detection import AIDetectionService
        from app.services.plagiarism import PlagiarismService

        ai_service = AIDetectionService()
        embedding_service = EmbeddingService()
        plagiarism_service = PlagiarismService(session)

        failed_count = 0
        completed_count = 0

        # ── Phase 1: Pre-compute embeddings for ALL documents ──
        # This ensures each document is encoded exactly once.
        if analysis_type in ["plagiarism", "both", "mixed"] and embedding_service.model:
            for doc in documents:
                if doc.text_content and doc.text_content.strip():
                    chunks, embeddings = plagiarism_service.precompute_embeddings(
                        str(doc.id), doc.text_content
                    )
                    # Store document-level embedding for cross-batch search
                    if embeddings:
                        import numpy as np
                        doc.embedding = np.mean(embeddings, axis=0).tolist()

            await session.commit()

        # ── Phase 2: Process each document ──
        for doc in documents:
            try:
                doc.status = "processing"
                await session.commit()

                # Check for empty/failed text extraction
                if not doc.text_content or not doc.text_content.strip():
                    doc.status = "failed"
                    failed_count += 1
                    await session.commit()
                    print(f"Document {doc.id} ({doc.filename}): text extraction failed (empty content)")
                    continue

                # AI Detection
                if analysis_type in ["ai", "both", "mixed"]:
                    ai_result = ai_service.detect(doc.text_content, provider=provider, threshold=ai_threshold)
                    doc.ai_score = ai_result.get("score", 0.0)
                    doc.is_ai_generated = ai_result.get("is_ai", False)
                    doc.ai_confidence = ai_result.get("confidence", 0.0)
                    doc.ai_provider = ai_result.get("provider", "unknown")

                    # Store detailed AI detection result
                    from app.models.ai_detection import AIDetection
                    ai_detection_record = AIDetection(
                        document_id=doc.id,
                        model_version=ai_result.get("details", {}).get("model", "unknown"),
                        probability=ai_result.get("score", 0.0),
                        meta_data={
                            "provider": ai_result.get("provider", "unknown"),
                            "confidence": ai_result.get("confidence", 0.0),
                            "label": ai_result.get("label", "unknown"),
                            "statistics": ai_result.get("details", {}).get("statistics", {}),
                        },
                    )
                    session.add(ai_detection_record)

                # Plagiarism Detection (within batch, using cached embeddings)
                if analysis_type in ["plagiarism", "both", "mixed"] and embedding_service.model:
                    similar_results = await plagiarism_service.find_similar_in_batch(doc, batch_id)

                    for res in similar_results:
                        comparison = Comparison(
                            doc_a=doc.id,
                            doc_b=res["document_id"],
                            similarity=res["similarity"],
                            matches=res.get("matches", []),
                        )
                        session.add(comparison)

                    # Cross-batch plagiarism detection
                    cross_batch_results = await plagiarism_service.find_similar_across_batches(
                        doc, exclude_batch_id=str(batch_id)
                    )
                    for res in cross_batch_results:
                        from sqlalchemy import select as sa_select
                        match_doc_id = res["document_id"]
                        existing = await session.execute(
                            sa_select(Comparison).where(
                                Comparison.doc_a == doc.id,
                                Comparison.doc_b == match_doc_id,
                            )
                        )
                        if not existing.scalar_one_or_none():
                            comparison = Comparison(
                                doc_a=doc.id,
                                doc_b=match_doc_id,
                                similarity=res["similarity"],
                                matches=[{
                                    "cross_batch": True,
                                    "source_filename": res.get("filename", "unknown"),
                                }],
                            )
                            session.add(comparison)

                doc.status = "completed"
                completed_count += 1
                await session.commit()

            except Exception as e:
                print(f"Error processing document {doc.id}: {e}")
                await session.rollback()
                doc = await session.get(Document, doc.id)
                if doc:
                    doc.status = "failed"
                    failed_count += 1
                    try:
                        await session.commit()
                    except Exception:
                        await session.rollback()
                        print(f"Could not update status for document {doc.id}")

        # Update batch status based on results
        if failed_count == len(documents):
            batch.status = "failed"
        elif failed_count > 0:
            batch.status = "completed_with_errors"
        else:
            batch.status = "completed"

        batch.processed_docs = completed_count
        await session.commit()

        # Free the embedding cache to release memory
        plagiarism_service.clear_cache()
