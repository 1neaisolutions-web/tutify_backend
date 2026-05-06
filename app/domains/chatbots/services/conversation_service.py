"""
Conversation service for managing chatbot conversations.
"""
from typing import Optional, List, Tuple
from uuid import UUID
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from sqlalchemy import and_, desc, tuple_

from app.core.logging import get_logger
from app.domains.chatbots.models import (
    Chatbot,
    ChatbotConversation,
    ChatbotMessage,
)

logger = get_logger(__name__)


class ConversationService:
    """Service for managing chatbot conversations."""

    def __init__(self, db: Session):
        self.db = db

    def get_conversation(self, conversation_id: UUID, user_id: UUID) -> Optional[ChatbotConversation]:
        """Get conversation by ID (ensuring user owns it)."""
        return self.db.query(ChatbotConversation).filter(
            and_(
                ChatbotConversation.id == conversation_id,
                ChatbotConversation.user_id == user_id,
            )
        ).first()

    def list_conversations(
        self,
        user_id: UUID,
        chatbot_id: Optional[UUID] = None,
        limit: int = 50,
    ) -> List[ChatbotConversation]:
        """List user's conversations, optionally filtered by chatbot."""
        query = self.db.query(ChatbotConversation).filter(
            ChatbotConversation.user_id == user_id
        )

        if chatbot_id:
            query = query.filter(ChatbotConversation.chatbot_id == chatbot_id)

        return query.order_by(desc(ChatbotConversation.updated_at)).limit(limit).all()

    def create_conversation(
        self,
        chatbot_id: UUID,
        user_id: UUID,
        tenant_id: Optional[UUID] = None,
        title: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> ChatbotConversation:
        """Create a new conversation."""
        conversation = ChatbotConversation(
            chatbot_id=chatbot_id,
            user_id=user_id,
            tenant_id=tenant_id,
            title=title or "New Conversation",
            conversation_metadata=metadata or {},
        )
        self.db.add(conversation)
        self.db.commit()
        self.db.refresh(conversation)
        return conversation

    def update_conversation(
        self,
        conversation_id: UUID,
        user_id: UUID,
        title: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> Optional[ChatbotConversation]:
        """Update conversation (title, metadata)."""
        conversation = self.get_conversation(conversation_id, user_id)
        if not conversation:
            return None

        if title is not None:
            conversation.title = title
        if metadata is not None:
            conversation.conversation_metadata = metadata or {}
        conversation.updated_at = datetime.now(timezone.utc)

        self.db.commit()
        self.db.refresh(conversation)
        return conversation

    def delete_conversation(
        self,
        conversation_id: UUID,
        user_id: UUID,
    ) -> bool:
        """Delete a conversation."""
        conversation = self.get_conversation(conversation_id, user_id)
        if not conversation:
            return False

        self.db.delete(conversation)
        self.db.commit()
        return True

    def generate_conversation_title(self, first_message: str) -> str:
        """Generate conversation title from first message."""
        if not first_message:
            return "New Conversation"

        words = first_message.split()[:6]
        title = " ".join(words)
        return title[:50] + "..." if len(title) > 50 else title

    def list_messages(
        self,
        conversation_id: UUID,
        user_id: UUID,
        *,
        limit: int = 50,
        before_cursor: Optional[str] = None,
    ) -> Tuple[List[ChatbotMessage], bool, Optional[str]]:
        """
        Paginate messages newest-first: returns up to `limit` messages older than `before_cursor`.

        Cursor format: "{iso8601}|{message_uuid}" (oldest message boundary for next "load older" page).
        """
        conv = self.get_conversation(conversation_id, user_id)
        if not conv:
            return [], False, None

        lim = max(1, min(limit, 200))

        before_ts: Optional[datetime] = None
        before_id: Optional[UUID] = None
        if before_cursor:
            if "|" in before_cursor:
                ts_part, id_part = before_cursor.split("|", 1)
                try:
                    before_ts = datetime.fromisoformat(ts_part.replace("Z", "+00:00"))
                    before_id = UUID(id_part.strip())
                except (ValueError, AttributeError):
                    before_ts, before_id = None, None
            else:
                try:
                    mid = UUID(before_cursor.strip())
                    msg = (
                        self.db.query(ChatbotMessage)
                        .filter(
                            ChatbotMessage.id == mid,
                            ChatbotMessage.conversation_id == conversation_id,
                        )
                        .first()
                    )
                    if msg:
                        before_ts = msg.created_at
                        before_id = msg.id
                except ValueError:
                    pass

        q = self.db.query(ChatbotMessage).filter(ChatbotMessage.conversation_id == conversation_id)

        if before_ts is not None and before_id is not None:
            q = q.filter(
                tuple_(ChatbotMessage.created_at, ChatbotMessage.id)
                < tuple_(before_ts, before_id)
            )

        q = q.order_by(desc(ChatbotMessage.created_at), desc(ChatbotMessage.id))

        batch = q.limit(lim + 1).all()
        has_more = len(batch) > lim
        batch = batch[:lim]

        # Chronological order for clients (oldest → newest within this page)
        batch_chrono = list(reversed(batch))

        next_before: Optional[str] = None
        if batch:
            oldest = batch[-1]  # smallest created_at in this page (we fetched desc)
            next_before = f"{oldest.created_at.isoformat()}|{oldest.id}"
        if not has_more:
            next_before = None

        return batch_chrono, has_more, next_before if has_more else None
