"""
Security utilities for password hashing, JWT tokens, and validation.
"""
import secrets
import re
import bcrypt
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt

from app.core.config import settings
from app.core.exceptions import (
    InvalidTokenError,
    PasswordValidationError,
)

# Bcrypt rounds (12 is a good balance between security and performance)
BCRYPT_ROUNDS = 12


def _truncate_password(password: str) -> bytes:
    """
    Truncate password to 72 bytes (bcrypt limit).
    Ensures we don't break UTF-8 encoding.
    
    Args:
        password: Plain text password
        
    Returns:
        Password as bytes, truncated to 72 bytes if necessary
    """
    password_bytes = password.encode('utf-8')
    if len(password_bytes) > 72:
        # Truncate to 72 bytes
        truncated = password_bytes[:72]
        # Ensure we don't break UTF-8 encoding - find last valid boundary
        try:
            truncated.decode('utf-8')
        except UnicodeDecodeError:
            # Find the last valid UTF-8 character boundary
            while truncated and truncated[-1] & 0x80 and not (truncated[-1] & 0x40):
                truncated = truncated[:-1]
    else:
        truncated = password_bytes
    return truncated


def hash_password(password: str) -> str:
    """
    Hash a password using bcrypt directly (bypassing passlib to avoid version issues).
    Bcrypt has a 72-byte limit, so we truncate if necessary.
    
    Args:
        password: Plain text password
        
    Returns:
        Hashed password string (bcrypt format)
    """
    password_bytes = _truncate_password(password)
    # Generate salt and hash password
    salt = bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
    hashed = bcrypt.hashpw(password_bytes, salt)
    # Return as string (bcrypt format starts with $2b$)
    return hashed.decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against a hash.
    Bcrypt has a 72-byte limit, so we truncate if necessary (same as in hash_password).
    
    Args:
        plain_password: Plain text password
        hashed_password: Hashed password to verify against
        
    Returns:
        True if password matches, False otherwise
    """
    password_bytes = _truncate_password(plain_password)
    hashed_bytes = hashed_password.encode('utf-8')
    return bcrypt.checkpw(password_bytes, hashed_bytes)


def validate_password_strength(password: str) -> tuple[bool, Optional[str]]:
    """
    Validate password meets strength requirements.
    
    Args:
        password: Password to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if len(password) < settings.PASSWORD_MIN_LENGTH:
        return False, f"Password must be at least {settings.PASSWORD_MIN_LENGTH} characters long"
    
    if settings.PASSWORD_REQUIRE_UPPERCASE and not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter"
    
    if settings.PASSWORD_REQUIRE_LOWERCASE and not re.search(r'[a-z]', password):
        return False, "Password must contain at least one lowercase letter"
    
    if settings.PASSWORD_REQUIRE_NUMBERS and not re.search(r'\d', password):
        return False, "Password must contain at least one number"
    
    if settings.PASSWORD_REQUIRE_SPECIAL and not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        return False, "Password must contain at least one special character"
    
    return True, None


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token.
    
    Args:
        data: Data to encode in the token (typically user_id, email, tenant_id)
        expires_delta: Optional expiration time delta. Defaults to ACCESS_TOKEN_EXPIRE_MINUTES
        
    Returns:
        Encoded JWT token string
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire, "type": "access"})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: dict) -> str:
    """
    Create a JWT refresh token.
    
    Args:
        data: Data to encode in the token (typically user_id)
        
    Returns:
        Encoded JWT token string
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def decode_token(token: str, token_type: str = "access") -> dict:
    """
    Decode and validate a JWT token.
    
    Args:
        token: JWT token string
        token_type: Expected token type ("access" or "refresh")
        
    Returns:
        Decoded token payload
        
    Raises:
        InvalidTokenError: If token is invalid or expired
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        
        # Verify token type
        if payload.get("type") != token_type:
            raise InvalidTokenError(f"Invalid token type. Expected {token_type}")
        
        return payload
    except JWTError as e:
        raise InvalidTokenError(f"Could not validate credentials: {str(e)}")


def generate_token_string(length: int = 32) -> str:
    """
    Generate a secure random token string.
    
    Used for password reset tokens, email verification tokens, etc.
    
    Args:
        length: Length of the token in bytes (will be hex encoded, so output length is 2x)
        
    Returns:
        Hex-encoded random token string
    """
    return secrets.token_urlsafe(length)


def hash_token(token: str) -> str:
    """
    Hash a token for secure storage (e.g., refresh tokens).
    
    Uses SHA-256 for fast, secure hashing of tokens before storing in database.
    
    Args:
        token: Plain token string to hash
        
    Returns:
        Hex-encoded hash of the token
    """
    import hashlib
    return hashlib.sha256(token.encode('utf-8')).hexdigest()

