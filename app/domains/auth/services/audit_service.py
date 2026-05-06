"""
Audit service for logging authentication and authorization events.
"""
from typing import Optional
from sqlalchemy.orm import Session
from app.core.logging import get_logger
from app.domains.auth.models import AuditEventType

logger = get_logger(__name__)


class AuditService:
    """Service for logging audit events."""
    
    def __init__(self, db: Optional[Session] = None):
        """Initialize audit service."""
        self.db = db
        logger.debug("AuditService initialized")
    
    def create(
        self,
        event_type: AuditEventType,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        details: Optional[dict] = None,
        db: Optional[Session] = None,
    ) -> None:
        """
        Create an audit log entry.
        
        Args:
            event_type: Type of audit event
            user_id: ID of user who triggered the event
            tenant_id: ID of tenant associated with the event
            details: Additional event details
            db: Database session (optional, uses self.db if not provided)
        """
        db_session = db or self.db
        if not db_session:
            # If no DB session available, just log to application log
            logger.info(
                f"Audit event: {event_type.value if hasattr(event_type, 'value') else event_type} "
                f"(user_id={user_id}, tenant_id={tenant_id}, details={details})"
            )
            return
        
        try:
            # TODO: Implement actual audit log table/model if needed
            # For now, just log to application logger
            logger.info(
                f"Audit event: {event_type.value if hasattr(event_type, 'value') else event_type} "
                f"(user_id={user_id}, tenant_id={tenant_id}, details={details})"
            )
        except Exception as e:
            logger.error(f"Error creating audit log: {e}")
    
    def log(
        self,
        event_type: AuditEventType,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        details: Optional[dict] = None,
        db: Optional[Session] = None,
    ) -> None:
        """Alias for create method."""
        self.create(event_type, user_id, tenant_id, details, db)
