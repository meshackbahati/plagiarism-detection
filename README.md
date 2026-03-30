# Plagiarism Detection

Plagiarism + AI-generated text detection platform with a React frontend, FastAPI backend, PostgreSQL + pgvector, Redis/Celery workers, and optional S3-compatible storage.

## What this release fixes

- Backend startup errors (`app.api.routes` import mismatch) are removed.
- Auth routes are now mounted and usable (`/api/auth/*` and `/api/v1/auth/*`).
- Frontend and backend auth paths are aligned.
- Async DB usage issues in batch results endpoints are fixed.
- Admin role update payload contract is fixed.
- File parsing now handles uploaded files and in-memory buffers safely.
- Sensitive reset/verification tokens are no longer logged.
- Insecure sample user seeding is now opt-in (`CREATE_SAMPLE_USERS=true`).
- Password hashing upgraded to Argon2 for better security.
- Comprehensive user dashboard with statistics and activity metrics.
- Report export functionality (PDF/CSV) for analysis results.
- Docs and env templates are updated for cross-platform use.

## Quick Start (Windows, macOS, Linux)

### Prerequisites

- Docker Desktop (Windows/macOS) or Docker Engine + Compose plugin (Linux)
- Git
- Python 3.11+ (Required for local development without Docker)

### 1. Clone

```bash
git clone https://github.com/Kyle6012/plagiarism-detection.git
cd plagiarism-detection
```

### 2. Configure environment

macOS/Linux:

```bash
cp backend/.env.docker.example backend/.env.docker
```

Windows PowerShell:

```powershell
Copy-Item backend/.env.docker.example backend/.env.docker
```

Edit `backend/.env.docker` and set at minimum:

- `SECRET_KEY` to a long random string (e.g., `openssl rand -hex 32`)
- `ADMIN_EMAIL`
- `ADMIN_PASSWORD`

### 3. Start everything (Docker Recommended)

```bash
docker compose up --build -d
```

**Windows Users:** If you encounter issues with Docker startup on Windows, ensure you are using Docker Desktop with the WSL2 backend. If `startup.sh` is not found, try rebuilding with `docker compose build --no-cache api`.

### 4. Open the app

- Frontend: http://localhost
- API docs: http://localhost:8000/docs
- Health: http://localhost:8000/health

## Default API route map

- Auth: `/api/auth/*` and `/api/v1/auth/*`
- Users: `/api/users/*` and `/api/v1/users/*`
- Analysis: `/api/v1/*`
- Admin: `/api/admin/*`

## Local Development (without Docker, optional)

### Backend (Requires Python 3.11+)

```bash
cd backend
python -m venv .venv
```

macOS/Linux:

```bash
source .venv/bin/activate
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

**Important for Windows Local Development:**
1. Ensure Python 3.11 is installed and in your PATH.
2. Install [Tesseract OCR for Windows](https://github.com/UB-Mannheim/tesseract/wiki) and [Poppler for Windows](http://blog.alivate.com.au/poppler-windows/).
3. Add Tesseract and Poppler bin directories to your Windows System PATH.

Install deps and run:

```bash
pip install --upgrade pip
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## Security notes

- Do not run production with default/example secrets.
- `ENVIRONMENT=production` now requires a non-default `SECRET_KEY`.
- Sample users are disabled by default (`CREATE_SAMPLE_USERS=false`).

## Useful commands

```bash
# Rebuild cleanly
docker compose down
docker compose up --build -d

# Logs
docker compose logs -f api
docker compose logs -f frontend
docker compose logs -f celery-worker
```

## Documentation

- [Developer Guide](./DEVELOPER_GUIDE.md)
- [Deployment Guide](./DEPLOYMENT_GUIDE.md)
- [Technical Docs](./TECHNICAL_DOCS.md)

## License

MIT
