import os
from contextlib import asynccontextmanager

import loguru
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.admin import router as admin_router
from app.api.auth import router as auth_router
from app.api.users import router as users_router
from app.api.v1.routes import router as analysis_router
from app.core.db import async_engine
from app.models.base import Base


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    yield
    # Shutdown
    loguru.logger.info("Shutting down...")


app = FastAPI(title="Plagiarism Detection API", lifespan=lifespan)

# CORS: strict by default, open in development only.
allowed_origins = ["http://localhost:5173", "http://localhost:80", "http://localhost"]
if os.getenv("ENVIRONMENT") == "development":
    allowed_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Auth and user routers (both canonical and v1 aliases for frontend compatibility).
# Registration and login routes are disabled in the local tool version
app.include_router(users_router, prefix="/api/users")
app.include_router(users_router, prefix="/api/v1/users")

# Domain routers.
app.include_router(admin_router, prefix="/api")
app.include_router(analysis_router, prefix="/api/v1")




@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.get("/")
async def root():
    return {"message": "Plagiarism Detection API", "status": "running"}
