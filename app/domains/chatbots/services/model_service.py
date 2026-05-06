"""
Model service for managing chatbot model assignments.
"""
from typing import List, Optional, Dict, Any
from uuid import UUID
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.domains.chatbots.models import Chatbot, ChatbotModelAssignment

logger = get_logger(__name__)


class ChatbotModelService:
    """Service for managing chatbot model assignments dynamically."""

    def __init__(self, db: Session):
        self.db = db

    def get_chatbot_models(
        self,
        chatbot_id: UUID,
        include_disabled: bool = False,
    ) -> List[ChatbotModelAssignment]:
        """Get all model assignments for a chatbot, ordered by priority."""
        query = self.db.query(ChatbotModelAssignment).filter(
            ChatbotModelAssignment.chatbot_id == chatbot_id
        )

        if not include_disabled:
            query = query.filter(ChatbotModelAssignment.is_enabled == True)

        return query.order_by(
            ChatbotModelAssignment.is_primary.desc(),
            ChatbotModelAssignment.priority.asc(),
        ).all()

    def assign_model_to_chatbot(
        self,
        chatbot_id: UUID,
        provider: str,
        model_name: str,
        priority: int = 0,
        is_primary: bool = False,
        temperature: Optional[Decimal] = None,
        max_tokens: Optional[int] = None,
        **model_config,
    ) -> ChatbotModelAssignment:
        """Assign a model to a chatbot (add new model)."""
        # If setting as primary, unset other primaries
        if is_primary:
            self.db.query(ChatbotModelAssignment).filter(
                ChatbotModelAssignment.chatbot_id == chatbot_id,
                ChatbotModelAssignment.is_primary == True,
            ).update({"is_primary": False})

        assignment = ChatbotModelAssignment(
            chatbot_id=chatbot_id,
            provider=provider,
            model_name=model_name,
            priority=priority,
            is_primary=is_primary,
            temperature=temperature or Decimal("0.7"),
            max_tokens=max_tokens or 2000,
            **model_config,
        )

        self.db.add(assignment)
        self.db.commit()
        self.db.refresh(assignment)

        return assignment

    def update_model_assignment(
        self,
        assignment_id: UUID,
        **updates,
    ) -> ChatbotModelAssignment:
        """Update model assignment (change priority, config, enable/disable)."""
        assignment = self.db.query(ChatbotModelAssignment).filter(
            ChatbotModelAssignment.id == assignment_id
        ).first()

        if not assignment:
            raise ValueError("Model assignment not found")

        # Handle primary flag change
        if updates.get("is_primary") and not assignment.is_primary:
            self.db.query(ChatbotModelAssignment).filter(
                ChatbotModelAssignment.chatbot_id == assignment.chatbot_id,
                ChatbotModelAssignment.is_primary == True,
            ).update({"is_primary": False})

        # Update fields
        for key, value in updates.items():
            if hasattr(assignment, key):
                setattr(assignment, key, value)

        self.db.commit()
        self.db.refresh(assignment)

        return assignment

    def remove_model_from_chatbot(
        self,
        assignment_id: UUID,
        soft_delete: bool = True,
    ):
        """Remove model from chatbot (soft delete by default)."""
        if soft_delete:
            # Disable instead of delete
            self.update_model_assignment(assignment_id, is_enabled=False)
        else:
            # Hard delete
            assignment = self.db.query(ChatbotModelAssignment).filter(
                ChatbotModelAssignment.id == assignment_id
            ).first()
            if assignment:
                self.db.delete(assignment)
                self.db.commit()

    def get_model_config_for_chatbot(
        self,
        chatbot_id: UUID,
    ) -> Optional[Dict[str, Any]]:
        """Get primary model config for chatbot (for LLM routing)."""
        assignments = self.get_chatbot_models(chatbot_id)

        if not assignments:
            return None

        # Get primary or first enabled
        primary = next((a for a in assignments if a.is_primary), None)
        assignment = primary or assignments[0]

        return {
            "provider": assignment.provider,
            "model": assignment.model_name,
            "temperature": float(assignment.temperature) if assignment.temperature else 0.7,
            "max_tokens": assignment.max_tokens or 2000,
            "top_p": float(assignment.top_p) if assignment.top_p else None,
            "frequency_penalty": float(assignment.frequency_penalty) if assignment.frequency_penalty else None,
            "presence_penalty": float(assignment.presence_penalty) if assignment.presence_penalty else None,
        }

    def get_fallback_chain(
        self,
        chatbot_id: UUID,
    ) -> List[Dict[str, Any]]:
        """Get fallback chain for chatbot (primary + fallbacks)."""
        assignments = self.get_chatbot_models(chatbot_id)

        return [
            {
                "provider": a.provider,
                "model": a.model_name,
                "temperature": float(a.temperature) if a.temperature else 0.7,
                "max_tokens": a.max_tokens or 2000,
            }
            for a in assignments
        ]
