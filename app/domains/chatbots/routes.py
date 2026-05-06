"""
Chatbot API routes.
"""
from typing import List, Optional
from uuid import UUID
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.session import get_db
from app.domains.auth.dependencies import get_current_user, get_optional_current_user
from app.domains.auth.models import User
from app.domains.chatbots import schemas
from app.domains.chatbots.services.chatbot_service import ChatbotService
from app.domains.chatbots.services.model_service import ChatbotModelService
from app.domains.chatbots.services.conversation_service import ConversationService
from app.domains.chatbots.services.message_service import MessageService
from app.domains.chatbots.services.capability_service import CapabilityService
from app.domains.chatbots.models import Chatbot, ChatbotConversation, ChatbotMessage
from app.domains.subscriptions.exceptions import InsufficientCreditsError
from app.domains.subscriptions.credit_errors import insufficient_credits_detail
from app.domains.subscriptions.services.subscription_service import SubscriptionService
from app.domains.user_history.quota_service import check_and_enforce

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/chatbots", tags=["chatbots"])


# Chatbot endpoints
@router.get("", response_model=List[schemas.ChatbotListItem])
async def list_chatbots(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_current_user),
):
    """List all chatbots available to the user."""
    chatbot_service = ChatbotService(db)
    user_id = current_user.id if current_user else None
    chatbots = chatbot_service.list_chatbots(user_id=user_id)
    return chatbots


@router.get("/{slug}", response_model=schemas.ChatbotDetail)
async def get_chatbot(
    slug: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_optional_current_user),
):
    """Get chatbot details by slug."""
    chatbot_service = ChatbotService(db)
    chatbot = chatbot_service.get_chatbot_by_slug(slug)
    
    if not chatbot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chatbot not found",
        )
    
    # Check access if required
    if chatbot.access_level == "premium" and not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required for premium chatbots",
        )
    
    # Return chatbot with capabilities
    return chatbot


# Conversation endpoints
@router.get("/conversations", response_model=List[schemas.ConversationListItem])
async def list_all_conversations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return all conversations for the current user across all chatbots, sorted by updated_at desc."""
    offset = (page - 1) * page_size

    rows = (
        db.query(ChatbotConversation, Chatbot, func.count(ChatbotMessage.id))
        .join(Chatbot, Chatbot.id == ChatbotConversation.chatbot_id)
        .outerjoin(ChatbotMessage, ChatbotMessage.conversation_id == ChatbotConversation.id)
        .filter(ChatbotConversation.user_id == current_user.id)
        .group_by(ChatbotConversation.id, Chatbot.id)
        .order_by(ChatbotConversation.updated_at.desc())
        .offset(offset)
        .limit(page_size)
        .all()
    )

    items: List[schemas.ConversationListItem] = []
    for conv, bot, message_count in rows:
        items.append(
            schemas.ConversationListItem(
                id=conv.id,
                chatbot_id=conv.chatbot_id,
                chatbot_slug=bot.slug,
                chatbot_name=bot.name,
                title=conv.title,
                message_count=int(message_count or 0),
                created_at=conv.created_at,
                updated_at=conv.updated_at,
            )
        )
    return items


@router.get("/{slug}/conversations", response_model=List[schemas.ConversationListItem])
async def list_conversations(
    slug: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List user's conversations for a chatbot."""
    chatbot_service = ChatbotService(db)
    conversation_service = ConversationService(db)
    
    chatbot = chatbot_service.get_chatbot_by_slug(slug)
    if not chatbot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chatbot not found",
        )
    
    conversations = conversation_service.list_conversations(
        user_id=current_user.id,
        chatbot_id=chatbot.id,
    )
    
    # Add chatbot info to each conversation
    result = []
    for conv in conversations:
        item = schemas.ConversationListItem(
            id=conv.id,
            chatbot_id=conv.chatbot_id,
            chatbot_slug=slug,
            chatbot_name=chatbot.name,
            title=conv.title,
            message_count=len(conv.messages) if conv.messages else 0,
            created_at=conv.created_at,
            updated_at=conv.updated_at,
        )
        result.append(item)
    
    return result


