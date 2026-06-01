# System Architecture

## Overview

A plagiarism and AI content detection system designed for local deployment. Uses Docker Compose to orchestrate 6 containers (7 with optional celery-beat) with explicit resource limits.

## High-Level Architecture

```
┌─────────────────┐
│  React Frontend │  Vite, TypeScript, TailwindCSS
│  (nginx :80)    │  Serves SPA + proxies /api/ to backend
└────────┬────────┘
         │ HTTP/REST
         ▼
┌─────────────────┐
│  FastAPI :8000  │  Python 3.11+, async, Gunicorn + Uvicorn workers
└───┬────┬────┬───┘
    │    │    │
    ▼    ▼    ▼
┌──────┐ ┌──────┐ ┌─────────┐
│Pg+   │ │Redis │ │MinIO    │
│vector│ │      │ │(S3)     │
└──────┘ └──┬───┘ └─────────┘
            │
            ▼
     ┌──────────────┐
     │ Celery Worker │  Async batch processing
     │ (1 process)   │  ML models loaded lazily
     └──────────────┘

External (optional):
  OpenAI API  │  Together AI API
```

## Container Resources

| Container | Image | Memory Limit | Purpose |
|-----------|-------|-------------|---------|
| `db` | ankane/pgvector:v0.5.1 | 1GB | PostgreSQL + vector extension |
| `redis` | redis:7-alpine | 256MB | Celery broker + result backend |
| `minio` | minio/minio | 512MB | S3-compatible file storage |
| `frontend` | nginx | 128MB | React SPA + reverse proxy |
| `api` | Custom (FastAPI) | 2GB | REST API + text extraction |
| `celery-worker` | Custom (Celery) | 3GB | Async ML processing |
| `celery-beat` | Custom (Celery) | 128MB | Scheduled tasks (optional, `--profile scheduled`) |

## Core Components

### 1. Model Manager (`app/core/model_manager.py`)

Thread-safe singleton that manages ML model lifecycle:

```
ModelManager (singleton)
├── embedding_model      # sentence-transformers/all-MiniLM-L6-v2 (~80MB)
│   ├── Lazy-loaded on first access
│   ├── Shared across all EmbeddingService instances
│   └── Auto-unloaded after idle timeout
│
└── ai_classifier        # roberta-base-openai-detector (~500MB)
    ├── Lazy-loaded on first access
    ├── Shared across all AIDetectionService instances
    └── Auto-unloaded after idle timeout
```

**Configuration:**
- `LIGHTWEIGHT_MODE=true` -- No models loaded at all
- `MODEL_UNLOAD_TIMEOUT=300` -- Seconds idle before auto-unload (0 = disabled)

### 2. Provider Router (`app/core/provider_router.py`)

Routes AI detection requests to Local/OpenAI/Together backends:
- Validates provider availability (API keys, model status)
- Fails explicitly when provider is misconfigured (no silent fallbacks)
- Logs all provider usage

### 3. AI Detection Service (`app/services/ai_detection.py`)

Hybrid detection combining:
- **Local model** (when available): HuggingFace classifier, chunked inference
- **Statistical heuristics** (always available): Burstiness, vocabulary, uniformity, Zipf's law
- **External APIs** (when configured): GPT-4o-mini or Mixtral-8x7B

Scoring: 70% model + 30% heuristics (local), 75% API + 25% heuristics (external).

### 4. Embedding Service (`app/services/embedding.py`)

Generates Sentence-BERT embeddings via the shared `ModelManager`:
- Chunks text into 500-char segments with 50-char overlap
- Encodes each chunk into a 384-dimensional vector
- Averages chunk embeddings for document-level embedding

### 5. Plagiarism Service (`app/services/plagiarism.py`)

Two-phase comparison pipeline:

**Phase 1 -- Pre-compute:** All documents encoded once, cached in memory.

**Phase 2 -- Compare:** Pairwise comparison using cached embeddings with vectorized numpy operations. Each chunk in doc A compared against all chunks in doc B via matrix multiply.

**Cross-batch search:** Document-level embeddings queried against all stored documents via pgvector cosine distance (`<=>` operator).

### 6. API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/analyze` | POST | Upload files/text for batch analysis |
| `/api/v1/ai-detection` | POST | Direct AI detection on text (min 10 words) |
| `/api/v1/ai-detection/health` | GET | Service status + model status |
| `/api/v1/batches` | GET | List batches (paginated, newest first) |
| `/api/v1/batches/{id}/results` | GET | Detailed results with AI scores + plagiarism matches |
| `/api/v1/batches/{id}/export/csv` | GET | CSV report with plagiarism data from stored Comparisons |
| `/api/v1/batches/{id}/export/pdf` | GET | PDF report with AI + plagiarism tables |
| `/api/v1/users/me/dashboard` | GET | Dashboard metrics (batch count, doc count) |
| `/health` | GET | API health check |

**Request flow for `/api/v1/analyze`:**
1. Validate file sizes (max 200MB) and sanitize filenames
2. Detect archives (ZIP/TAR) -- extract and process inner files individually
3. Store files in MinIO/S3 (or local filesystem)
4. Extract text: PDFMiner for PDFs, python-docx for DOCX, Tesseract OCR for images/scanned PDFs
5. Create Batch + Document records in PostgreSQL
6. Send Celery task for async processing
7. Return batch_id immediately

