"""
Custom exceptions for the application.
"""
from fastapi import HTTPException, status


class AuthenticationError(HTTPException):
    """Raised when authentication fails."""
    def __init__(self, detail: str = "Authentication failed"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )


class AuthorizationError(HTTPException):
    """Raised when user lacks required permissions."""
    def __init__(self, detail: str = "Insufficient permissions"):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
        )


class AccountLockedError(HTTPException):
    """Raised when account is locked."""
    def __init__(self, detail: str = "Account is locked. Please try again later."):
        super().__init__(
            status_code=status.HTTP_423_LOCKED,
            detail=detail,
        )


class InvalidTokenError(HTTPException):
    """Raised when token is invalid or expired."""
    def __init__(self, detail: str = "Invalid or expired token"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )


class UserNotFoundError(HTTPException):
    """Raised when user is not found."""
    def __init__(self, detail: str = "User not found"):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail,
        )


class UserAlreadyExistsError(HTTPException):
    """Raised when user already exists."""
    def __init__(self, detail: str = "User already exists"):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
        )


class InvalidCredentialsError(HTTPException):
    """Raised when credentials are invalid."""
    def __init__(self, detail: str = "Invalid email or password"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )


class EmailNotVerifiedError(HTTPException):
    """Raised when email is not verified."""
    def __init__(self, detail: str = "Email not verified. Please check your email."):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
        )


class TokenExpiredError(HTTPException):
    """Raised when token has expired."""
    def __init__(self, detail: str = "Token has expired"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )


class PasswordValidationError(HTTPException):
    """Raised when password doesn't meet requirements."""
    def __init__(self, detail: str = "Password does not meet requirements"):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
        )



