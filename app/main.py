"""
FastAPI application factory and main entry point.
"""
import asyncio
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from sqlalchemy.exc import SQLAlchemyError, IntegrityError, OperationalError
from pydantic import ValidationError

from app.core.config import settings
from app.core.logging import setup_logging, get_logger
from app.core.middleware import TimeoutMiddleware
from app.core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    AccountLockedError,
    InvalidTokenError,
    UserNotFoundError,
    UserAlreadyExistsError,
    EmailNotVerifiedError,
    PasswordValidationError,
    InvalidCredentialsError,
)
from dotenv import load_dotenv
load_dotenv()
from app.api.v1 import router as v1_router
from app.db.session import SessionLocal
from app.domains.content_factory.services.gap_generation_worker import GapGenerationWorker

# Setup logging before creating the app
setup_logging()
logger = get_logger(__name__)

app = FastAPI(
    title="1ne.ai Backend API",
    description="AI-powered teacher assistant backend",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Add timeout middleware first (outermost) to catch all requests
app.add_middleware(
    TimeoutMiddleware,
    timeout=30.0,  # 30 seconds timeout to match frontend
)

# Add CORS middleware to allow frontend requests
# In development, allow all origins to avoid connection issues
if settings.ENVIRONMENT == "dev":
    cors_origins = ["*"]  # Allow all origins in development
else:
    # Get frontend URL from environment variable, fallback to localhost
    frontend_url = settings.FRONTEND_URL or "http://localhost:5173"
    
    cors_origins = [
        "https://1ne-frontend.vercel.app",  # Vercel production frontend
        frontend_url,  # Primary frontend URL from environment
        "http://localhost:5173",  # Vite default port (local dev)
        "http://localhost:3000",    # Alternative React port (local dev)
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
        "http://localhost:5174",  # Vite alternative port
        "http://127.0.0.1:5174",
    ]
    
    # Add Vercel frontend URL if provided via environment variable
    vercel_url = settings.FRONTEND_URL
    if vercel_url and vercel_url not in cors_origins:
        cors_origins.append(vercel_url)
    
    # Also allow any Vercel preview deployments (pattern matching)
    # This allows preview deployments to work without manual configuration
    import os
    vercel_preview_url = os.getenv("VERCEL_URL")
    if vercel_preview_url:
        cors_origins.append(f"https://{vercel_preview_url}")
    
    # Remove duplicates while preserving order
    cors_origins = list(dict.fromkeys(cors_origins))

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ========== Global Exception Handlers ==========

# Gap-detection background processor
#
# The learning hub personalization flow enqueues gap jobs, but the repository
# includes a dedicated worker class that must be actively processed for jobs
# to turn into published `content_registry` items.
#
# We run a conservative loop that processes at most one pending job at a time.
@app.on_event("startup")
async def _start_gap_generation_worker() -> None:
    if not settings.LEARNING_HUB_AUTO_LLM_ENABLED:
        logger.info(
            "GapGenerationWorker not started (LEARNING_HUB_AUTO_LLM_ENABLED is false)"
        )
        return

    async def loop() -> None:
        while True:
            try:
                # Do not hold a pooled connection here: process_once uses its own
                # short-lived sessions; an outer SessionLocal would sit checked out
                # for the entire run_job duration and exhaust the pool under load.
                worker = GapGenerationWorker()
                await worker.process_once()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"GapGenerationWorker loop error: {e}", exc_info=True)

            # Keep polling aggressive enough for progressive UX:
            # if only a few jobs are pending, users should not wait tens of seconds
            # between each generation attempt.
            await asyncio.sleep(2)

    app.state.gap_worker_task = asyncio.create_task(loop())


@app.on_event("shutdown")
async def _stop_gap_generation_worker() -> None:
    task = getattr(app.state, "gap_worker_task", None)
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

@app.exception_handler(AuthenticationError)
async def authentication_error_handler(request: Request, exc: AuthenticationError):
    """Handle authentication errors."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=exc.headers if hasattr(exc, "headers") else None,
    )


@app.exception_handler(AuthorizationError)
async def authorization_error_handler(request: Request, exc: AuthorizationError):
    """Handle authorization errors."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


@app.exception_handler(InvalidCredentialsError)
async def invalid_credentials_error_handler(request: Request, exc: InvalidCredentialsError):
    """Handle invalid credentials errors."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=exc.headers if hasattr(exc, "headers") else None,
    )


@app.exception_handler(UserNotFoundError)
async def user_not_found_error_handler(request: Request, exc: UserNotFoundError):
    """Handle user not found errors."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


@app.exception_handler(UserAlreadyExistsError)
async def user_already_exists_error_handler(request: Request, exc: UserAlreadyExistsError):
    """Handle user already exists errors."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


@app.exception_handler(EmailNotVerifiedError)
async def email_not_verified_error_handler(request: Request, exc: EmailNotVerifiedError):
    """Handle email not verified errors."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


@app.exception_handler(PasswordValidationError)
async def password_validation_error_handler(request: Request, exc: PasswordValidationError):
    """Handle password validation errors."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


@app.exception_handler(InvalidTokenError)
async def invalid_token_error_handler(request: Request, exc: InvalidTokenError):
    """Handle invalid token errors."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=exc.headers if hasattr(exc, "headers") else None,
    )


