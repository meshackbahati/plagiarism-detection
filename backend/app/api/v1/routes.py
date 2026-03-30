from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Body
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
import uuid
import json

from app.core.db import get_db
from app.models.user import User
from fastapi.responses import Response, StreamingResponse
from app.api.auth import fastapi_users
from app.services.ai_detection import AIDetectionService
from app.services.report import ReportService
from app.core.provider_router import ProviderType

router = APIRouter()
ai_service = AIDetectionService()
# PlagiarismService needs a session, so we instantiate it per request

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
    user: User = Depends(fastapi_users.current_user())
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

    # Create Batch
    from app.models import Batch, Document
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
        doc_id = uuid.uuid4()
        doc = Document(
            id=doc_id,
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
    storage_service = StorageService()
    
    for file in files:
        content = await file.read()
        storage_path = f"{batch_id}/{file.filename}"
        storage_service.save(storage_path, content)
        
        # Extract text
        from io import BytesIO
        file_obj = BytesIO(content)
        file_obj.name = file.filename
        text_content = await extract_text_from_file(file_obj, file.filename)
        
        doc = Document(
            batch_id=batch_id,
            filename=file.filename,
            storage_path=storage_path,
            text_content=text_content,
            status="queued"
        )
        db.add(doc)
        docs_to_process.append(doc)

    batch.total_docs = len(docs_to_process)
    await db.commit()

    # Trigger Processing (Async) - Options stored in batch
    from app.services.batch_processing import process_batch
    
    process_batch.delay(str(batch_id), provider=opts.provider, ai_threshold=opts.ai_threshold)

    return AnalysisResponse(
        batch_id=str(batch_id),
        status="queued",
        message="Analysis started successfully"
    )

@router.get("/ai-detection/health")
async def ai_health_check():
    """Health check for AI detection service."""
    health_status = ai_service.health_check()
    return {"service": "ai_detection", "health": health_status}

@router.post("/ai-detection")
async def detect_ai_only(
    text: str = Body(..., embed=True),
    provider: str = Body("local", embed=True),
    threshold: float = Body(0.5, embed=True),
    user: User = Depends(fastapi_users.current_user())
):
    """
    Direct AI detection endpoint for text.
    """
    try:
        ai_result = ai_service.detect(text, provider=provider, threshold=threshold)
        
        # Create temporary document to store result
        from app.models.document import Document
        from app.models.ai_detection import AIDetection
        from sqlalchemy.orm import Session
        from app.core.db import get_db
        
        # Note: For this endpoint, we're returning the result directly
        # In a full implementation, we might want to store this in the DB
        return {
            "is_ai": ai_result["is_ai"],
            "score": ai_result["score"],
            "confidence": ai_result["confidence"],
            "label": ai_result["label"],
            "provider": ai_result["provider"],
            "details": ai_result["details"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI detection failed: {str(e)}")

@router.get("/batches/{batch_id}/results")
async def get_batch_results(
    batch_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(fastapi_users.current_user())
):
    """
    Get detailed results for a batch, including AI scores and plagiarism matches.
    """
    from app.models import Batch, Document, Comparison
    from sqlalchemy import select
    from sqlalchemy.orm import aliased

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
                "matches": comp.matches or [] # Detailed chunks
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
        
    return {"status": "ok", "data": results}

@router.get("/batches/{batch_id}/export/pdf")
async def export_batch_pdf(
    batch_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(fastapi_users.current_user())
):
    """Export batch results as PDF"""
    from app.models import Batch, Document
    from sqlalchemy import select

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

    pdf_content = ReportService.generate_pdf_report(batch, documents)

    return Response(
        content=pdf_content,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=report_{batch_id}.pdf"}
    )

@router.get("/batches/{batch_id}/export/csv")
async def export_batch_csv(
    batch_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(fastapi_users.current_user())
):
    """Export batch results as CSV"""
    from app.models import Batch, Document
    from sqlalchemy import select

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

    csv_content = ReportService.generate_csv_report(documents)

    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=report_{batch_id}.csv"}
    )
