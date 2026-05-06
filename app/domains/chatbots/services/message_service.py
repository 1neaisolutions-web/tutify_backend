"""
Message service for handling chatbot messages and LLM integration.
"""
from typing import Optional, Dict, Any, AsyncIterator
import re
import asyncio
from uuid import UUID
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.llm.router import ModelRouter
from app.llm.cache import ResponseCache
from app.llm.rate_limiter import RateLimiter
from app.llm.cost_tracker import CostTracker
from app.llm.config import llm_settings
from app.llm.schemas import LLMResponse
from app.domains.chatbots.models import (
    Chatbot,
    ChatbotConversation,
    ChatbotMessage,
    ChatbotModelUsage,
)
from app.domains.chatbots.services.model_service import ChatbotModelService
from app.domains.chatbots.services.conversation_service import ConversationService
from app.domains.subscriptions.services.quota_service import QuotaService
from app.domains.subscriptions.services.credit_service import CreditService

logger = get_logger(__name__)


class MessageService:
    """Service for handling chatbot messages and LLM integration."""

    def __init__(self, db: Session):
        self.db = db
        self.model_service = ChatbotModelService(db)
        self.conversation_service = ConversationService(db)
        self.quota_service = QuotaService(db)
        self.credit_service = CreditService(db)
        
        # Initialize LLM infrastructure (reuse existing components)
        self.cache = ResponseCache(
            ttl_seconds=llm_settings.CACHE_TTL_SECONDS,
            redis_url=llm_settings.REDIS_URL
        ) if llm_settings.CACHE_ENABLED else None
        
        self.rate_limiter = RateLimiter(llm_settings) if llm_settings.RATE_LIMIT_ENABLED else None
        self.cost_tracker = CostTracker() if llm_settings.COST_TRACKING_ENABLED else None
        
        self.model_router = ModelRouter(
            config=llm_settings,
            cache=self.cache,
            rate_limiter=self.rate_limiter,
            cost_tracker=self.cost_tracker,
        )

    async def send_message(
        self,
        chatbot_id: UUID,
        user_id: UUID,
        message: str,
        conversation_id: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Send a message to a chatbot and get response."""
        # 1. Get chatbot
        chatbot = self.db.query(Chatbot).filter(Chatbot.id == chatbot_id).first()
        if not chatbot:
            raise ValueError("Chatbot not found")

        # 2. Get or create conversation
        if conversation_id:
            conversation = self.conversation_service.get_conversation(conversation_id, user_id)
            if not conversation:
                raise ValueError("Conversation not found")
        else:
            # Create new conversation
            title = self.conversation_service.generate_conversation_title(message)
            conversation = self.conversation_service.create_conversation(
                chatbot_id=chatbot_id,
                user_id=user_id,
                tenant_id=tenant_id,
                title=title,
                metadata=metadata or {},  # This is passed to conversation_service, which will use conversation_metadata
            )

        # 3. Check credit balance before processing
        credit_check = self.credit_service.check_balance(user_id)
        if not credit_check.allowed:
            raise ValueError(credit_check.reason or "Insufficient credits")

        # 4. Save user message
        user_message = ChatbotMessage(
            conversation_id=conversation.id,
            role="user",
            content=message,
            message_metadata=metadata or {},
        )
        self.db.add(user_message)
        self.db.flush()

        # 5. Get chatbot's model config
        model_config = self.model_service.get_model_config_for_chatbot(chatbot_id)
        if not model_config:
            raise ValueError("No models assigned to chatbot")

        # 6. Build system prompt
        system_prompt = chatbot.system_prompt or "You are a helpful teaching assistant."

        # 7. Get conversation history for context
        previous_messages = self.db.query(ChatbotMessage).filter(
            ChatbotMessage.conversation_id == conversation.id
        ).order_by(ChatbotMessage.created_at).all()

        # Build context from previous messages
        context = "\n".join([
            f"{msg.role}: {msg.content}"
            for msg in previous_messages[-10:]  # Last 10 messages for context
        ])

        full_prompt = context + f"\nuser: {message}" if context else message

        # 8. Generate response using ModelRouter
        try:
            llm_response: LLMResponse = await self.model_router.generate(
                system_message=system_prompt,
                prompt=full_prompt,
                model_config=model_config,
            )

            # 9. Save assistant message
            assistant_message = ChatbotMessage(
                conversation_id=conversation.id,
                role="assistant",
                content=llm_response.content,
                message_metadata={
                    "model_used": llm_response.model_used,
                    "provider": llm_response.provider,
                    "token_usage": {
                        "prompt": llm_response.token_usage.prompt if llm_response.token_usage else 0,
                        "completion": llm_response.token_usage.completion if llm_response.token_usage else 0,
                        "total": llm_response.token_usage.total if llm_response.token_usage else 0,
                    } if llm_response.token_usage else None,
                    "cost_estimate": float(llm_response.cost_estimate) if llm_response.cost_estimate else None,
                    "latency_ms": llm_response.latency_ms,
                    "cache_hit": llm_response.cache_hit,
                },
            )
            self.db.add(assistant_message)

            # 10. Log model usage
            usage_log = ChatbotModelUsage(
                chatbot_id=chatbot_id,
                conversation_id=conversation.id,
                provider=llm_response.provider,
                model_name=llm_response.model_used,
                tokens_used=llm_response.token_usage.total if llm_response.token_usage else 0,
                cost_estimate=llm_response.cost_estimate,
                latency_ms=llm_response.latency_ms,
                success=True,
            )
            self.db.add(usage_log)

            # 11. Update conversation timestamp
            conversation.updated_at = datetime.now(timezone.utc)

            # 12. Commit main transaction first (messages, conversation, usage log)
            self.db.commit()
            self.db.refresh(user_message)
            self.db.refresh(assistant_message)

            # 13. Deduct credits (non-blocking — never fails the main operation)
            self.credit_service.charge(
                user_id=user_id,
                feature_key="chatbot_message",
                llm_response=llm_response,
                description=f"AI Chat · {chatbot.name}",
            )
            self.db.refresh(user_message)
            self.db.refresh(assistant_message)

            return {
                "conversation_id": conversation.id,
                "user_message": user_message,
                "assistant_message": assistant_message,
                "token_usage": {
                    "prompt": llm_response.token_usage.prompt if llm_response.token_usage else 0,
                    "completion": llm_response.token_usage.completion if llm_response.token_usage else 0,
                    "total": llm_response.token_usage.total if llm_response.token_usage else 0,
                } if llm_response.token_usage else None,
                "cost_estimate": llm_response.cost_estimate,
                "model_used": llm_response.model_used,
                "provider_used": llm_response.provider,
            }

        except Exception as e:
            logger.error(f"Error generating message: {e}", exc_info=True)
            # Log failure
            usage_log = ChatbotModelUsage(
                chatbot_id=chatbot_id,
                conversation_id=conversation.id,
                success=False,
                error_message=str(e),
            )
            self.db.add(usage_log)
            self.db.commit()
            raise

    async def stream_message(
        self,
        chatbot_id: UUID,
        user_id: UUID,
        message: str,
        conversation_id: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Stream response from chatbot (SSE format)."""
        import json
        
        # 1. Get chatbot
        chatbot = self.db.query(Chatbot).filter(Chatbot.id == chatbot_id).first()
        if not chatbot:
            yield {"type": "error", "data": {"detail": "Chatbot not found"}}
            return

        # 2. Get or create conversation (FAST - use placeholder title, generate async later)
        if conversation_id:
            conversation = self.conversation_service.get_conversation(conversation_id, user_id)
            if not conversation:
                yield {"type": "error", "data": {"detail": "Conversation not found"}}
                return
        else:
            # Create new conversation with placeholder title (don't wait for LLM title generation)
            placeholder_title = message[:50] + "..." if len(message) > 50 else message
            conversation = self.conversation_service.create_conversation(
                chatbot_id=chatbot_id,
                user_id=user_id,
                tenant_id=tenant_id,
                title=placeholder_title,  # Use placeholder, generate proper title async later
                metadata=metadata or {},
            )

        # 3. Get chatbot's model config FIRST (needed for streaming)
        model_config = self.model_service.get_model_config_for_chatbot(chatbot_id)
        if not model_config:
            yield {"type": "error", "data": {"detail": "No models assigned to chatbot"}}
            return

        # 4. Build system prompt
        system_prompt = chatbot.system_prompt or "You are a helpful teaching assistant."

        # 5. Get conversation history FAST (optimized query - only last 10, limit before fetch)
        previous_messages = self.db.query(ChatbotMessage).filter(
            ChatbotMessage.conversation_id == conversation.id
        ).order_by(ChatbotMessage.created_at.desc()).limit(10).all()
        previous_messages.reverse()  # Reverse to chronological order

        # Build context from previous messages
        context = "\n".join([
            f"{msg.role}: {msg.content}"
            for msg in previous_messages
        ])

        full_prompt = context + f"\nuser: {message}" if context else message

        # 6. Save user message (non-blocking - don't flush yet, let streaming start)
        user_message = ChatbotMessage(
            conversation_id=conversation.id,
            role="user",
            content=message,
            message_metadata=metadata or {},
        )
        self.db.add(user_message)
        # Don't flush - start streaming immediately

        # 7. Check credit balance before streaming
        credit_check = self.credit_service.check_balance(user_id)
        if not credit_check.allowed:
            yield {
                "type": "error",
                "data": {
                    "detail": "You don't have enough credits to continue.",
                    "error_code": "insufficient_credits",
                    "balance": credit_check.balance,
                },
            }
            return

        # 8. Start streaming IMMEDIATELY (don't wait for DB operations)
        assistant_content = ""
        chunk_count = 0
        try:
            # Start streaming IMMEDIATELY - yield first chunk as fast as possible
            async for chunk in self.model_router.stream(
                system_message=system_prompt,
                prompt=full_prompt,
                model_config=model_config,
            ):
                if chunk:
                    # CRITICAL: Yield chunks as-is from provider (they already include spaces)
                    # The provider (OpenAI) sends word-by-word chunks with proper spacing
                    # Don't re-split - this can lose spaces and cause concatenated text
                    assistant_content += chunk
                    chunk_count += 1
                    yield {"type": "content", "content": chunk}
                    # Let the event loop flush each chunk immediately for word-by-word display
                    await asyncio.sleep(0)
            
            # 9. Flush user message and save assistant message after streaming completes
            self.db.flush()  # Now flush user message (non-blocking during streaming)
            assistant_message = ChatbotMessage(
                conversation_id=conversation.id,
                role="assistant",
                content=assistant_content,
                message_metadata={
                    "model_used": model_config.get("model_name", "unknown"),
                    "provider": model_config.get("provider", "unknown"),
                },
            )
            self.db.add(assistant_message)

            # 11. Update conversation timestamp
            conversation.updated_at = datetime.now(timezone.utc)

            # 12. Commit transaction
            self.db.commit()
            self.db.refresh(user_message)
            self.db.refresh(assistant_message)

            # 13. Deduct credits after streaming completes (non-blocking)
            self.credit_service.charge(
                user_id=user_id,
                feature_key="chatbot_message",
                description=f"AI Chat · {chatbot.name}",
            )

            # 14. Yield final response with metadata
            yield {
                "type": "done",
                "data": {
                    "conversation_id": str(conversation.id),
                    "user_message": {
                        "id": str(user_message.id),
                        "role": user_message.role,
                        "content": user_message.content,
                        "created_at": user_message.created_at.isoformat(),
                    },
                    "assistant_message": {
                        "id": str(assistant_message.id),
                        "role": assistant_message.role,
                        "content": assistant_message.content,
                        "created_at": assistant_message.created_at.isoformat(),
                    },
                }
            }

        except Exception as e:
            logger.error(f"Error streaming message: {e}", exc_info=True)
            yield {"type": "error", "data": {"detail": f"Failed to stream message: {str(e)}"}}
            self.db.rollback()
            raise