@app.exception_handler(AccountLockedError)
async def account_locked_error_handler(request: Request, exc: AccountLockedError):
    """Handle account locked errors."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    """Handle request validation errors."""
    logger.warning(f"Validation error: {exc.errors()}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": exc.errors()},
    )


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError):
    """Handle database integrity errors."""
    logger.error(f"Database integrity error: {str(exc)}", exc_info=True)
    
    # Check for common integrity errors
    error_str = str(exc.orig) if hasattr(exc, "orig") else str(exc)
    
    if "unique constraint" in error_str.lower() or "duplicate key" in error_str.lower():
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": "A record with this information already exists"},
        )
    elif "foreign key constraint" in error_str.lower():
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": "Invalid reference to related record"},
        )
    else:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": "Database constraint violation"},
        )


@app.exception_handler(OperationalError)
async def operational_error_handler(request: Request, exc: OperationalError):
    """Handle database operational errors."""
    logger.error(f"Database operational error: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": "Database service temporarily unavailable. Please try again later."},
    )


@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_error_handler(request: Request, exc: SQLAlchemyError):
    """Handle general SQLAlchemy errors."""
    logger.error(f"Database error: {str(exc)}", exc_info=True)

    exc_str = str(exc)
    exc_lower = exc_str.lower()
    is_schema_mismatch = (
        "does not exist" in exc_lower
        and ("content_generation_jobs" in exc_lower or "content_registry" in exc_lower)
        and ("column" in exc_lower or "relation" in exc_lower)
    )
    if is_schema_mismatch:
        # Operationally safe guidance: schema mismatch is almost always an un-run migration.
        detail = "Database schema is out of date. Please run `alembic upgrade head` and retry."
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": detail},
        )

    # In development, provide more details for debugging
    if settings.ENVIRONMENT != "prod":
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": "A database error occurred. Please try again later.",
                "error": exc_str,
                "type": type(exc).__name__,
            },
        )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "A database error occurred. Please try again later."},
    )


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    """Handle ValueError exceptions."""
    logger.warning(f"Value error: {str(exc)}")
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": str(exc)},
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle all other unhandled exceptions."""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    
    # Check if it's already an HTTPException (should have been handled by specific handlers)
    from fastapi import HTTPException as FastAPIHTTPException
    if isinstance(exc, FastAPIHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )
    
    # In production, don't expose internal error details
    if settings.ENVIRONMENT == "prod":
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "An internal server error occurred. Please try again later."},
        )
    else:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": "An internal server error occurred.",
                "error": str(exc),
                "type": type(exc).__name__,
            },
        )


@app.get("/health")
async def health_check():
    """
    Liveness probe — returns immediately (no DB).
    Use GET /health/ready for a database ping (may be slow on cold cloud Postgres).
    """
    return {"status": "ok", "liveness": True}


@app.get("/health/ready")
async def health_ready():
    """Readiness: verifies DB connectivity with a bounded async timeout."""
    from app.db.session import SessionLocal
    from sqlalchemy import text
    import asyncio

    def _db_ping() -> None:
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
        finally:
            db.close()

    try:
        await asyncio.wait_for(asyncio.to_thread(_db_ping), timeout=8.0)
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        logger.warning(f"Database health check failed: {e}")
        return {
            "status": "degraded",
            "database": "disconnected",
            "message": "Backend is running but database is unavailable",
            "error": str(e) if settings.ENVIRONMENT != "prod" else None,
        }


@app.get("/api/routes")
async def list_routes():
    """List all registered routes for debugging."""
    routes_info = []
    for route in app.routes:
        if hasattr(route, 'path') and hasattr(route, 'methods'):
            routes_info.append({
                "path": route.path,
                "methods": list(route.methods),
                "name": getattr(route, 'name', None)
            })
    return {
        "total_routes": len(routes_info),
        "routes": sorted(routes_info, key=lambda x: x["path"])
    }


@app.get("/api/v1/test")
async def test_endpoint():
    """Simple test endpoint that doesn't require database - for connection testing."""
    import datetime
    return {
        "status": "ok",
        "message": "Backend API is accessible",
        "cors": "enabled",
        "timestamp": datetime.datetime.now().isoformat()
    }


# Register API v1 routers (they already include /api/v1 prefixes)
try:
    app.include_router(v1_router)
    logger.info("API v1 router registered successfully")
    # Log registered routes for debugging
    for route in app.routes:
        if hasattr(route, 'path') and hasattr(route, 'methods'):
            logger.debug(f"Registered route: {list(route.methods)} {route.path}")
except Exception as e:
    logger.error(f"Failed to register API v1 router: {e}", exc_info=True)
    raise

# Teacher Tools — assignments: explicit mount (same URL prefix as domain router).
# Ensures /api/v1/teacher-tools/assignments is present even if the v1 package import tree drifts in a deploy.
try:
    from app.domains.teacher_assignment import routes as teacher_assignment_routes

    app.include_router(teacher_assignment_routes.router)
    logger.info("Teacher Tools assignment routes registered (explicit app mount)")
except Exception as e:
    logger.error("Failed to register teacher_assignment routes: %s", e, exc_info=True)
    raise

# Mount static files for profile pictures
from app.core.config import settings
profile_pictures_dir = Path(settings.PROFILE_PICTURES_DIR)
profile_pictures_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static/profile_pictures", StaticFiles(directory=str(profile_pictures_dir)), name="profile_pictures")
