import asyncio
import os
import uuid
import json
from io import BytesIO
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Body
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from sqlalchemy.orm import aliased

from app.core.db import get_db
from app.models.user import User
from app.models import Batch, Document, Comparison
from app.api.auth import get_current_user
from app.services.report import ReportService
from app.core.provider_router import ProviderType

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


# File size limit: 200MB
MAX_FILE_SIZE = 200 * 1024 * 1024

# Allowed file extensions
ALLOWED_EXTENSIONS = {
    '.pdf', '.docx', '.txt', '.png', '.jpg', '.jpeg',
    '.zip', '.tar', '.tar.gz', '.tgz',
}


def _sanitize_filename(filename: str) -> str:
    """Remove path traversal and null bytes from user-supplied filenames."""
    # Strip directory components (handles both / and \)
    filename = os.path.basename(filename)
    # Remove null bytes
    filename = filename.replace('\x00', '')
    # Reject empty filenames
    if not filename or filename in ('.', '..'):
        filename = 'unnamed_file'
    return filename


class AnalysisOptions(BaseModel):
    provider: str = Field(default=ProviderType.LOCAL, description="AI detection provider (local, openai, together)")
    ai_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    check_plagiarism: bool = True
    check_ai: bool = True


class AnalysisResponse(BaseModel):
    batch_id: str
    status: str
    message: str


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
    """
    try:
        parsed_options = json.loads(options)
        opts = AnalysisOptions(**parsed_options)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid options JSON: {e}")

    if not files and not text:
        raise HTTPException(status_code=400, detail="Must provide either files or text")

    # Validate file sizes before any processing
    for file in files:
        # Read a byte past the limit to check size without loading entire file
        file.file.seek(0, 2)  # Seek to end
        size = file.file.tell()
        file.file.seek(0)  # Reset
        if size > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"File '{file.filename}' is too large ({size / 1024 / 1024:.1f}MB). Maximum is 200MB."
            )

    # Create Batch
    batch_id = uuid.uuid4()
    analysis_type = "plagiarism"
    if opts.check_ai and opts.check_plagiarism:
        analysis_type = "both"
    elif opts.check_ai:
        analysis_type = "ai"

    batch = Batch(
        id=batch_id,
        user_id=user.id,
        total_docs=0,
        status="queued",
        analysis_type=analysis_type,
        ai_provider=opts.provider,
        ai_threshold=opts.ai_threshold
    )
    db.add(batch)

    # Process Text Input
    docs_to_process = []
    if text:
        doc = Document(
            id=uuid.uuid4(),
            batch_id=batch_id,
            filename="input_text.txt",
            storage_path=f"{batch_id}/input_text.txt",
            text_content=text,
            status="queued"
        )
        db.add(doc)
        docs_to_process.append(doc)

    # Process Uploaded Files
    from app.services.parsing import extract_text_from_file
    from app.services.storage import StorageService
    from app.services.archive_extractor import ArchiveExtractor
    storage_service = StorageService()

    # Extensions for files we can extract text from (excludes archives)
    DOC_EXTENSIONS = [ext for ext in ALLOWED_EXTENSIONS if ext not in {'.zip', '.tar', '.tar.gz', '.tgz'}]

    for file in files:
        safe_filename = _sanitize_filename(file.filename or 'unnamed_file')
        content = await file.read()

        # Check if this is an archive - if so, extract and process each file inside
        if ArchiveExtractor.is_archive(safe_filename):
            import tempfile
            import shutil
            # Write archive to temp file, extract, then process each inner file
            with tempfile.NamedTemporaryFile(suffix=os.path.splitext(safe_filename)[1] or '.zip', delete=False) as tmp:
                tmp.write(content)
                tmp_path = tmp.name
            extract_dir = None
            try:
                extracted = await asyncio.to_thread(
                    ArchiveExtractor.extract_and_filter,
                    tmp_path,
                    DOC_EXTENSIONS,
                )
                # Track the extraction directory for cleanup
                if extracted:
                    extract_dir = os.path.dirname(extracted[0][1])

                for inner_filename, inner_path in extracted:
                    inner_safe = _sanitize_filename(inner_filename)
                    with open(inner_path, 'rb') as f:
                        inner_content = f.read()

                    inner_storage_path = f"{batch_id}/{inner_safe}"
                    await asyncio.to_thread(storage_service.save, inner_storage_path, inner_content)

                    file_obj = BytesIO(inner_content)
                    file_obj.name = inner_safe
                    text_content = await extract_text_from_file(file_obj, inner_safe)

                    doc = Document(
                        batch_id=batch_id,
                        filename=inner_safe,
                        storage_path=inner_storage_path,
                        text_content=text_content,
                        status="queued"
                    )
                    db.add(doc)
                    docs_to_process.append(doc)
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
                # Clean up the extraction temp directory
                if extract_dir and os.path.exists(extract_dir):
                    shutil.rmtree(extract_dir, ignore_errors=True)
            continue

        # Regular (non-archive) file processing
        storage_path = f"{batch_id}/{safe_filename}"
        await asyncio.to_thread(storage_service.save, storage_path, content)

        file_obj = BytesIO(content)
        file_obj.name = safe_filename
        text_content = await extract_text_from_file(file_obj, safe_filename)

        doc = Document(
            batch_id=batch_id,
            filename=safe_filename,
            storage_path=storage_path,
            text_content=text_content,
            status="queued"
        )
        db.add(doc)
        docs_to_process.append(doc)

    batch.total_docs = len(docs_to_process)
    await db.commit()

    # Trigger Processing (Async)
    from app.services.batch_processing import process_batch
    process_batch.delay(str(batch_id), provider=opts.provider, ai_threshold=opts.ai_threshold)

    return AnalysisResponse(
        batch_id=str(batch_id),
        status="queued",
        message="Analysis started successfully"
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
        service = _get_ai_service()
        ai_result = service.detect(text, provider=provider, threshold=threshold)

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
    limit: int = 50,
    offset: int = 0,
):
    """List all batches for the current user, newest first."""
    result = await db.execute(
        select(Batch)
        .where(Batch.user_id == user.id)
        .order_by(desc(Batch.created_at))
        .limit(limit)
        .offset(offset)
    )
    batches = result.scalars().all()

    # Get document counts per batch
    batch_list = []
    for batch in batches:
        doc_count = await db.scalar(
            select(func.count(Document.id)).where(Document.batch_id == batch.id)
        )
        batch_list.append({
            "id": str(batch.id),
            "status": batch.status,
            "analysis_type": batch.analysis_type,
            "total_docs": batch.total_docs,
            "processed_docs": batch.processed_docs,
            "document_count": doc_count or 0,
            "created_at": batch.created_at.isoformat() if batch.created_at else None,
        })

    total = await db.scalar(
        select(func.count(Batch.id)).where(Batch.user_id == user.id)
    )

    return {"status": "ok", "data": batch_list, "total": total or 0}


@router.get("/batches/{batch_id}/results")
async def get_batch_results(
    batch_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Get detailed results for a batch, including AI scores and plagiarism matches.
    """
    batch_result = await db.execute(
        select(Batch).where(Batch.id == batch_id, Batch.user_id == user.id)
    )
    batch = batch_result.scalar_one_or_none()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    documents_result = await db.execute(
        select(Document).where(Document.batch_id == batch_id)
    )
    documents = documents_result.scalars().all()

    results = []
    for doc in documents:
        # Get plagiarism comparisons
        DocB = aliased(Document)
        comparisons_result = await db.execute(
            select(Comparison, DocB.filename.label("match_filename"))
            .join(DocB, Comparison.doc_b == DocB.id)
            .where(Comparison.doc_a == doc.id)
            .order_by(Comparison.similarity.desc())
        )
        comparisons = comparisons_result.all()

        plagiarism_details = []
        for comp, match_filename in comparisons:
            plagiarism_details.append({
                "similar_document": match_filename,
                "similarity": comp.similarity,
                "matches": comp.matches or []
            })

        results.append({
            "document_id": str(doc.id),
            "filename": doc.filename,
            "status": doc.status,
            "ai_analysis": {
                "score": doc.ai_score,
                "is_ai": doc.is_ai_generated,
                "confidence": doc.ai_confidence,
                "provider": doc.ai_provider
            },
            "plagiarism_analysis": plagiarism_details
        })

    return {
        "status": "ok",
        "batch": {
            "id": str(batch.id),
            "status": batch.status,
            "analysis_type": batch.analysis_type,
            "total_docs": batch.total_docs,
            "processed_docs": batch.processed_docs,
        },
        "data": results,
    }


async def _fetch_comparisons(db: AsyncSession, documents) -> dict:
    """
    Fetch all comparisons for a set of documents.
    Returns dict mapping doc_id -> list of (Comparison, match_filename) tuples.
    """
    doc_ids = [doc.id for doc in documents]
    if not doc_ids:
        return {}

    DocB = aliased(Document)
    comp_result = await db.execute(
        select(Comparison, DocB.filename.label("match_filename"))
        .join(DocB, Comparison.doc_b == DocB.id)
        .where(Comparison.doc_a.in_(doc_ids))
        .order_by(Comparison.similarity.desc())
    )
    rows = comp_result.all()

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
    batch_result = await db.execute(
        select(Batch).where(Batch.id == batch_id, Batch.user_id == user.id)
    )
    batch = batch_result.scalar_one_or_none()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

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
    batch_result = await db.execute(
        select(Batch).where(Batch.id == batch_id, Batch.user_id == user.id)
    )
    batch = batch_result.scalar_one_or_none()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

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
