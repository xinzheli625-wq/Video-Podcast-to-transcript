"""
FastAPI Application Entry Point
"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1 import transcribe, tasks
from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    print(f"Starting {settings.app_name} v{settings.app_version}")

    # Create directories
    os.makedirs(settings.temp_dir, exist_ok=True)
    os.makedirs("data", exist_ok=True)
    
    print("Service is ready!")

    yield

    # Shutdown
    print("Shutting down...")


def create_app() -> FastAPI:
    """Create FastAPI application."""
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Asynchronous Audio/Video Transcription API with Celery",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount static files (frontend)
    frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
    if os.path.exists(frontend_dir):
        app.mount("/frontend", StaticFiles(directory=frontend_dir), name="frontend")
        print(f"Static files mounted: {frontend_dir}")

    # Include routers
    app.include_router(
        transcribe.router,
        prefix="/api/v1",
        tags=["transcription"],
    )
    app.include_router(
        tasks.router,
        prefix="/api/v1",
        tags=["tasks"],
    )

    # Health check
    @app.get("/health")
    async def health_check():
        return {"status": "healthy", "version": settings.app_version}

    @app.get("/")
    async def root():
        return {
            "name": settings.app_name,
            "version": settings.app_version,
            "docs": "/docs",
            "health": "/health",
            "frontend": "/frontend/index.html",
        }

    return app


app = create_app()
