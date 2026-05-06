"""
Custom middleware for FastAPI application.
Includes timeout middleware to prevent hanging requests.
"""
import asyncio
from typing import Callable
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from fastapi import status

from app.core.logging import get_logger

logger = get_logger(__name__)

# Default timeout: 30 seconds (matches frontend timeout)
DEFAULT_REQUEST_TIMEOUT = 30.0
PIXGEN_REQUEST_TIMEOUT = 120.0


class TimeoutMiddleware(BaseHTTPMiddleware):
    """
    Middleware to enforce request timeouts and prevent hanging requests.
    
    This middleware wraps all requests in a timeout to ensure they don't hang
    indefinitely. If a request takes longer than the timeout, it will be
    cancelled and return a 504 Gateway Timeout response.
    """
    
    def __init__(self, app, timeout: float = DEFAULT_REQUEST_TIMEOUT):
        super().__init__(app)
        self.timeout = timeout

    def _resolve_timeout(self, request: Request) -> float:
        """
        Resolve per-route timeout while keeping a safe global default.

        PixGen generation calls can exceed 30s due to external model latency,
        so they receive a larger budget without relaxing timeout for all APIs.
        """
        path = request.url.path
        if path in {
            "/api/v1/generate",
            "/api/v1/generate-batch",
            "/api/v1/pixgen/generate",
            "/api/v1/pixgen/generate-batch",
        }:
            return PIXGEN_REQUEST_TIMEOUT
        return self.timeout
    
    async def dispatch(self, request: Request, call_next: Callable):
        """
        Process request with timeout protection.
        
        Args:
            request: The incoming request
            call_next: The next middleware/route handler
            
        Returns:
            Response with timeout protection
        """
        # Skip timeout for streaming endpoints and long-running worksheet generation
        if request.url.path.endswith('/execute-stream') or '/stream' in request.url.path:
            return await call_next(request)
        if '/worksheets/generate' in request.url.path and request.method == 'POST':
            return await call_next(request)
        # Auth + hub home can exceed 30s on cold DB / SSL reconnect (demo + cloud Postgres)
        path = request.url.path
        if path.startswith("/api/v1/auth/login") or path.startswith("/api/v1/auth/register"):
            return await call_next(request)
        if path.startswith("/api/v1/auth/refresh") or path.startswith("/api/v1/auth/signup"):
            return await call_next(request)
        if path == "/api/v1/learning-hub/home":
            return await call_next(request)
        if path in ("/health", "/health/ready", "/"):
            return await call_next(request)
        
        try:
            # Wrap the request handling in a timeout
            timeout_seconds = self._resolve_timeout(request)
            response = await asyncio.wait_for(
                call_next(request),
                timeout=timeout_seconds
            )
            return response
        except asyncio.TimeoutError:
            timeout_seconds = self._resolve_timeout(request)
            logger.warning(
                f"Request timeout after {timeout_seconds}s: {request.method} {request.url.path}"
            )
            return JSONResponse(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                content={
                    "detail": f"Request timeout: The server took longer than {timeout_seconds} seconds to process the request. Please try again or contact support if the issue persists."
                }
            )
        except Exception as e:
            # Log unexpected errors but don't let them hang
            logger.error(f"Unexpected error in timeout middleware: {str(e)}", exc_info=True)
            raise
