import asyncio
import hashlib
import logging
import mimetypes
import os
import uuid
import json
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Body, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, or_, delete as sa_delete
from sqlalchemy.orm import aliased

from app.core.db import get_db
from app.models.user import User
from app.models import AIDetection, Batch, Comparison, Document, Embedding, Result
from app.api.auth import get_current_user
from app.services.report import ReportService
from app.core.config import settings
from app.core.provider_router import ProviderRouter, ProviderType
from app.services.archive_extractor import ArchiveError, ArchiveExtractor
from app.services.batch_processing import process_batch
from app.services.parsing import DOCUMENT_EXTENSIONS, ExtractionError, extract_text_from_bytes
from app.services.storage import StorageService

logger = logging.getLogger(__name__)

router = APIRouter()

# Lazy-load AI service to avoid loading 500MB model in every Gunicorn worker.
# Only loaded when the /ai-detection endpoint is actually called.
_ai_service = None


def _get_ai_service():
    global _ai_service
    if _ai_service is None:
        from app.services.ai_detection import AIDetectionService
        _ai_service = AIDetectionService()
    return _ai_service


MAX_FILE_SIZE = settings.MAX_UPLOAD_BYTES

ARCHIVE_EXTENSIONS = {'.zip', '.tar', '.tar.gz', '.tgz', '.tar.bz2', '.tbz2'}
ALLOWED_EXTENSIONS = DOCUMENT_EXTENSIONS | ARCHIVE_EXTENSIONS


def _sanitize_filename(filename: str) -> str:
    """Remove path components, control characters and odd whitespace from a user-supplied name."""
    filename = filename.replace("\\", "/")
    filename = os.path.basename(filename)
    filename = "".join(ch for ch in filename if ch.isprintable()).strip()
    if not filename or filename in ('.', '..'):
        filename = 'unnamed_file'
    return filename[:200]


class AnalysisOptions(BaseModel):
    provider: str = Field(default=ProviderType.LOCAL, description="AI detection provider (local, openai, together)")
    ai_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    check_plagiarism: bool = True
    check_ai: bool = True


class AnalysisResponse(BaseModel):
    batch_id: str
    status: str
    message: str
    documents: int = 0
    failed_documents: int = 0
    skipped: List[str] = []


def _new_document(batch_id, display_name: str, content: bytes) -> Document:
    doc_id = uuid.uuid4()
    return Document(
        id=doc_id,
        batch_id=batch_id,
        filename=display_name[:255],
        # doc id prefix: two files with the same name never overwrite each other
        storage_path=f"{batch_id}/{doc_id}_{_sanitize_filename(display_name)}",
        content_hash=hashlib.sha256(content).hexdigest() if content else None,
        mime_type=mimetypes.guess_type(display_name)[0],
        status="queued",
    )


async def _fill_text(doc: Document, content: bytes, filename: str) -> None:
    """Extract text into doc, or mark it failed with a readable reason."""
    try:
        result = await asyncio.to_thread(extract_text_from_bytes, content, filename)
    except ExtractionError as exc:
        doc.status, doc.error = "failed", str(exc)
        return
    except Exception as exc:  # never let one file sink the whole upload
        logger.exception("Extraction crashed for %s", filename)
        doc.status, doc.error = "failed", f"Could not read this file ({exc.__class__.__name__})."
        return
    doc.text_content = result.text
    doc.word_count = len(result.text.split())
    doc.extraction_method = result.method
    if result.warnings:
        doc.error = " ".join(result.warnings)  # informational; status stays queued


