"""
Chatbot service for managing chatbot registry.
"""
from typing import Optional, List
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.domains.chatbots.models import Chatbot
from app.domains.subscriptions.services.subscription_service import SubscriptionService
from app.domains.subscriptions.services.credit_service import CreditService

logger = get_logger(__name__)


class ChatbotService:
    """Service for managing chatbot registry."""

    def __init__(self, db: Session):
        self.db = db
        self.subscription_service = SubscriptionService(db)
        self.credit_service = CreditService(db)

    def get_chatbot_by_slug(self, slug: str) -> Optional[Chatbot]:
        """Get chatbot by slug."""
        return self.db.query(Chatbot).filter(Chatbot.slug == slug, Chatbot.is_active == True).first()

    def list_chatbots(self, user_id: Optional[UUID] = None, include_inactive: bool = False) -> List[Chatbot]:
        """List all chatbots, optionally filtered by user's subscription tier."""
        query = self.db.query(Chatbot)

        if not include_inactive:
            query = query.filter(Chatbot.is_active == True)

        if user_id:
            tier = self.subscription_service.get_user_tier(user_id)
            if tier.value == "free":
                # Free subscription: show premium catalog only when user can spend credits
                # (access-code credits do not upgrade DB tier; usage is still gated per request).
                credit_check = self.credit_service.check_balance(user_id)
                if not credit_check.allowed:
                    query = query.filter(Chatbot.access_level == "free")

        return query.order_by(Chatbot.category, Chatbot.name).all()

    def create_chatbot(
        self,
        slug: str,
        name: str,
        description: Optional[str] = None,
        category: Optional[str] = None,
        subject: Optional[str] = None,
        access_level: str = "free",
        system_prompt: Optional[str] = None,
    ) -> Chatbot:
        """Create a new chatbot."""
        chatbot = Chatbot(
            slug=slug,
            name=name,
            description=description,
            category=category,
            subject=subject,
            access_level=access_level,
            system_prompt=system_prompt,
        )
        self.db.add(chatbot)
        self.db.commit()
        self.db.refresh(chatbot)
        return chatbot
