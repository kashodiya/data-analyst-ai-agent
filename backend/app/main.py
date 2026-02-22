"""Main FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import settings
from .api import sessions_router, messages_router, database_router
from .api.debug import router as debug_router
from .utils.dependencies import get_session_manager

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("Starting Data Analytics Agent...")

    # Initialize database
    session_manager = get_session_manager()
    await session_manager.initialize()
    logger.info("Database initialized")

    yield

    # Shutdown
    logger.info("Shutting down Data Analytics Agent...")


# Create FastAPI app
app = FastAPI(
    title="Data Analytics Agent",
    description="General Purpose Data Analytics Agent with SQL capabilities",
    version="0.1.0",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(sessions_router)
app.include_router(messages_router)
app.include_router(database_router)
app.include_router(debug_router)


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "version": "0.1.0",
        "llm_model": settings.llm_model
    }

# Mount frontend static files (must be after API routes)
frontend_path = Path(__file__).parent.parent.parent / "frontend"
if frontend_path.exists():
    app.mount("/", StaticFiles(directory=str(frontend_path), html=True), name="frontend")
    logger.info(f"Frontend mounted from {frontend_path}")
else:
    logger.warning(f"Frontend directory not found at {frontend_path}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
        log_level=settings.log_level.lower()
    )