"""
Chatbot domain models.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional
from decimal import Decimal

from sqlalchemy import (
    Column, String, Text, Boolean, Integer, DateTime, ForeignKey, JSON,
    Index, UniqueConstraint, Numeric
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.db.base_class import Base
from app.domains.chatbots.enums import (
    ChatbotCategory,
    AccessLevel,
    CapabilityCategory,
    ProcessingMode,
    MessageRole,
)


class Chatbot(Base):
    """Chatbot registry model."""

    __tablename__ = "chatbots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(50), nullable=True)  # 'free', 'llm', 'subject'
    subject = Column(String(50), nullable=True)  # NULL for general, 'English', 'Mathematics', etc.
    access_level = Column(String(20), nullable=False, index=True)  # 'free', 'premium'

    # Model configuration (legacy - kept for backward compatibility)
    system_prompt = Column(Text, nullable=True)
    model_config = Column(JSONB, nullable=True)
    fallback_models = Column(JSONB, nullable=True)
    model_strategy = Column(String(50), default="primary_fallback", nullable=True)

    # Feature flags
    premium_features = Column(JSONB, nullable=True)

    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    # When True, conversations are hidden from global user_history UNION (e.g. General Teaching Assistant).
    exclude_from_history = Column(Boolean, default=False, nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    model_assignments = relationship("ChatbotModelAssignment", back_populates="chatbot", cascade="all, delete-orphan")
    capabilities = relationship("ChatbotCapability", back_populates="chatbot", cascade="all, delete-orphan")
    conversations = relationship("ChatbotConversation", back_populates="chatbot", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Chatbot(id={self.id}, slug={self.slug}, name={self.name})>"


class ChatbotModelAssignment(Base):
    """Model assignments for chatbots (many-to-many: chatbots ↔ models)."""

    __tablename__ = "chatbot_model_assignments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    chatbot_id = Column(UUID(as_uuid=True), ForeignKey("chatbots.id", ondelete="CASCADE"), nullable=False)
    provider = Column(String(50), nullable=False)  # 'openai', 'anthropic', 'google', etc.
    model_name = Column(String(100), nullable=False)  # 'gpt-4', 'claude-3.5-sonnet', etc.

    # Priority/ordering (lower = higher priority)
    priority = Column(Integer, nullable=False, default=0)

    # Model-specific config
    temperature = Column(Numeric(3, 2), nullable=True, default=Decimal("0.7"))
    max_tokens = Column(Integer, nullable=True, default=2000)
    top_p = Column(Numeric(3, 2), nullable=True)
    frequency_penalty = Column(Numeric(3, 2), nullable=True)
    presence_penalty = Column(Numeric(3, 2), nullable=True)

    # Usage limits per model (optional)
    max_tokens_per_request = Column(Integer, nullable=True)
    rate_limit_per_minute = Column(Integer, nullable=True)

    # Status
    is_primary = Column(Boolean, default=False, nullable=False)
    is_enabled = Column(Boolean, default=True, nullable=False)

    # Metadata
    assignment_metadata = Column("metadata", JSONB, nullable=True)  # Database column is 'metadata' to avoid reserved keyword

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    chatbot = relationship("Chatbot", back_populates="model_assignments")
    usage_logs = relationship("ChatbotModelUsage", back_populates="assignment")

    __table_args__ = (
        UniqueConstraint("chatbot_id", "provider", "model_name", name="uq_chatbot_provider_model"),
        Index("idx_chatbot_priority", "chatbot_id", "priority", "is_enabled"),
    )

    def __repr__(self) -> str:
        return f"<ChatbotModelAssignment(id={self.id}, chatbot_id={self.chatbot_id}, provider={self.provider}, model={self.model_name})>"


class ChatbotCapability(Base):
    """Chatbot capability definitions."""

    __tablename__ = "chatbot_capabilities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    chatbot_id = Column(UUID(as_uuid=True), ForeignKey("chatbots.id", ondelete="CASCADE"), nullable=False, index=True)

    # Capability definition
    capability_key = Column(String(100), nullable=False)  # 'text_complexity', 'guided_reading', etc.
    capability_name = Column(String(200), nullable=False)  # Display name
    capability_description = Column(Text, nullable=True)
    capability_category = Column(String(50), nullable=True)  # 'analysis', 'instruction', 'feedback', 'tracking'

    # UI/UX configuration
    icon_name = Column(String(50), nullable=True)  # Icon identifier for frontend
    display_order = Column(Integer, nullable=False, default=0)
    is_primary = Column(Boolean, default=False, nullable=False)  # Show prominently in header
    requires_input_type = Column(String(50), nullable=True)  # 'text', 'file', 'conversation', 'none'

    # Functionality configuration
    system_prompt_template = Column(Text, nullable=True)  # LLM prompt template for this capability
    output_schema = Column(JSONB, nullable=True)  # Expected response structure
    processing_mode = Column(String(50), default="structured", nullable=True)  # 'chat', 'structured', 'streaming', 'batch'

    # Metadata
    capability_metadata = Column("metadata", JSONB, nullable=True)  # Database column is 'metadata' to avoid reserved keyword

    # Status
    is_active = Column(Boolean, default=True, nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    chatbot = relationship("Chatbot", back_populates="capabilities")
    user_progress = relationship("UserCapabilityProgress", back_populates="capability", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("chatbot_id", "capability_key", name="uq_chatbot_capability"),
    )

    def __repr__(self) -> str:
        return f"<ChatbotCapability(id={self.id}, chatbot_id={self.chatbot_id}, capability_key={self.capability_key})>"


class ChatbotConversation(Base):
    """User conversations with chatbots."""

    __tablename__ = "chatbot_conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    chatbot_id = Column(UUID(as_uuid=True), ForeignKey("chatbots.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True)

    title = Column(String(200), nullable=True)
    conversation_metadata = Column("metadata", JSONB, nullable=True)  # Database column is 'metadata' to avoid reserved keyword

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    chatbot = relationship("Chatbot", back_populates="conversations")
    user = relationship("User", foreign_keys=[user_id])
    tenant = relationship("Tenant", foreign_keys=[tenant_id])
    messages = relationship("ChatbotMessage", back_populates="conversation", cascade="all, delete-orphan", order_by="ChatbotMessage.created_at")

    __table_args__ = (
        Index("idx_user_chatbot", "user_id", "chatbot_id"),
        Index("idx_user_updated", "user_id", "updated_at"),
    )

    def __repr__(self) -> str:
        return f"<ChatbotConversation(id={self.id}, chatbot_id={self.chatbot_id}, user_id={self.user_id})>"


class ChatbotMessage(Base):
    """Individual messages in chatbot conversations."""

    __tablename__ = "chatbot_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("chatbot_conversations.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(20), nullable=False)  # 'user', 'assistant', 'system'
    content = Column(Text, nullable=False)
    message_metadata = Column("metadata", JSONB, nullable=True)  # Database column is 'metadata' to avoid reserved keyword

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    conversation = relationship("ChatbotConversation", back_populates="messages")

    __table_args__ = (
        Index("idx_conversation", "conversation_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<ChatbotMessage(id={self.id}, conversation_id={self.conversation_id}, role={self.role})>"


class ChatbotModelUsage(Base):
    """Model usage tracking for analytics."""

    __tablename__ = "chatbot_model_usage"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    chatbot_id = Column(UUID(as_uuid=True), ForeignKey("chatbots.id", ondelete="CASCADE"), nullable=False)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("chatbot_conversations.id", ondelete="SET NULL"), nullable=True)
    assignment_id = Column(UUID(as_uuid=True), ForeignKey("chatbot_model_assignments.id", ondelete="SET NULL"), nullable=True)

    provider = Column(String(50), nullable=True)
    model_name = Column(String(100), nullable=True)
    tokens_used = Column(Integer, nullable=True)
    cost_estimate = Column(Numeric(10, 6), nullable=True)
    latency_ms = Column(Integer, nullable=True)
    success = Column(Boolean, default=True, nullable=False)
    error_message = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    chatbot = relationship("Chatbot")
    conversation = relationship("ChatbotConversation")
    assignment = relationship("ChatbotModelAssignment", back_populates="usage_logs")

    __table_args__ = (
        Index("idx_chatbot_usage", "chatbot_id", "created_at"),
        Index("idx_model_usage", "provider", "model_name", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<ChatbotModelUsage(id={self.id}, chatbot_id={self.chatbot_id}, provider={self.provider}, model={self.model_name})>"


class UserCapabilityProgress(Base):
    """Progress tracking per user per capability."""

    __tablename__ = "user_capability_progress"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    capability_id = Column(UUID(as_uuid=True), ForeignKey("chatbot_capabilities.id", ondelete="CASCADE"), nullable=False)

    # Usage statistics
    times_used = Column(Integer, nullable=False, default=0)
    last_used_at = Column(DateTime(timezone=True), nullable=True)

    # Mastery/achievement tracking
    mastery_level = Column(String(50), nullable=True)  # 'beginner', 'intermediate', 'advanced'
    achievements = Column(JSONB, nullable=True)  # Unlocked features/badges

    # Preferences
    preferred_settings = Column(JSONB, nullable=True)  # User's preferred defaults

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    capability = relationship("ChatbotCapability", back_populates="user_progress")

    __table_args__ = (
        UniqueConstraint("user_id", "capability_id", name="uq_user_capability"),
        Index("idx_user_capability", "user_id", "capability_id"),
    )

    def __repr__(self) -> str:
        return f"<UserCapabilityProgress(id={self.id}, user_id={self.user_id}, capability_id={self.capability_id})>"
