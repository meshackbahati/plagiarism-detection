# Technical Documentation: Plagiarism & AI Detection System

## Architecture Overview

The plagiarism and AI detection system is built with a microservices architecture using Docker containers. The system consists of several interconnected services and now includes comprehensive user management with role-based access control:

### Core Components

1. **Frontend**: React 18 application built with Vite and TypeScript
2. **Backend API**: FastAPI application with async capabilities
3. **Database**: PostgreSQL with pgvector extension for vector similarity search
4. **Message Queue**: Redis with Celery for background task processing
5. **Storage**: MinIO (S3-compatible) for document storage
6. **Background Workers**: Celery workers for processing analysis tasks

### Data Flow

```
Document Upload → Storage (MinIO) → Text Extraction → Embedding Generation → 
Similarity Analysis → Results Storage → User Interface
```

## Backend Architecture

### Tech Stack
- **Framework**: FastAPI (Python 3.11)
- **Database**: PostgreSQL 15 + pgvector
- **ORM**: SQLAlchemy 2.0 (async)
- **Authentication**: FastAPI-Users with JWT
- **Background Jobs**: Celery + Redis
- **AI/ML**: sentence-transformers, transformers, PyTorch
- **OCR**: Tesseract, pdf2image

### Database Schema

#### Users Table
- `id`: UUID (Primary Key)
- `email`: String (Unique, Indexed)
- `hashed_password`: String
- `role`: String (Default: "user")
- `created_at`: DateTime (Auto-generated)
- `updated_at`: DateTime (Auto-updated)

#### Batches Table
- `id`: UUID (Primary Key)
- `user_id`: UUID (Foreign Key to Users)
- `name`: String
- `total_docs`: Integer
- `processed_docs`: Integer (Default: 0)
- `status`: String
- `analysis_type`: String (Default: "plagiarism")
- `created_at`: DateTime (Auto-generated)

#### Documents Table
- `id`: UUID (Primary Key)
- `batch_id`: UUID (Foreign Key to Batches)
- `filename`: String
- `content_hash`: String
- `mime_type`: String
- `text_content`: Text
- `embedding`: Vector(384) - pgvector embedding
- `storage_path`: String
- `uploaded_by`: UUID
- `status`: String (Default: "queued")
- `ai_score`: Float (Default: 0.0)
- `is_ai_generated`: Boolean (Default: False)
- `created_at`: DateTime (Auto-generated)
- `updated_at`: DateTime (Auto-updated)

#### Comparisons Table
- `id`: UUID (Primary Key)
- `doc_a`: UUID (Foreign Key to Documents)
- `doc_b`: UUID (Foreign Key to Documents)
- `similarity`: Float
- `matches`: JSON (Detailed chunk matches)
- `created_at`: DateTime

#### AI Detection Table
- `id`: UUID (Primary Key)
- `document_id`: UUID (Foreign Key to Documents)
- `model_version`: String
- `probability`: Float
- `meta_data`: JSONB (Detailed results)
- `created_at`: DateTime (Auto-generated)

### API Endpoints

#### Authentication
- `POST /api/auth/register` - User registration
- `POST /api/auth/login` - User login
- `POST /api/auth/logout` - User logout
- `GET /api/auth/me` - Get current user

#### Analysis
- `POST /api/v1/analyze` - Submit documents for analysis
- `POST /api/v1/ai-detection` - Direct AI detection
- `GET /api/v1/batches/{batch_id}/results` - Get batch results
- `GET /api/v1/batches/{batch_id}/export/pdf` - Export results as PDF
- `GET /api/v1/batches/{batch_id}/export/csv` - Export results as CSV
- `GET /api/v1/ai-detection/health` - AI service health check
- `GET /health` - System health check

### Core Services

#### 1. Embedding Service
Handles text embedding generation using sentence-transformers:

```python
class EmbeddingService:
    def __init__(self, model_name="sentence-transformers/all-MiniLM-L6-v2"):
        # Initializes the embedding model
        
    def chunk_text(self, text, chunk_size=500, overlap=50):
        # Splits text into overlapping chunks
        
    def encode_chunks(self, text):
        # Generates embeddings for text chunks
        
    def generate_text_embedding(self, text):
        # Creates averaged embedding for entire text
```

#### 2. Plagiarism Service
Performs semantic similarity analysis:

```python
class PlagiarismService:
    def calculate_similarity(self, embedding_a, embedding_b):
        # Calculates cosine similarity between embeddings
        
    async def compare_documents(self, doc_a_text: str, doc_b_text: str):
        # Compares two documents using chunk-based analysis
        
    async def find_similar_in_batch(self, document: Document, batch_id: str):
        # Finds similar documents within the same batch
```

