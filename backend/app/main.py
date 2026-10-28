from contextlib import asynccontextmanager
from datetime import datetime, timezone
import logging
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.core.config import settings
from app.core.database import get_db, init_db
from app.schemas.schemas import HealthResponse
from app.api.readings import router as readings_router
from app.api.events import router as events_router
from app.api.stats import router as stats_router
from app.api.audio import router as audio_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("baby_monitor_api")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    logger.info("Initializing Smart Baby Monitoring System Backend...")
    try:
        init_db()
        logger.info("Database schemas verified.")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
    yield
    logger.info("Shutting down backend server.")

app = FastAPI(
    title="Smart Baby Monitoring System API",
    description="IoT Acoustic Sensor Ingestion & Alert Backend (MCA College Major Project)",
    version="1.0.0",
    lifespan=lifespan
)

# CORS Middleware for Local Frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS if isinstance(settings.CORS_ORIGINS, list) else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API Routers
app.include_router(readings_router)
app.include_router(events_router)
app.include_router(stats_router)
app.include_router(audio_router)

@app.get("/", tags=["General"])
def root():
    """Root endpoint providing project overview and documentation links."""
    return {
        "project": "Smart Baby Monitoring System",
        "role": "IoT Acoustic Monitoring & Assistive Alert Backend",
        "version": "1.0.0",
        "status": "operational",
        "docs_url": "/docs",
        "redoc_url": "/redoc"
    }

@app.get("/health", response_model=HealthResponse, tags=["General"])
def health_check(db: Session = Depends(get_db)):
    """Verifies API status and database connectivity."""
    db_status = "connected"
    try:
        db.execute(text("SELECT 1"))
    except Exception as e:
        logger.error(f"Health check database query failed: {e}")
        db_status = f"disconnected: {str(e)}"
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "degraded", "database": db_status}
        )

    return HealthResponse(
        status="healthy",
        database=db_status,
        timestamp=datetime.now(timezone.utc),
        version="1.0.0"
    )
