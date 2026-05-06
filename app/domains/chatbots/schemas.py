"""
Pydantic schemas for chatbot domain.
"""
from typing import Optional, Dict, Any, List
from datetime import datetime
from uuid import UUID
from decimal import Decimal
from pydantic import BaseModel, Field, ConfigDict


# Chatbot schemas
class ChatbotListItem(BaseModel):
    """Chatbot list item response."""

    id: UUID
    slug: str
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    subject: Optional[str] = None
    access_level: str
    is_active: bool = True

    model_config = ConfigDict(from_attributes=True)


class ChatbotDetail(BaseModel):
    """Chatbot detail response."""

    id: UUID
    slug: str
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    subject: Optional[str] = None
    access_level: str
    system_prompt: Optional[str] = None
    premium_features: Optional[Dict[str, Any]] = None
    is_active: bool = True
    capabilities: List["CapabilityResponse"] = []

    model_config = ConfigDict(from_attributes=True)


class ModelAssignmentResponse(BaseModel):
    """Model assignment response."""

    id: UUID
    provider: str
    model_name: str
    priority: int
    temperature: Optional[Decimal] = None
    max_tokens: Optional[int] = None
    is_primary: bool = False
    is_enabled: bool = True

    model_config = ConfigDict(from_attributes=True)


class CapabilityResponse(BaseModel):
    """Capability response."""

    id: UUID
    capability_key: str
    capability_name: str
    capability_description: Optional[str] = None
    capability_category: Optional[str] = None
    icon_name: Optional[str] = None
    display_order: int
    is_primary: bool = False
    requires_input_type: Optional[str] = None
    output_schema: Optional[Dict[str, Any]] = None
    processing_mode: str = "structured"

    model_config = ConfigDict(from_attributes=True)


# Conversation schemas
class ConversationListItem(BaseModel):
    """Conversation list item response."""

    id: UUID
    chatbot_id: UUID
    chatbot_slug: Optional[str] = None
    chatbot_name: Optional[str] = None
    title: Optional[str] = None
    message_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConversationDetail(BaseModel):
    """Conversation detail with messages."""

    id: UUID
    chatbot_id: UUID
    chatbot_slug: Optional[str] = None
    chatbot_name: Optional[str] = None
    title: Optional[str] = None
    messages: List["MessageResponse"] = []
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MessageResponse(BaseModel):
    """Message response."""

    id: UUID
    role: str
    content: str
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MessagesPage(BaseModel):
    """Paginated slice of messages (newest page first; use `before` cursor to load older)."""

    items: List[MessageResponse] = []
    has_more: bool = False
    next_before: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# Request schemas
class SendMessageRequest(BaseModel):
    """Request to send a message to a chatbot."""

    message: str = Field(..., min_length=1, max_length=10000)
    conversation_id: Optional[str] = None  # Can be UUID string or None
    bot_mode: Optional[str] = Field(None, description="fastest, smartest, critical-thinking")
    response_length: Optional[str] = Field(None, description="short, medium, long")
    web_search: bool = Field(False, description="Enable web search (premium feature)")
    metadata: Optional[Dict[str, Any]] = None
    
    def get_conversation_id_as_uuid(self) -> Optional[UUID]:
        """Convert conversation_id string to UUID if valid, else None."""
        if not self.conversation_id:
            return None
        try:
            # Try to convert string to UUID
            return UUID(str(self.conversation_id))
        except (ValueError, AttributeError):
            # If not a valid UUID, return None (will create new conversation)
            return None


class SendMessageResponse(BaseModel):
    """Response from sending a message."""

    conversation_id: UUID
    user_message: MessageResponse
    assistant_message: MessageResponse
    token_usage: Optional[Dict[str, int]] = None
    cost_estimate: Optional[Decimal] = None
    model_used: Optional[str] = None
    provider_used: Optional[str] = None


class ExecuteCapabilityRequest(BaseModel):
    """Request to execute a capability."""

    input: str = Field(..., min_length=1)
    input_type: Optional[str] = Field("text", description="text, file, conversation")
    parameters: Optional[Dict[str, Any]] = None
    conversation_id: Optional[UUID] = None
    save_result: bool = Field(True, description="Store in progress tracking")


class ExecuteCapabilityResponse(BaseModel):
    """Response from executing a capability."""

    result: Dict[str, Any]
    metadata: Optional[Dict[str, Any]] = None
    usage_id: Optional[UUID] = None
    progress_update: Optional[Dict[str, Any]] = None
    conversation_id: Optional[UUID] = None


class HistoryLogRequest(BaseModel):
    """Client-side logging for non-chat specialized tools (stores as a chatbot conversation)."""

    title: Optional[str] = Field(None, max_length=200)
    user_content: str = Field(..., min_length=1, max_length=10000)
    assistant_content: str = Field(..., min_length=1, max_length=50000)
    metadata: Optional[Dict[str, Any]] = None
    conversation_id: Optional[UUID] = None


class HistoryLogResponse(BaseModel):
    conversation_id: UUID


# Update forward references
ChatbotDetail.model_rebuild()
ConversationDetail.model_rebuild()