#### 3. AI Detection Service
Detects AI-generated content using multiple approaches:

```python
class AIDetectionService:
    def detect(self, text: str, provider: str = "local", threshold: float = 0.5):
        # Main detection method with provider selection
        
    def _detect_local(self, text: str, threshold: float):
        # Uses local roberta-base-openai-detector model
        
    def _detect_external(self, text: str, provider: str, threshold: float):
        # Uses OpenAI or Together API
```

#### 4. Batch Processing Service
Handles background processing of document batches:

```python
@celery.task
def process_batch(batch_id: str, provider: str = "local", ai_threshold: float = 0.5):
    # Processes a batch of documents asynchronously
```

### Security Implementation

#### Authentication
- JWT tokens with configurable expiration
- Secure cookie transport
- Password hashing with Argon2
- Role-based access control (user/moderator/admin)

#### Authorization
- Per-request user validation
- Resource ownership verification
- Permission-based endpoint access
- Admin-only endpoints for user management
- Moderator and admin access levels

#### User Management
- Automatic database seeding on first startup
- Admin user creation with environment variables
- User role assignment and modification
- User deactivation (soft delete) functionality

#### Input Validation
- Pydantic models for request/response validation
- File type and size validation
- SQL injection protection through ORM

## Frontend Architecture

### Tech Stack
- **Framework**: React 18 with TypeScript
- **Routing**: React Router DOM
- **Styling**: Tailwind CSS with custom design system
- **State Management**: React Context API

### Component Structure
```
App
├── AuthProvider
├── MainLayout
│   ├── Navbar
│   └── Routes
│       ├── LandingPage
│       ├── LoginPage
│       ├── RegisterPage
│       ├── DashboardPage
│       ├── UploadForm
│       ├── AIDetectionPage
│       ├── AdminPage
│       └── BatchResultsPage
```

### Key Features
- Responsive design with mobile-first approach
- Glassmorphism UI design
- Real-time progress indicators
- Secure authentication flow
- File upload with drag-and-drop
- Results visualization

## AI/ML Implementation

### Semantic Plagiarism Detection
Uses sentence-transformers with pgvector for similarity search:
- Chunks documents into overlapping segments
- Generates embeddings for each chunk
- Performs cosine similarity calculations
- Identifies matching passages between documents

### AI Content Detection
Supports multiple detection methods:
- **Local**: roberta-base-openai-detector model
- **OpenAI**: GPT-based analysis via API
- **Together**: Alternative models via API

### Text Processing Pipeline
1. Document parsing (PDF, DOCX, TXT, images)
2. OCR for scanned documents
3. Text cleaning and normalization
4. Chunking for large documents
5. Embedding generation
6. Analysis and comparison

## Performance Optimization

### Database Optimization
- Vector indexes on embedding columns
- Proper indexing on foreign keys and frequently queried fields
- Connection pooling with SQLAlchemy
- Async database operations

### Caching Strategy
- Redis for session storage
- Potential caching for embeddings and results
- CDN for static assets

### Background Processing
- Celery workers for analysis tasks
- Redis as message broker
- Task prioritization and retry mechanisms

### Memory Management
- Efficient text chunking to prevent OOM errors
- Streaming for large file processing
- Model loading optimization

## Deployment Configuration

### Docker Multi-stage Build
Frontend uses build-time optimization:
- Node.js builder stage
- Nginx production stage
- Asset optimization and compression

Backend includes all necessary dependencies:
- System packages for OCR and PDF processing
- Python dependencies via pip
- Security hardening with non-root user

### Environment Configuration
All settings configurable via environment variables:
- Database connections
- API keys
- Storage settings
- Security parameters

## Testing Strategy

### Backend Tests
- Unit tests for services and utilities
- Integration tests for API endpoints
- Database transaction tests
- Async operation tests

### Frontend Tests
- Component rendering tests
- User interaction tests
- API integration tests
- Responsive design tests

## Error Handling

### Backend Error Handling
- Global exception handlers
- Custom HTTP exceptions
- Graceful degradation
- Detailed error logging

### Frontend Error Handling
- User-friendly error messages
- Network error recovery
- Form validation
- Loading states

## Security Considerations

### Authentication Security
- Strong password hashing with Argon2
- JWT token security
- Secure session management
- Rate limiting considerations

### Data Security
- Encrypted data transmission
- Secure file storage
- Input sanitization
- Access control enforcement

### Infrastructure Security
- Container isolation
- Network segmentation
- Resource limits
- Secure base images

---

This technical documentation provides comprehensive insight into the system architecture, implementation details, and operational considerations for the plagiarism and AI detection system.