@router.get("/conversations/{conversation_id}/messages", response_model=schemas.MessagesPage)
async def list_conversation_messages(
    conversation_id: UUID,
    limit: int = Query(50, ge=1, le=200),
    before: Optional[str] = Query(None, description="Cursor from prior page (next_before) to load older messages"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Paginated messages for a conversation (newest chunk first; scroll-up loads older via `before`)."""
    conversation_service = ConversationService(db)
    if not conversation_service.get_conversation(conversation_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    rows, has_more, next_before = conversation_service.list_messages(
        conversation_id,
        current_user.id,
        limit=limit,
        before_cursor=before,
    )
    items = [
        schemas.MessageResponse(
            id=m.id,
            role=m.role,
            content=m.content,
            metadata=m.message_metadata,
            created_at=m.created_at,
        )
        for m in rows
    ]
    return schemas.MessagesPage(items=items, has_more=has_more, next_before=next_before)


@router.get("/conversations/{conversation_id}", response_model=schemas.ConversationDetail)
async def get_conversation(
    conversation_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get conversation metadata with the latest messages only (up to 50). Prefer GET .../messages for pagination."""
    conversation_service = ConversationService(db)

    conversation = conversation_service.get_conversation(conversation_id, current_user.id)
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    chatbot = conversation.chatbot

    rows, _, _ = conversation_service.list_messages(
        conversation_id,
        current_user.id,
        limit=50,
        before_cursor=None,
    )
    messages = [
        schemas.MessageResponse(
            id=msg.id,
            role=msg.role,
            content=msg.content,
            metadata=msg.message_metadata,
            created_at=msg.created_at,
        )
        for msg in rows
    ]

    return schemas.ConversationDetail(
        id=conversation.id,
        chatbot_id=conversation.chatbot_id,
        chatbot_slug=chatbot.slug,
        chatbot_name=chatbot.name,
        title=conversation.title,
        messages=messages,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


@router.post("/{slug}/messages", response_model=schemas.SendMessageResponse)
async def send_message(
    slug: str,
    request: schemas.SendMessageRequest,
    http_request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    response: Response = None,  # type: ignore[assignment]
):
    """Send a message to a chatbot. Supports streaming if requested."""
    chatbot_service = ChatbotService(db)
    message_service = MessageService(db)
    
    chatbot = chatbot_service.get_chatbot_by_slug(slug)
    if not chatbot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chatbot not found",
        )
    
    # Check access
    if chatbot.access_level == "premium":
        # Check subscription
        from app.domains.subscriptions.services.subscription_service import SubscriptionService
        subscription_service = SubscriptionService(db)
        tier = subscription_service.get_user_tier(current_user.id)
        if tier.value == "free":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Premium subscription required",
            )

    # Streaming if Accept: text/event-stream or ?stream=true
    accept_header = http_request.headers.get("accept", "").lower()
    stream_requested = "text/event-stream" in accept_header or http_request.query_params.get("stream") == "true"

    # Quota enforcement: a new conversation is created when conversation_id is absent.
    conversation_uuid = request.get_conversation_id_as_uuid()
    quota = None
    if conversation_uuid is None:
        tier = SubscriptionService(db).get_user_tier(current_user.id).value
        quota = check_and_enforce(db, user_id=str(current_user.id), source_type="chatbot_conversation", tier=tier)

    if stream_requested:
        async def generate_stream():
            try:
                async for chunk in message_service.stream_message(
                    chatbot_id=chatbot.id,
                    user_id=current_user.id,
                    message=request.message,
                    conversation_id=conversation_uuid,
                    tenant_id=current_user.tenant_id,
                    metadata={
                        **(request.metadata or {}),
                        "bot_mode": request.bot_mode,
                        "response_length": request.response_length,
                        "web_search": request.web_search,
                    },
                ):
                    yield f"data: {json.dumps(chunk)}\n\n"
                    import asyncio
                    await asyncio.sleep(0)
            except Exception as e:
                logger.error(f"Error in stream (messages endpoint): {e}", exc_info=True)
                error_chunk = {"type": "error", "data": {"detail": str(e)}}
                yield f"data: {json.dumps(error_chunk)}\n\n"

        return StreamingResponse(
            generate_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                **(
                    {
                        "X-History-Warning-Level": quota.warning_level,
                        "X-History-Count": str(quota.current_count + 1),
                        "X-History-Limit": str(quota.limit),
                        **(
                            {
                                "X-History-Eviction-Title": quota.evicted_title or "",
                                "X-History-Eviction-Type": "chatbot_conversation",
                            }
                            if quota.evicted_id
                            else {}
                        ),
                    }
                    if quota is not None
                    else {}
                ),
            },
        )
    
    try:
        result = await message_service.send_message(
            chatbot_id=chatbot.id,
            user_id=current_user.id,
            message=request.message,
            conversation_id=conversation_uuid,
            tenant_id=current_user.tenant_id,
            metadata={
                **(request.metadata or {}),
                "bot_mode": request.bot_mode,
                "response_length": request.response_length,
                "web_search": request.web_search,
            },
        )

        if response is not None and quota is not None:
            response.headers["X-History-Warning-Level"] = quota.warning_level
            response.headers["X-History-Count"] = str(quota.current_count + 1)
            response.headers["X-History-Limit"] = str(quota.limit)
            if quota.evicted_id:
                response.headers["X-History-Eviction-Title"] = quota.evicted_title or ""
                response.headers["X-History-Eviction-Type"] = "chatbot_conversation"
        
        return schemas.SendMessageResponse(
            conversation_id=result["conversation_id"],
            user_message=schemas.MessageResponse(
                id=result["user_message"].id,
                role=result["user_message"].role,
                content=result["user_message"].content,
                metadata=result["user_message"].message_metadata,
                created_at=result["user_message"].created_at,
            ),
            assistant_message=schemas.MessageResponse(
                id=result["assistant_message"].id,
                role=result["assistant_message"].role,
                content=result["assistant_message"].content,
                metadata=result["assistant_message"].message_metadata,
                created_at=result["assistant_message"].created_at,
            ),
            token_usage=result.get("token_usage"),
            cost_estimate=result.get("cost_estimate"),
            model_used=result.get("model_used"),
            provider_used=result.get("provider_used"),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error sending message: {e}", exc_info=True)
        # Return more detailed error for debugging
        error_detail = f"Failed to send message: {str(e)}"
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_detail,
        )


