import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from app.core.config import settings

logger = logging.getLogger(__name__)

# Determine if using SQLite or PostgreSQL
is_sqlite = settings.DATABASE_URL.startswith("sqlite")

connect_args = {"check_same_thread": False} if is_sqlite else {}

try:
    engine = create_engine(
        settings.DATABASE_URL,
        connect_args=connect_args,
        pool_pre_ping=True,
        echo=False
    )
except Exception as e:
    logger.error(f"Failed to initialize database engine with URL {settings.DATABASE_URL}: {e}")
    # Fallback to local SQLite if PostgreSQL connection fails
    fallback_url = "sqlite:///./baby_monitor_fallback.db"
    logger.warning(f"Falling back to local SQLite at {fallback_url}")
    engine = create_engine(fallback_url, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    """FastAPI dependency for yielding database session per request."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """Create all database tables on startup if they do not exist."""
    import app.models.models  # Ensure models are registered
    Base.metadata.create_all(bind=engine)

    # Safe auto-migration for newly added columns across PostgreSQL / SQLite
    try:
        with engine.begin() as conn:
            if engine.dialect.name == "postgresql":
                conn.execute(text("ALTER TABLE sensor_readings ADD COLUMN IF NOT EXISTS classification VARCHAR(50);"))
                conn.execute(text("ALTER TABLE sensor_readings ADD COLUMN IF NOT EXISTS confidence FLOAT;"))
                conn.execute(text("ALTER TABLE sensor_readings ADD COLUMN IF NOT EXISTS source VARCHAR(32) DEFAULT 'esp32_device';"))
            elif engine.dialect.name == "sqlite":
                res = conn.execute(text("PRAGMA table_info(sensor_readings);")).fetchall()
                col_names = [r[1] for r in res] if res else []
                if "classification" not in col_names:
                    conn.execute(text("ALTER TABLE sensor_readings ADD COLUMN classification VARCHAR(50);"))
                if "confidence" not in col_names:
                    conn.execute(text("ALTER TABLE sensor_readings ADD COLUMN confidence FLOAT;"))
                if "source" not in col_names:
                    conn.execute(text("ALTER TABLE sensor_readings ADD COLUMN source VARCHAR(32) DEFAULT 'esp32_device';"))
    except Exception as e:
        logger.warning(f"Database schema auto-sync note: {e}")

    logger.info("Database tables initialized successfully.")
