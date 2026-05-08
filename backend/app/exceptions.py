"""
Custom exception classes for PulseQ API.

Provides typed exception classes that support error_code for standardized error handling.
"""

from fastapi import HTTPException, status
from typing import Any, Dict, Optional


class PulseQException(HTTPException):
    """Base exception class for PulseQ API with error_code support.
    
    Extends HTTPException to include an error_code field for frontend consumption.
    
    Example:
        raise PulseQException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor not found",
            error_code="NOT_FOUND"
        )
    """
    
    def __init__(
        self,
        status_code: int,
        detail: str,
        error_code: str,
        headers: Optional[Dict[str, str]] = None,
    ):
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        self.error_code = error_code


class ValidationError(PulseQException):
    """Raised when input validation fails (422 Unprocessable Entity)."""
    
    def __init__(self, detail: str, error_code: str = "VALIDATION_ERROR"):
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=detail,
            error_code=error_code,
        )


class InvalidInput(ValidationError):
    """Raised when input is malformed or invalid (422 Unprocessable Entity)."""
    
    def __init__(self, detail: str, error_code: str = "INVALID_INPUT"):
        super().__init__(detail=detail, error_code=error_code)


class BadRequest(PulseQException):
    """Raised for bad requests (400 Bad Request)."""
    
    def __init__(self, detail: str, error_code: str = "BAD_REQUEST"):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
            error_code=error_code,
        )


class OperationFailed(BadRequest):
    """Raised when a business operation fails (400 Bad Request)."""
    
    def __init__(self, detail: str, error_code: str = "OPERATION_FAILED"):
        super().__init__(detail=detail, error_code=error_code)


class InvalidState(BadRequest):
    """Raised when operation conflicts with current state (400 Bad Request)."""
    
    def __init__(self, detail: str, error_code: str = "INVALID_STATE"):
        super().__init__(detail=detail, error_code=error_code)


class Unauthorized(PulseQException):
    """Raised when authentication fails (401 Unauthorized)."""
    
    def __init__(self, detail: str, error_code: str = "UNAUTHORIZED"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            error_code=error_code,
        )


class InvalidCredentials(Unauthorized):
    """Raised when credentials are invalid (401 Unauthorized)."""
    
    def __init__(self, detail: str = "Invalid credentials", error_code: str = "INVALID_CREDENTIALS"):
        super().__init__(detail=detail, error_code=error_code)


class TokenExpired(Unauthorized):
    """Raised when authentication token has expired (401 Unauthorized)."""
    
    def __init__(self, detail: str = "Token expired", error_code: str = "TOKEN_EXPIRED"):
        super().__init__(detail=detail, error_code=error_code)


class Forbidden(PulseQException):
    """Raised when user lacks required permissions (403 Forbidden)."""
    
    def __init__(self, detail: str, error_code: str = "FORBIDDEN"):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
            error_code=error_code,
        )


class InsufficientPermissions(Forbidden):
    """Raised when user has insufficient permissions (403 Forbidden)."""
    
    def __init__(self, detail: str = "Insufficient permissions", error_code: str = "INSUFFICIENT_PERMISSIONS"):
        super().__init__(detail=detail, error_code=error_code)


class NotFound(PulseQException):
    """Raised when a resource is not found (404 Not Found)."""
    
    def __init__(self, detail: str, error_code: str = "NOT_FOUND"):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail,
            error_code=error_code,
        )


class ResourceNotFound(NotFound):
    """Raised when a specific resource is not found (404 Not Found)."""
    
    def __init__(self, resource: str, error_code: str = "RESOURCE_NOT_FOUND"):
        detail = f"{resource} not found"
        super().__init__(detail=detail, error_code=error_code)


class Conflict(PulseQException):
    """Raised when request conflicts with current state (409 Conflict)."""
    
    def __init__(self, detail: str, error_code: str = "CONFLICT"):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
            error_code=error_code,
        )


class AlreadyExists(Conflict):
    """Raised when resource already exists (409 Conflict)."""
    
    def __init__(self, detail: str, error_code: str = "ALREADY_EXISTS"):
        super().__init__(detail=detail, error_code=error_code)


class TooManyRequests(PulseQException):
    """Raised when rate limit is exceeded (429 Too Many Requests)."""
    
    def __init__(self, detail: str, error_code: str = "RATE_LIMIT_EXCEEDED"):
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail,
            error_code=error_code,
        )


class QuotaExceeded(TooManyRequests):
    """Raised when quota is exceeded (429 Too Many Requests)."""
    
    def __init__(self, detail: str, error_code: str = "QUOTA_EXCEEDED"):
        super().__init__(detail=detail, error_code=error_code)


class InternalServerError(PulseQException):
    """Raised for internal server errors (500 Internal Server Error)."""
    
    def __init__(self, detail: str, error_code: str = "INTERNAL_SERVER_ERROR"):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail,
            error_code=error_code,
        )


class DatabaseError(InternalServerError):
    """Raised for database-related errors (500 Internal Server Error)."""
    
    def __init__(self, detail: str = "Database error occurred", error_code: str = "DATABASE_ERROR"):
        super().__init__(detail=detail, error_code=error_code)


class ServiceUnavailable(PulseQException):
    """Raised when service is temporarily unavailable (503 Service Unavailable)."""
    
    def __init__(self, detail: str, error_code: str = "SERVICE_UNAVAILABLE"):
        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=detail,
            error_code=error_code,
        )