@router.post("/analyze", response_model=AnalysisResponse)
async def analyze_content(
    files: List[UploadFile] = File(default=[]),
    text: Optional[str] = Form(default=None),
    options: str = Form(default='{"provider": "local", "check_plagiarism": true, "check_ai": true}'),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Unified endpoint for analyzing content (files or text).
    Supports Plagiarism and AI Detection with configurable providers.
    Unreadable files are recorded as failed documents with a reason instead
    of failing the whole upload.
    """
    try:
        opts = AnalysisOptions(**json.loads(options))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid options JSON: {e}")

    if not opts.check_ai and not opts.check_plagiarism:
        raise HTTPException(status_code=400, detail="Choose at least one check: plagiarism or AI detection.")

    try:
        ProviderRouter().validate_provider(opts.provider)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    text = (text or "").strip() or None
    files = [f for f in files if f is not None and f.filename]
    if not files and not text:
        raise HTTPException(status_code=400, detail="Must provide either files or text")
    if len(files) > settings.MAX_FILES_PER_BATCH:
        raise HTTPException(status_code=400, detail=f"Too many files (maximum {settings.MAX_FILES_PER_BATCH} per upload).")

    for file in files:
        file.file.seek(0, 2)
        size = file.file.tell()
        file.file.seek(0)
        if size > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"File '{file.filename}' is too large ({size / 1024 / 1024:.1f}MB). Maximum is {MAX_FILE_SIZE // (1024 * 1024)}MB."
            )
        name = (file.filename or "").lower()
        if not any(name.endswith(ext) for ext in ALLOWED_EXTENSIONS):
            raise HTTPException(
                status_code=400,
                detail=f"'{file.filename}' is not a supported file type. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}.",
            )

    batch_id = uuid.uuid4()
    analysis_type = "both" if (opts.check_ai and opts.check_plagiarism) else ("ai" if opts.check_ai else "plagiarism")
    first_name = _sanitize_filename(files[0].filename) if files else "Pasted text"
    item_count = len(files) + (1 if text else 0)
    batch = Batch(
        id=batch_id,
        user_id=user.id,
        name=first_name if item_count == 1 else f"{first_name} + {item_count - 1} more",
        total_docs=0,
        status="queued",
        analysis_type=analysis_type,
        ai_provider=opts.provider,
        ai_threshold=opts.ai_threshold,
    )
    db.add(batch)

    storage_service = StorageService()
    docs: List[Document] = []
    skipped: List[str] = []

    async def store(doc: Document, content: bytes):
        try:
            await asyncio.to_thread(storage_service.save, doc.storage_path, content)
        except Exception as exc:
            logger.exception("Storage failed for %s", doc.filename)
            raise HTTPException(status_code=503, detail=f"File storage is unavailable: {exc}")

    if text:
        content = text.encode("utf-8")
        doc = _new_document(batch_id, "Pasted text.txt", content)
        await _fill_text(doc, content, "input.txt")
        await store(doc, content)
        docs.append(doc)

    for file in files:
        safe_filename = _sanitize_filename(file.filename or 'unnamed_file')
        content = await file.read()

        if ArchiveExtractor.is_archive(safe_filename):
            try:
                members, notes = await asyncio.to_thread(
                    ArchiveExtractor.read_members, content, safe_filename, DOCUMENT_EXTENSIONS
                )
            except ArchiveError as exc:
                doc = _new_document(batch_id, safe_filename, content)
                doc.status, doc.error = "failed", str(exc)
                docs.append(doc)
                continue
            skipped.extend(f"{safe_filename}: {n}" for n in notes)
            if not members:
                doc = _new_document(batch_id, safe_filename, content)
                doc.status, doc.error = "failed", "The archive contains no supported documents."
                docs.append(doc)
                continue
            for member in members:
                if len(docs) >= settings.MAX_FILES_PER_BATCH:
                    skipped.append(f"{safe_filename}/{member.name}: batch file limit reached")
                    continue
                display = f"{safe_filename}/{member.name}"
                doc = _new_document(batch_id, display, member.content)
                await _fill_text(doc, member.content, member.name)
                await store(doc, member.content)
                docs.append(doc)
            continue

        doc = _new_document(batch_id, safe_filename, content)
        await _fill_text(doc, content, safe_filename)
        await store(doc, content)
        docs.append(doc)

    for doc in docs:
        db.add(doc)
    batch.total_docs = len(docs)
    await db.commit()

    try:
        process_batch.delay(str(batch_id), provider=opts.provider, ai_threshold=opts.ai_threshold)
    except Exception as exc:
        logger.exception("Could not queue batch %s", batch_id)
        batch.status, batch.error = "failed", f"Task queue unavailable: {exc}"
        await db.commit()
        raise HTTPException(status_code=503, detail="The analysis queue (Redis/Celery) is unavailable. Try again shortly.")

    failed = sum(1 for d in docs if d.status == "failed")
    return AnalysisResponse(
        batch_id=str(batch_id),
        status="queued",
        message="Analysis started successfully" if failed < len(docs) else "None of the files could be read",
        documents=len(docs),
        failed_documents=failed,
        skipped=skipped[:100],
    )


@router.get("/ai-detection/health")
async def ai_health_check():
    """Health check for AI detection service, including model status."""
    from app.core.model_manager import model_manager
    service = _get_ai_service()
    health_status = service.health_check()
    health_status["models"] = model_manager.status()
    return {"service": "ai_detection", **health_status}


@router.post("/ai-detection")
async def detect_ai_only(
    text: str = Body(..., embed=True),
    provider: str = Body("local", embed=True),
    threshold: float = Body(0.5, embed=True),
    user: User = Depends(get_current_user)
):
    """
    Direct AI detection endpoint for text.
    """
    if not text or not text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    if len(text.strip().split()) < 10:
        raise HTTPException(status_code=400, detail="Text is too short for reliable AI detection (minimum 10 words)")

    try:
        if len(text) > 200_000:
            raise HTTPException(status_code=400, detail="Text is too long for direct checking (maximum 200,000 characters). Upload it as a file instead.")
        if not 0.0 <= threshold <= 1.0:
            raise HTTPException(status_code=400, detail="threshold must be between 0 and 1")
        service = _get_ai_service()
        # Model inference is blocking; keep the event loop free.
        ai_result = await asyncio.to_thread(service.detect, text, provider, threshold)

        if ai_result.get("label") == "Error":
            raise HTTPException(status_code=500, detail=ai_result.get("details", {}).get("error", "AI detection failed"))

        return {
            "is_ai": ai_result["is_ai"],
            "score": ai_result["score"],
            "confidence": ai_result["confidence"],
            "label": ai_result["label"],
            "provider": ai_result["provider"],
            "details": ai_result["details"]
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI detection failed: {str(e)}")


@router.get("/batches")
async def list_batches(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List all batches for the current user, newest first."""
    doc_counts = (
        select(Document.batch_id, func.count(Document.id).label("n"))
        .group_by(Document.batch_id)
        .subquery()
    )
    result = await db.execute(
        select(Batch, doc_counts.c.n)
        .outerjoin(doc_counts, doc_counts.c.batch_id == Batch.id)
        .where(Batch.user_id == user.id)
        .order_by(desc(Batch.created_at))
        .limit(limit)
        .offset(offset)
    )
    batch_list = [
        {
            "id": str(batch.id),
            "name": batch.name,
            "status": batch.status,
            "analysis_type": batch.analysis_type,
            "total_docs": batch.total_docs,
            "processed_docs": batch.processed_docs,
            "document_count": n or 0,
            "error": batch.error,
            "created_at": batch.created_at.isoformat() if batch.created_at else None,
        }
        for batch, n in result.all()
    ]

    total = await db.scalar(select(func.count(Batch.id)).where(Batch.user_id == user.id))
    return {"status": "ok", "data": batch_list, "total": total or 0}


async def _get_user_batch(db: AsyncSession, batch_id: uuid.UUID, user: User) -> Batch:
    batch = (
        await db.execute(select(Batch).where(Batch.id == batch_id, Batch.user_id == user.id))
    ).scalar_one_or_none()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    return batch


def _public_match(m: dict) -> dict:
    return {
        "type": m.get("type", "semantic" if not m.get("cross_batch") else "exact"),
        "source_chunk": m.get("source_chunk", ""),
        "target_chunk": m.get("target_chunk", ""),
        "score": m.get("score", 0.0),
        "words": m.get("words"),
    }


@router.get("/batches/{batch_id}/results")
async def get_batch_results(
    batch_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Detailed results for a batch: AI scores and plagiarism matches with evidence."""
    batch = await _get_user_batch(db, batch_id, user)
    documents = (
        await db.execute(select(Document).where(Document.batch_id == batch_id).order_by(Document.filename))
    ).scalars().all()
    comparisons = await _fetch_comparisons(db, documents)

    results = []
    for doc in documents:
        plagiarism_details = [
            {
                "document_id": str(comp.doc_b),
                "similar_document": match_filename,
                "similarity": comp.similarity,
                "lexical_similarity": comp.lexical_similarity,
                "semantic_similarity": comp.semantic_similarity,
                "cross_batch": bool(comp.cross_batch),
                # Old rows stored only metadata ({"cross_batch": true, ...}); drop those.
                "matches": [_public_match(m) for m in (comp.matches or []) if m.get("source_chunk")],
            }
            for comp, match_filename in comparisons.get(doc.id, [])
        ]
        results.append({
            "document_id": str(doc.id),
            "filename": doc.filename,
            "status": doc.status,
            "error": doc.error,
            "word_count": doc.word_count,
            "extraction_method": doc.extraction_method,
            "ai_analysis": {
                "score": doc.ai_score,
                "is_ai": doc.is_ai_generated,
                "confidence": doc.ai_confidence,
                "provider": doc.ai_provider,
                "label": doc.ai_label,
            },
            "plagiarism_analysis": plagiarism_details,
        })

    return {
        "status": "ok",
        "batch": {
            "id": str(batch.id),
            "name": batch.name,
            "status": batch.status,
            "analysis_type": batch.analysis_type,
            "total_docs": batch.total_docs,
            "processed_docs": batch.processed_docs,
            "error": batch.error,
            "created_at": batch.created_at.isoformat() if batch.created_at else None,
        },
        "data": results,
    }


@router.delete("/batches/{batch_id}")
async def delete_batch(
    batch_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Delete a batch, its documents, results and stored files."""
    await _get_user_batch(db, batch_id, user)
    docs = (
        await db.execute(select(Document.id, Document.storage_path).where(Document.batch_id == batch_id))
    ).all()
    doc_ids = [d.id for d in docs]
    if doc_ids:
        await db.execute(sa_delete(Comparison).where(or_(Comparison.doc_a.in_(doc_ids), Comparison.doc_b.in_(doc_ids))))
        await db.execute(sa_delete(AIDetection).where(AIDetection.document_id.in_(doc_ids)))
        await db.execute(sa_delete(Embedding).where(Embedding.file_id.in_(doc_ids)))
        await db.execute(sa_delete(Result).where(or_(Result.file_id.in_(doc_ids), Result.matched_file_id.in_(doc_ids))))
        await db.execute(sa_delete(Document).where(Document.id.in_(doc_ids)))
    await db.execute(sa_delete(Batch).where(Batch.id == batch_id))
    await db.commit()

    storage = StorageService()
    for d in docs:
        if d.storage_path:
            try:
                await asyncio.to_thread(storage.delete, d.storage_path)
            except Exception:
                logger.warning("Could not delete stored file %s", d.storage_path)
    return {"status": "ok", "deleted_documents": len(doc_ids)}


async def _fetch_comparisons(db: AsyncSession, documents) -> dict:
    """Map doc_id -> list of (Comparison, match_filename), highest similarity first."""
    doc_ids = [doc.id for doc in documents]
    if not doc_ids:
        return {}

    DocB = aliased(Document)
    rows = (
        await db.execute(
            select(Comparison, DocB.filename.label("match_filename"))
            .join(DocB, Comparison.doc_b == DocB.id)
            .where(Comparison.doc_a.in_(doc_ids))
            .order_by(Comparison.similarity.desc())
        )
    ).all()

    lookup: dict = {doc_id: [] for doc_id in doc_ids}
    for comp, match_filename in rows:
        lookup.setdefault(comp.doc_a, []).append((comp, match_filename))
    return lookup


@router.get("/batches/{batch_id}/export/pdf")
async def export_batch_pdf(
    batch_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Export batch results as PDF"""
    batch = await _get_user_batch(db, batch_id, user)

    documents_result = await db.execute(
        select(Document).where(Document.batch_id == batch_id)
    )
    documents = documents_result.scalars().all()

    # Query comparisons for all documents in this batch
    comparisons = await _fetch_comparisons(db, documents)

    pdf_content = ReportService.generate_pdf_report(batch, documents, comparisons)

    return Response(
        content=pdf_content,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=report_{batch_id}.pdf"}
    )


@router.get("/batches/{batch_id}/export/csv")
async def export_batch_csv(
    batch_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Export batch results as CSV"""
    batch = await _get_user_batch(db, batch_id, user)

    documents_result = await db.execute(
        select(Document).where(Document.batch_id == batch_id)
    )
    documents = documents_result.scalars().all()

    # Query comparisons for all documents in this batch
    comparisons = await _fetch_comparisons(db, documents)

    csv_content = ReportService.generate_csv_report(batch, documents, comparisons)

    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=report_{batch_id}.csv"}
    )