@router.post("/{slug}/messages/stream")
async def send_message_stream(
    slug: str,
    request: schemas.SendMessageRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Send a message to a chatbot with streaming response (SSE)."""
    chatbot_service = ChatbotService(db)
    message_service = MessageService(db)
    
    chatbot = chatbot_service.get_chatbot_by_slug(slug)
    if not chatbot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chatbot not found",
        )
    
    # Check access
    if chatbot.access_level == "premium":
        from app.domains.subscriptions.services.subscription_service import SubscriptionService
        subscription_service = SubscriptionService(db)
        tier = subscription_service.get_user_tier(current_user.id)
        if tier.value == "free":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Premium subscription required",
            )
    
    async def generate_stream():
        try:
            import asyncio
            # Convert conversation_id string to UUID if provided
            conversation_uuid = request.get_conversation_id_as_uuid()
            
            logger.info(f"Starting stream for chatbot {slug}, user {current_user.id}")
            
            async for chunk in message_service.stream_message(
                chatbot_id=chatbot.id,
                user_id=current_user.id,
                message=request.message,
                conversation_id=conversation_uuid,
                tenant_id=current_user.tenant_id,
                metadata={
                    **(request.metadata or {}),
                    "bot_mode": request.bot_mode,
                    "response_length": request.response_length,
                    "web_search": request.web_search,
                },
            ):
                # Format as SSE: data: {json}\n\n
                chunk_json = json.dumps(chunk)
                sse_line = f"data: {chunk_json}\n\n"
                
                # CRITICAL: Yield SSE chunk immediately
                yield sse_line
                
                # CRITICAL: Yield control to event loop to flush chunk immediately (like GPT)
                # This ensures chunks are sent to frontend in real-time, not buffered
                await asyncio.sleep(0)
        except Exception as e:
            logger.error(f"Error in stream: {e}", exc_info=True)
            error_chunk = {"type": "error", "data": {"detail": str(e)}}
            yield f"data: {json.dumps(error_chunk)}\n\n"
    
    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a conversation."""
    conversation_service = ConversationService(db)
    
    success = conversation_service.delete_conversation(conversation_id, current_user.id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    
    return {"message": "Conversation deleted"}


# Capability endpoints
@router.post("/{slug}/capabilities/{capability_key}", response_model=schemas.ExecuteCapabilityResponse)
async def execute_capability(
    slug: str,
    capability_key: str,
    request: schemas.ExecuteCapabilityRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Execute a chatbot capability."""
    chatbot_service = ChatbotService(db)
    capability_service = CapabilityService(db)
    
    chatbot = chatbot_service.get_chatbot_by_slug(slug)
    if not chatbot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chatbot not found",
        )
    
    # Check access if capability is premium
    # (This would be checked in capability_service if needed)
    
    try:
        result = await capability_service.execute_capability(
            chatbot_id=chatbot.id,
            capability_key=capability_key,
            user_id=current_user.id,
            input_data=request.input,
            parameters=request.parameters,
            save_result=request.save_result,
            conversation_id=request.conversation_id,
        )
        
        return schemas.ExecuteCapabilityResponse(
            result=result["result"],
            metadata=result.get("metadata"),
            usage_id=result.get("usage_id"),
            progress_update=result.get("progress_update"),
            conversation_id=result.get("conversation_id"),
        )
    except InsufficientCreditsError as e:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=insufficient_credits_detail(e.check, e.required, e.message),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error executing capability: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to execute capability",
        )


@router.post("/{slug}/history-log", response_model=schemas.HistoryLogResponse)
async def history_log(
    slug: str,
    body: schemas.HistoryLogRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Log a client-side generation as a chatbot conversation so it appears in /history."""
    chatbot_service = ChatbotService(db)
    chatbot = chatbot_service.get_chatbot_by_slug(slug)
    if not chatbot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chatbot not found")

    conversation_service = ConversationService(db)
    if body.conversation_id:
        conversation = conversation_service.get_conversation(body.conversation_id, current_user.id)
        if not conversation or conversation.chatbot_id != chatbot.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

        conversation.title = body.title or conversation.title
        existing_meta = conversation.conversation_metadata or {}
        conversation.conversation_metadata = {
            **existing_meta,
            **(body.metadata or {}),
            "chatbot_slug": slug,
            "chatbot_name": chatbot.name,
        }
        conversation.updated_at = datetime.now(timezone.utc)

        user_msg = (
            db.query(ChatbotMessage)
            .filter(
                ChatbotMessage.conversation_id == conversation.id,
                ChatbotMessage.role == "user",
            )
            .order_by(ChatbotMessage.created_at.desc(), ChatbotMessage.id.desc())
            .first()
        )
        if not user_msg:
            user_msg = ChatbotMessage(
                conversation_id=conversation.id,
                role="user",
                content=body.user_content,
                message_metadata={"source": "history_log", **(body.metadata or {})},
            )
            db.add(user_msg)
        else:
            user_msg.content = body.user_content
            user_msg.message_metadata = {"source": "history_log", **(body.metadata or {})}

        assistant_msg = (
            db.query(ChatbotMessage)
            .filter(
                ChatbotMessage.conversation_id == conversation.id,
                ChatbotMessage.role == "assistant",
            )
            .order_by(ChatbotMessage.created_at.desc(), ChatbotMessage.id.desc())
            .first()
        )
        if not assistant_msg:
            assistant_msg = ChatbotMessage(
                conversation_id=conversation.id,
                role="assistant",
                content=body.assistant_content,
                message_metadata={"source": "history_log", **(body.metadata or {})},
            )
            db.add(assistant_msg)
        else:
            assistant_msg.content = body.assistant_content
            assistant_msg.message_metadata = {"source": "history_log", **(body.metadata or {})}

        db.commit()
        return schemas.HistoryLogResponse(conversation_id=conversation.id)

    conversation = conversation_service.create_conversation(
        chatbot_id=chatbot.id,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        title=body.title or "Generation",
        metadata={
            **(body.metadata or {}),
            "chatbot_slug": slug,
            "chatbot_name": chatbot.name,
        },
    )

    db.add(
        ChatbotMessage(
            conversation_id=conversation.id,
            role="user",
            content=body.user_content,
            message_metadata={"source": "history_log", **(body.metadata or {})},
        )
    )
    db.add(
        ChatbotMessage(
            conversation_id=conversation.id,
            role="assistant",
            content=body.assistant_content,
            message_metadata={"source": "history_log", **(body.metadata or {})},
        )
    )
    db.commit()

    return schemas.HistoryLogResponse(conversation_id=conversation.id)
