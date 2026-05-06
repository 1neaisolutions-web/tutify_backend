"""
TemplateFavorite model for tracking user favorites.
Designed to work without auth (session-based) but easily attachable to user accounts.
"""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.db.base_class import Base


class TemplateFavorite(Base):
    """TemplateFavorite model for tracking favorite templates.
    
    Works without authentication using session_id, but user_id is available
    for future authentication integration.
    """

    __tablename__ = "template_favorites"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    template_id = Column(UUID(as_uuid=True), ForeignKey("templates.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), nullable=True, index=True)  # For future auth
    session_id = Column(String(255), nullable=True, index=True)  # For session-based favorites (no auth)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Unique constraint: one favorite per template per user/session
    __table_args__ = (
        UniqueConstraint("template_id", "user_id", name="uq_template_favorite_user"),
        UniqueConstraint("template_id", "session_id", name="uq_template_favorite_session"),
        {"comment": "Template favorites. Can be user-based (with auth) or session-based (without auth)."},
    )

    def __repr__(self) -> str:
        return f"<TemplateFavorite(id={self.id}, template_id={self.template_id}, user_id={self.user_id}, session_id={self.session_id})>"

