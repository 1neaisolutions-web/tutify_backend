"""
Database session management with SSL support for cloud databases.
Includes retry logic and robust error handling for connection issues.
"""
from typing import Generator
import time

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import OperationalError, DisconnectionError, TimeoutError

from app.core.config import settings
from app.core.logging import get_logger
from app.db.base import Base

logger = get_logger(__name__)

# Determine if connecting to Supabase or other cloud database (requires SSL)
is_cloud_db = "supabase.co" in settings.DATABASE_URL or "pooler.supabase.com" in settings.DATABASE_URL

# Create SQLAlchemy engine optimized for cloud databases with SSL
# Keep statement timeout long enough for heavy OCR/chunk/index operations.
statement_timeout_ms = int(getattr(settings, "DB_STATEMENT_TIMEOUT_MS", 600000) or 600000)
statement_timeout = f"-c statement_timeout={statement_timeout_ms}"
timezone_setting = "-c timezone=utc"
db_options = f"{statement_timeout} {timezone_setting}"


def _postgres_connect_args() -> dict:
    """psycopg2/libpq kwargs for SQLAlchemy; keepalives help with dropped SSL on cloud poolers."""
    args: dict = {
        "connect_timeout": 15,
        "sslmode": "require" if is_cloud_db else "prefer",
        "options": db_options,
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 3,
    }
    return args


engine = create_engine(
    settings.DATABASE_URL,
    # Avoid extra pg_type query on connect (can fail when SSL drops mid-handshake on cloud DBs).
    use_native_hstore=False,
    pool_pre_ping=True,  # Check connection before using (important for cloud DBs)
    echo=settings.ENVIRONMENT == "dev",  # Echo SQL queries in dev mode
    connect_args=_postgres_connect_args() if "postgresql" in settings.DATABASE_URL else {},
    pool_timeout=30,  # Pool timeout (30 seconds - increased for better reliability)
    pool_size=10,  # Increased pool size for better concurrency
    max_overflow=20,  # Allow more overflow connections
    pool_reset_on_return='rollback',  # Never issue implicit commit on pooled connections
    pool_recycle=3600,  # Recycle connections after 1 hour
    poolclass=None,  # Use default queue pool
)

# Add connection pool event listeners for better error handling
@event.listens_for(engine, "connect")
def set_connection_pragmas(dbapi_conn, connection_record):
    """Set connection-level settings."""
    try:
        # Set timezone to UTC using cursor (psycopg2 requires cursor, not direct execute)
        cursor = dbapi_conn.cursor()
        cursor.execute("SET timezone TO 'UTC'")
        cursor.close()
    except Exception as e:
        logger.warning(f"Failed to set connection pragmas: {e}")

@event.listens_for(engine, "checkout")
def receive_checkout(dbapi_conn, connection_record, connection_proxy):
    """Handle connection checkout with retry logic."""
    # Connection is already checked by pool_pre_ping, but we can add additional logic here
    pass

# Create SessionLocal class
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,  # Avoid implicit lazy reloads after commit on long-running jobs.
    bind=engine,
)


def get_db() -> Generator[Session, None, None]:
    """
    Dependency function for FastAPI to get database session.
    Retries only SessionLocal() creation; yield/commit/close follow the standard pattern
    so the generator does not break exception propagation (Python 3.12+).
    """
    db: Session | None = None
    max_retries = 3
    retry_delay = 0.5

    for attempt in range(max_retries):
        try:
            db = SessionLocal()
            break
        except (OperationalError, DisconnectionError, TimeoutError) as e:
            error_msg = str(e).lower()
            is_connection_error = any(
                keyword in error_msg
                for keyword in [
                    "connection",
                    "timeout",
                    "network",
                    "could not connect",
                    "server closed",
                    "connection lost",
                    "connection refused",
                    "temporarily unavailable",
                    "pool",
                    "ssl",
                ]
            )
            if attempt < max_retries - 1 and is_connection_error:
                wait_time = retry_delay * (2**attempt)
                logger.warning(
                    "Database connection failed (attempt %s/%s): %s. Retrying in %.2fs...",
                    attempt + 1,
                    max_retries,
                    str(e),
                    wait_time,
                )
                time.sleep(wait_time)
                continue
            logger.error("Database connection error after %s attempts: %s", attempt + 1, e, exc_info=True)
            raise

    if db is None:
        raise RuntimeError("Could not create database session")

    try:
        # Request handlers/services own transaction boundaries and call commit explicitly.
        # Auto-committing here can fail after a streaming response has started and turn
        # otherwise handled DB disconnects into ASGI runtime errors.
        yield db
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            db.close()
        except Exception:
            pass