### 7. Batch Processing (`app/services/batch_processing.py`)

Celery task that runs asynchronously:

```
process_batch(batch_id, provider, ai_threshold)
│
├── Phase 1: Pre-compute embeddings for all documents
│   ├── Encode chunks (once per document)
│   ├── Cache in PlagiarismService._embedding_cache
│   └── Store document-level embedding in DB
│
├── Phase 2: Process each document
│   ├── AI detection (if analysis_type includes AI)
│   │   ├── Store score, label, confidence on Document
│   │   └── Store detailed result in AIDetection table
│   │
│   ├── Within-batch plagiarism (if analysis_type includes plagiarism)
│   │   ├── Compare against all other docs in batch (cached)
│   │   └── Store Comparison records
│   │
│   ├── Cross-batch plagiarism
│   │   ├── pgvector similarity search against all stored docs
│   │   └── Store cross-batch Comparison records
│   │
│   └── Error handling: session rollback, doc marked "failed"
│
├── Update batch status: completed / completed_with_errors / failed
└── Clear embedding cache
```

**Worker configuration:**
- `--concurrency=1` -- One task at a time (ML models are memory-heavy)
- `worker_max_tasks_per_child=5` -- Restart after 5 tasks (prevents memory leaks)
- `worker_prefetch_multiplier=1` -- Don't grab extra tasks while busy
- `task_acks_late=True` -- Re-queue on failure

## Database Schema

```sql
-- Users
CREATE TABLE users (
    id UUID PRIMARY KEY,
    email VARCHAR UNIQUE NOT NULL,
    hashed_password VARCHAR NOT NULL,
    role VARCHAR DEFAULT 'user',
    is_active BOOLEAN DEFAULT true
);

-- Batches
CREATE TABLE batches (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES users(id),  -- indexed
    total_docs INT,
    processed_docs INT DEFAULT 0,
    status VARCHAR(50),                  -- queued/processing/completed/completed_with_errors/failed
    analysis_type VARCHAR(50),           -- plagiarism/ai/both
    ai_provider VARCHAR(50),
    ai_threshold FLOAT DEFAULT 0.5,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Documents
CREATE TABLE documents (
    id UUID PRIMARY KEY,
    batch_id UUID REFERENCES batches(id),  -- indexed
    filename VARCHAR NOT NULL,
    text_content TEXT,
    embedding VECTOR(384),                 -- SBERT document-level embedding
    status VARCHAR(50) DEFAULT 'queued',   -- indexed
    ai_score FLOAT,
    is_ai_generated BOOLEAN,
    ai_confidence FLOAT,
    ai_provider VARCHAR,
    storage_path VARCHAR,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Comparisons (plagiarism matches)
CREATE TABLE comparisons (
    id UUID PRIMARY KEY,
    doc_a UUID REFERENCES documents(id),   -- indexed
    doc_b UUID REFERENCES documents(id),   -- indexed
    similarity FLOAT NOT NULL,
    matches JSON,                          -- chunk match details
    created_at TIMESTAMPTZ DEFAULT now()
);

-- AI Detection (detailed results)
CREATE TABLE ai_detection (
    id UUID PRIMARY KEY,
    document_id UUID REFERENCES documents(id),  -- indexed
    model_version VARCHAR,
    probability FLOAT,
    meta_data JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Additional tables (registered but not actively used in processing):
-- embeddings: Per-chunk embedding storage (file_id indexed)
-- results: Generic result storage (file_id, matched_file_id indexed)
-- tasks: Async task tracking
```

## Security

**Implemented:**
- JWT-based authentication with configurable secret key
- User-scoped batch access (users can only see their own batches)
- File size validation (200MB limit, enforced server-side and client-side)
- Filename sanitization (path traversal protection via `os.path.basename`)
- Archive extraction with zip-slip protection (validates paths don't escape extraction directory)
- Provider validation (explicit API key checks, no silent fallbacks)
- nginx `client_max_body_size` prevents large payload attacks

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18, TypeScript, Vite 5, TailwindCSS 4 |
| Backend | FastAPI, Gunicorn, Uvicorn |
| Database | PostgreSQL 15 + pgvector 0.5 |
| Task Queue | Celery 5 + Redis 7 |
| Storage | MinIO (S3-compatible) |
| ML: Embeddings | sentence-transformers/all-MiniLM-L6-v2 |
| ML: AI Detection | roberta-base-openai-detector |
| ML: OCR | Tesseract (pytesseract + pdf2image) |
| ML: PDF | PDFMiner |
| ML: DOCX | python-docx |
| Reverse Proxy | nginx |
| Containerization | Docker Compose |

## Deployment

### Standard (default)
```bash
docker compose up -d
```
Starts all services except celery-beat.

### With scheduled tasks
```bash
docker compose --profile scheduled up -d
```
Includes celery-beat (currently no scheduled tasks defined).

### Lightweight (low-resource)
```bash
# In backend/.env.docker:
LIGHTWEIGHT_MODE=true
OPENAI_API_KEY=sk-your-key  # Optional

docker compose up -d
```
Skips ML model loading, uses heuristics + external APIs.
