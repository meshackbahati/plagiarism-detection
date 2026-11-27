# Plagiarism and AI Content Detection Tool

A locally deployable tool for detecting plagiarism and AI-generated content in documents and text. Designed to run on your own machine -- no external services required unless you opt in.

## Features

- **Plagiarism Detection**: Two signals. Word-for-word fingerprinting finds copy-paste and shows the exact copied passages; it works with no ML model. Sentence-BERT embeddings catch paraphrasing. Documents are compared within a batch and against earlier batches (pgvector). See [Plagiarism Detection Algorithm](docs/plagiarism.md).
- **AI Content Detection**: Hybrid approach combining a local HuggingFace classifier with statistical heuristics (burstiness, vocabulary diversity, sentence uniformity). External providers (OpenAI, Together) available as optional add-ons. See [AI Detection Methods](docs/ai-detection.md).
- **Batch Processing**: Upload multiple files at once. Celery handles async processing with session rollback and per-document status tracking. See [Batch Processing Pipeline](docs/architecture.md#7-batch-processing-appservicesbatch_processingpy).
- **Cross-Batch Plagiarism**: Documents are compared against earlier uploads too: pgvector nearest neighbours (paraphrase), identical files, and recent documents (word-for-word). Re-uploads of the same file collapse to the original. See [Algorithm Flow](docs/plagiarism.md#algorithm-flow).
- **Lightweight Mode**: Run on low-resource machines by skipping local ML models (~580MB saved). Word-for-word plagiarism checks still run. AI detection falls back to statistical heuristics or an external API provider. See [Lightweight Mode](#lightweight-mode-low-resource-machines).
- **Archive Support**: Upload ZIP/TAR archives. Files are read in memory with zip-slip, symlink and zip-bomb protection, then processed individually.
- **Clear failures**: An unreadable file (password-protected PDF, corrupt DOCX, empty scan) is recorded with a plain-English reason instead of failing the whole upload.
- **OCR Support**: Scanned PDFs and images (PNG, JPG, JPEG) are processed via Tesseract OCR.
- **Export**: Generate CSV and PDF reports with AI scores and plagiarism match details from stored Comparison data.
- **Local First**: All processing happens on your infrastructure. No data leaves your server unless you configure external API keys.

## Supported File Formats

| Format | Extension | Method |
|--------|-----------|--------|
| PDF (text) | `.pdf` | pdfminer.six (≥ 20251107, patched CVEs), first `MAX_PDF_PAGES` pages |
| PDF (scanned or broken fonts) | `.pdf` | Tesseract OCR page by page when the text layer is empty or mostly `(cid:N)` garbage |
| Word | `.docx` | python-docx: paragraphs, tables (in document order), headers and footers |
| Plain text | `.txt`, `.md` | UTF-8, UTF-16 (BOM) or Windows-1252 |
| Images | `.png`, `.jpg`, `.jpeg`, `.tif`, `.tiff`, `.bmp` | Tesseract OCR (EXIF rotation, multi-page TIFF) |
| Archives | `.zip`, `.tar`, `.tar.gz`, `.tgz`, `.tar.bz2` | Read in memory with path traversal, symlink and size-bomb protection |

Legacy `.doc` files are rejected with a message to save as `.docx` or PDF. Maximum file size: **200MB** (`MAX_UPLOAD_BYTES`, also enforced by nginx and the client).

## Quick Start

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose installed.

### Installation & Run

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd plagiarism-detection
   ```

2. **Configure** (optional):
   Edit [`backend/.env.docker`](backend/.env.docker) to set API keys, enable lightweight mode, etc. See [Environment Variables](#environment-variables) for all options.

3. **Start the application**:
   ```bash
   docker compose up -d
   ```

4. **Access the tool**:
   - Frontend: [http://localhost](http://localhost)
   - API Documentation: [http://localhost:8000/docs](http://localhost:8000/docs)
   - MinIO Console: [http://localhost:9001](http://localhost:9001) (minioadmin/minioadmin)

### Lightweight Mode (Low-Resource Machines)

If your machine doesn't have enough RAM for the local ML models (~580MB), enable lightweight mode:

```bash
# In backend/.env.docker
LIGHTWEIGHT_MODE=true
```

In this mode:
- No local ML models are loaded
- AI detection uses [statistical heuristics](docs/ai-detection.md#statistical-heuristics-always-available) only (always available, no model required)
- Set `OPENAI_API_KEY` or `TOGETHER_API_KEY` for ML-based AI detection via [external API](docs/providers.md#openai-api)
- Plagiarism embedding-based comparison is skipped (no sentence-transformers model)

See the [Provider Guide](docs/providers.md#choosing-a-configuration) for recommended configurations by use case.

### Resource Requirements

| Mode | Min RAM | Recommended RAM | Disk |
|------|---------|-----------------|------|
| Full (default) | 4GB | 8GB | 10GB |
| Lightweight | 1GB | 2GB | 2GB |

Docker [resource limits](docker-compose.yml) per container:

| Container | Memory Limit | Purpose |
|-----------|-------------|---------|
| PostgreSQL | 1GB | Database + pgvector |
| Redis | 256MB | Celery broker |
| MinIO | 512MB | File storage |
| Frontend (nginx) | 128MB | React SPA + proxy |
| API (FastAPI) | 2GB | REST API + text extraction |
| Celery Worker | 3GB | Async ML processing |

See [Architecture: Container Resources](docs/architecture.md#container-resources) for the full breakdown.

## How It Works

```
User uploads files
       |
       v
  [nginx :80] ──── React frontend + reverse proxy
       |
       v
  [FastAPI :8000] ── Validate, sanitize, extract text, store in MinIO
       |
       v
  [Celery Worker] ── Phase 1: Pre-compute embeddings (once per doc)
       |              Phase 2: AI detection + plagiarism comparison
       |              Phase 3: Cross-batch pgvector search
       v
  [PostgreSQL] ── Results stored with full match details
       |
       v
  Frontend polls /api/v1/batches/{id}/results
```

See [Architecture: Full System Design](docs/architecture.md) for the detailed data flow, model lifecycle management, and database schema.

## API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/analyze` | POST | Upload files/text for batch analysis |
| `/api/v1/ai-detection` | POST | Direct AI detection on text (min 10 words) |
| `/api/v1/ai-detection/health` | GET | Service + [model status](docs/architecture.md#1-model-manager-appcoremodel_managerpy) |
| `/api/v1/batches` | GET | List all batches (paginated, newest first) |
| `/api/v1/batches/{id}/results` | GET | Detailed results: AI scores, plagiarism matches with copied passages, per-file errors |
| `/api/v1/batches/{id}` | DELETE | Delete a batch, its documents, results and stored files |
| `/api/v1/batches/{id}/export/csv` | GET | CSV report using stored Comparison data |
| `/api/v1/batches/{id}/export/pdf` | GET | PDF report with AI + plagiarism tables |
| `/api/v1/users/me/dashboard` | GET | Dashboard metrics (batch/doc counts) |
| `/health` | GET | API health check |

See [Architecture: API Endpoints](docs/architecture.md#6-api-endpoints) for request flow details.

## Environment Variables

All configuration in [`backend/.env.docker`](backend/.env.docker):

| Variable | Default | Description |
|----------|---------|-------------|
| `LIGHTWEIGHT_MODE` | `false` | Skip local ML models ([details](docs/providers.md#model-lifecycle-management)) |
| `MODEL_UNLOAD_TIMEOUT` | `300` | Seconds idle before models auto-unload, 0 = disabled |
| `MAX_CROSS_BATCH_DOCS` | `500` | Recent earlier documents checked word-for-word ([cross-batch](docs/plagiarism.md#algorithm-flow)) |
| `CROSS_BATCH_SCOPE` | `user` | `user`: compare only against the same account's uploads. `all`: shared corpus; other accounts' names and text are hidden in results |
| `CROSS_BATCH_CANDIDATES` | `20` | pgvector nearest neighbours per document (paraphrase check) |
| `SHINGLE_SIZE` / `MIN_MATCH_WORDS` | `5` / `8` | Word-for-word sensitivity ([tuning](docs/plagiarism.md#tuning)) |
| `SEMANTIC_MATCH_THRESHOLD` | `0.82` | Cosine needed to call a chunk a paraphrase |
| `MAX_UPLOAD_BYTES` | `209715200` | Per-file upload limit |
| `MAX_FILES_PER_BATCH` | `500` | Files per upload (archives count their contents) |
| `MAX_PDF_PAGES` / `MAX_OCR_PAGES` | `1000` / `100` | Page caps for text extraction and OCR |
| `ARCHIVE_MAX_FILES` / `ARCHIVE_MAX_TOTAL_BYTES` | `500` / `500MB` | Zip-bomb limits |
| `OCR_LANG` / `OCR_DPI` | `eng` / `200` | Tesseract language(s), e.g. `eng+fra`, and scan resolution |
| `WEB_CONCURRENCY` | `2` | Gunicorn API workers |
| `STORAGE_TYPE` | `s3` | `s3` for MinIO or `local` for filesystem |
| `OPENAI_API_KEY` | _(empty)_ | Enables [OpenAI provider](docs/providers.md#openai-api) |
| `TOGETHER_API_KEY` | _(empty)_ | Enables [Together provider](docs/providers.md#together-api) |
| `SECRET_KEY` | _(must set in prod)_ | JWT signing key |
| `ADMIN_EMAIL` | `admin@example.com` | Seeded admin account |
| `ADMIN_PASSWORD` | _(must change)_ | Seeded admin password |

See [`backend/.env.docker.example`](backend/.env.docker.example) for a template with all options documented.

## Project Structure

```
plagiarism-detection/
  frontend/                        React + Vite + TypeScript
    nginx.conf                     Reverse proxy (200MB limit, timeouts)
    Dockerfile                     Multi-stage build (Node -> nginx)
    src/
      components/                  UI pages
        DashboardPage.tsx          Metrics + recent batches table
        UploadForm.tsx             File upload with size validation
        BatchResultsPage.tsx       Results with AI + plagiarism details
        AIDetectionPage.tsx        Direct text AI detection
        AdminPage.tsx              User management
        AuthProvider.tsx           Auth context
      utils/
        api.ts                     Safe fetch wrapper (handles non-JSON)
  backend/                         FastAPI + Celery
    Dockerfile                     Python 3.11 + system deps + Poetry
    startup.sh                     DB wait + MinIO bucket + Gunicorn/Celery
    pyproject.toml                 Dependencies (with [ai] group for models)
    app/
      core/
        config.py                  Settings (Pydantic BaseSettings)
        celery.py                  Celery app (memory limits configured)
        model_manager.py           Singleton ML model lifecycle manager
        provider_router.py         AI provider validation + routing
        db.py                      SQLAlchemy async engine
        schema.py                  Creates pgvector extension, tables, new columns
      models/
        __init__.py                All model exports (for Base.metadata)
        batch.py, document.py      Core data models (with FK indexes)
        comparison.py              Plagiarism match storage
        ai_detection.py            Detailed AI detection results
      services/
        ai_detection.py            Hybrid: model + heuristics + external
        plagiarism.py              Lexical + semantic comparison, cross-batch candidates
        fingerprint.py             Word n-gram fingerprints, copied-passage finder
        embedding.py               Sentence chunking + Sentence-BERT via ModelManager
        batch_processing.py        Celery pipeline (per-document commits, idempotent)
        parsing.py                 Text extraction (PDF, DOCX, TXT, OCR) + normalisation
        ocr.py                     Tesseract OCR service
        archive_extractor.py       ZIP/TAR with zip-slip protection
        report.py                  CSV + PDF report generation
        storage.py                 MinIO/S3 or local filesystem
      api/v1/
        routes.py                  REST endpoints + archive handling
    tests/                         pytest suite (unit + end-to-end with pgvector)
  docker-compose.yml               6 containers with resource limits
  docker-compose.dev.yml           Dev override: live-mount backend source
  .dockerignore                    Build context exclusions
  docs/                            Detailed documentation
    ai-detection.md                Detection methods, heuristics, scoring
    plagiarism.md                  Algorithm, caching, cross-batch search
    providers.md                   Provider comparison + configuration guide
    architecture.md                Full system design + database schema
```

## Documentation

| Document | Contents |
|----------|----------|
| [**AI Detection**](docs/ai-detection.md) | [Statistical heuristics](docs/ai-detection.md#statistical-heuristics-always-available), [local model](docs/ai-detection.md#local-model-default), [external providers](docs/ai-detection.md#external-providers), [scoring](docs/ai-detection.md#confidence-calculation), [limitations](docs/ai-detection.md#known-limitations) |
| [**Plagiarism Detection**](docs/plagiarism.md) | [Pipeline](docs/plagiarism.md#algorithm-flow), [word-for-word](docs/plagiarism.md#1-word-for-word-lexical-matching), [paraphrase](docs/plagiarism.md#2-paraphrase-semantic-matching), [tuning](docs/plagiarism.md#tuning), [limitations](docs/plagiarism.md#limitations) |
| [**Provider Guide**](docs/providers.md) | [Comparison table](docs/providers.md#quick-comparison), [decision guide](docs/providers.md#choosing-a-configuration), [model lifecycle](docs/providers.md#model-lifecycle-management), [error handling](docs/providers.md#error-handling) |
| [**Architecture**](docs/architecture.md) | [System diagram](docs/architecture.md#high-level-architecture), [ModelManager](docs/architecture.md#1-model-manager-appcoremodel_managerpy), [database schema](docs/architecture.md#database-schema), [deployment](docs/architecture.md#deployment) |

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| `413 Request Entity Too Large` | File exceeds 200MB nginx limit | Split file or increase `client_max_body_size` in `nginx.conf` |
| `JSON.parse: unexpected character` | Non-JSON error response | Fixed -- frontend now uses safe `apiRequest` wrapper |
| Celery worker OOM | Models too large for available RAM | Set `LIGHTWEIGHT_MODE=true` in `.env.docker` |
| `Database not ready` | PostgreSQL still starting | Automatic -- `startup.sh` retries 30 times |
| MinIO bucket missing | Bucket not created before API starts | Fixed -- `startup.sh` auto-creates with retry |
| AI detection inaccurate | Model trained on GPT-2 outputs | Use external provider for modern LLM detection |
| Slow batch processing | Large documents, many comparisons | Expected -- Celery processes one batch at a time |
| `relation "users" does not exist` | Older versions never enabled the pgvector extension, so tables were not created | Fixed: start-up now runs `CREATE EXTENSION vector` and stops loudly if the schema fails |
| `exec /app/startup.sh: no such file or directory` | Windows line endings or a bind mount hiding the script | Fixed: the script now lives at `/usr/local/bin/startup.sh` with CRLF stripped |
| A file shows "failed" with a reason | The file itself is unreadable (password, damaged, no text) | Fix the file and upload it again; other files in the batch are unaffected |
| First full-mode batch is slow | Models (~600MB) download once | Cached in the `model_cache` volume afterwards |

## Running the tests

```bash
cd backend
poetry install --with dev                      # add --with ai for the ML models
python -m pytest                               # unit tests
# End-to-end tests need PostgreSQL with pgvector:
TEST_DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/plagiarism_test python -m pytest
```

OCR tests need `tesseract` and `pdftoppm` (poppler) installed; they are skipped otherwise. CI runs everything on each pull request.

## License

MIT
