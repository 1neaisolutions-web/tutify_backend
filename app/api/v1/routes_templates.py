"""
Template API routes (v1).
"""
import json
import uuid
from typing import List, Optional, Dict, Any, AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, or_

# API dependencies placeholder (for future auth/tenant deps)
from app.db.session import get_db
from app.domains.auth.dependencies import get_optional_current_user, get_current_user
from app.domains.auth.models import User
from app.models.template import Template, TemplateCategory
from app.models.template_version import TemplateVersion, TemplateVersionStatus
from app.models.template_execution import TemplateExecution
from app.schemas.template_execution import TemplateExecutionPublic
from app.models.template_favorite import TemplateFavorite
from app.schemas.template import (
    TemplateListItem,
    TemplateDetail,
    TemplateVersionPublic,
    TemplateExecuteRequest,
    TemplateExecuteResponse,
)
from app.services.execution_service import ExecutionService
from app.domains.subscriptions.services.credit_service import CreditService
from app.domains.subscriptions.credit_errors import insufficient_credits_detail
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["templates"])


def _get_session_id(request: Request) -> Optional[str]:
    """Get session ID from request headers or cookies.
    
    For now, we'll use a simple header-based approach.
    Frontend should send X-Session-Id header.
    """
    return request.headers.get("X-Session-Id") or request.cookies.get("session_id")


def _get_latest_published_version(
    db: Session,
    template_id: Any,
) -> Optional[TemplateVersion]:
    """Fetch the latest published TemplateVersion for a given template."""
    return (
        db.query(TemplateVersion)
        .filter(
            TemplateVersion.template_id == template_id,
            TemplateVersion.status == TemplateVersionStatus.PUBLISHED.value,
        )
        .order_by(TemplateVersion.version.desc())
        .first()
    )


@router.get("/api/v1/templates", response_model=List[TemplateListItem])
def list_templates(
    request: Request,
    db: Session = Depends(get_db),
    subject: Optional[str] = Query(default=None),
    grade_band: Optional[str] = Query(default=None),
    category: Optional[TemplateCategory] = Query(default=None),
    q: Optional[str] = Query(default=None, description="Search query for template name/description"),
    is_hot: Optional[bool] = Query(default=None, description="Filter by hot templates (top 3 by execution count)"),
    is_favorite: Optional[bool] = Query(default=None, description="Filter by favorite templates"),
    current_user: Optional[User] = Depends(get_optional_current_user),
) -> List[TemplateListItem]:
    """
    List published templates with search, hot, and favorite support.

    Optional filters:
    - subject: match against subject_default
    - grade_band: templates whose grade_bands_supported contains this value
    - category: filter by TemplateCategory
    - q: search query (searches in name and description)
    - is_hot: filter by hot templates (top 3 by execution count)
    - is_favorite: filter by favorite templates for current session
    """
    # Base query: active templates that have at least one published version
    try:
        logger.info(f"Listing templates with filters: subject={subject}, grade_band={grade_band}, category={category}, q={q}")
        
        subquery = (
            db.query(TemplateVersion.template_id)
            .filter(TemplateVersion.status == TemplateVersionStatus.PUBLISHED)
            .distinct()
            .subquery()
        )

        query = db.query(Template).filter(
            Template.is_active.is_(True),
            Template.id.in_(subquery),
        )

        # Apply filters
        if category is not None:
            query = query.filter(Template.category == category)

        if subject:
            query = query.filter(Template.subject_default == subject)

        if grade_band:
            query = query.filter(Template.grade_bands_supported.contains([grade_band]))

        # Search functionality
        if q:
            search_term = f"%{q.lower()}%"
            query = query.filter(
                or_(
                    func.lower(Template.name).like(search_term),
                    func.lower(Template.description).like(search_term),
                )
            )

        # Get all templates
        templates = query.order_by(Template.name.asc()).all()
        logger.info(f"Found {len(templates)} templates")

        # Get top 3 template IDs by execution count for "hot" flag
        try:
            top_templates = (
                db.query(TemplateExecution.template_id)
                .group_by(TemplateExecution.template_id)
                .order_by(func.count(TemplateExecution.id).desc())
                .limit(3)
                .all()
            )
            hot_template_ids = {t[0] for t in top_templates}
        except Exception as e:
            logger.warning(f"Error getting hot templates: {e}")
            hot_template_ids = set()

        # Get favorite template IDs for current session/user
        # Prefer user_id if authenticated, otherwise use session_id
        session_id = _get_session_id(request)
        favorite_template_ids = set()
        try:
            if current_user:
                # Use user_id if authenticated
                favorites = db.query(TemplateFavorite.template_id).filter(
                    TemplateFavorite.user_id == current_user.id
                ).all()
                favorite_template_ids = {f[0] for f in favorites}
            elif session_id:
                # Fall back to session_id for non-authenticated users
                favorites = db.query(TemplateFavorite.template_id).filter(
                    TemplateFavorite.session_id == session_id
                ).all()
                favorite_template_ids = {f[0] for f in favorites}
        except Exception as e:
            logger.warning(f"Error getting favorites: {e}")

        # Get execution counts for each template (optimized with single query)
        try:
            execution_counts = (
                db.query(
                    TemplateExecution.template_id,
                    func.count(TemplateExecution.id).label('count')
                )
                .group_by(TemplateExecution.template_id)
                .all()
            )
            execution_count_map = {t[0]: t[1] for t in execution_counts}
        except Exception as e:
            logger.warning(f"Error getting execution counts: {e}")
            execution_count_map = {}

        # Build response with hot and favorite flags
        result = []
        for template in templates:
            execution_count = execution_count_map.get(template.id, 0)
            template_is_hot = template.id in hot_template_ids
            template_is_favorite = template.id in favorite_template_ids
            
            # Apply hot filter
            if is_hot is not None and template_is_hot != is_hot:
                continue
            
            # Apply favorite filter
            if is_favorite is not None and template_is_favorite != is_favorite:
                continue
            
            result.append(TemplateListItem(
                id=template.id,
                slug=template.slug,
                name=template.name,
                description=template.description,
                category=template.category,
                subject_default=template.subject_default,
                grade_bands_supported=template.grade_bands_supported,
                is_active=template.is_active,
                is_hot=template_is_hot,
                is_favorite=template_is_favorite,
                execution_count=execution_count,
            ))

        return result
    except Exception as e:
        logger.error(f"Error listing templates: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)[:200]}"
        )


@router.get("/api/v1/templates/{slug}", response_model=TemplateDetail)
def get_template_detail(
    slug: str,
    db: Session = Depends(get_db),
) -> TemplateDetail:
    """Get template metadata and latest published version by slug."""
    template: Optional[Template] = (
        db.query(Template)
        .filter(Template.slug == slug, Template.is_active.is_(True))
        .first()
    )

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template with slug '{slug}' not found or is not active.",
        )

    latest_version = _get_latest_published_version(db, template.id)
    latest_version_public: Optional[TemplateVersionPublic] = None

    if latest_version:
        latest_version_public = TemplateVersionPublic.model_validate(latest_version)

    return TemplateDetail(
        id=template.id,
        slug=template.slug,
        name=template.name,
        description=template.description,
        category=template.category,
        subject_default=template.subject_default,
        grade_bands_supported=template.grade_bands_supported,
        is_system_template=template.is_system_template,
        is_active=template.is_active,
        created_at=template.created_at,
        updated_at=template.updated_at,
        latest_version=latest_version_public,
    )


def _validate_against_input_schema(
    input_schema: Dict[str, Any],
    data: Dict[str, Any],
) -> None:
    """
    Perform lightweight validation based on TemplateVersion.input_schema.

    We only enforce that keys listed in a top-level "required" array
    exist in the provided data.

    Args:
        input_schema: JSON schema from TemplateVersion
        data: Input data to validate

    Raises:
        HTTPException: 422 if required fields are missing
    """
    if not isinstance(input_schema, dict):
        return  # Skip validation if schema is invalid
    
    required_fields = input_schema.get("required", [])
    if not isinstance(required_fields, list):
        return  # Skip if required is not a list
    
    missing = [field for field in required_fields if field not in data]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": f"Missing required fields in input data: {', '.join(missing)}",
                "missing": missing,
                "error_type": "validation_error",
            },
        )


@router.post(
    "/api/v1/templates/{slug}/execute",
    response_model=TemplateExecuteResponse,
    status_code=status.HTTP_200_OK,
)
async def execute_template(
    slug: str,
    payload: TemplateExecuteRequest,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
) -> TemplateExecuteResponse:
    """
    Execute a template by slug using the latest published version.

    This uses a stubbed execution service that returns fake but structurally
    correct UniversalTemplateOutput (no real LLM yet).
    
    Authentication is optional - if provided, user_id and tenant_id will be tracked.
    """
    template: Optional[Template] = (
        db.query(Template)
        .filter(Template.slug == slug, Template.is_active.is_(True))
        .first()
    )
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found.",
        )

    latest_version = _get_latest_published_version(db, template.id)
    if not latest_version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No published version found for this template.",
        )

    # Lightweight validation based on input_schema
    _validate_against_input_schema(latest_version.input_schema or {}, payload.data)

    # Get user_id and tenant_id from auth if available
    user_id = current_user.id if current_user else None
    tenant_id = current_user.tenant_id if current_user else None

    # Credit check — authenticated users must have sufficient balance
    if current_user:
        credit_service = CreditService(db)
        check = credit_service.check_balance(current_user.id)
        cost = credit_service.get_feature_cost("template_generate")
        if not check.allowed or check.balance < cost:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=insufficient_credits_detail(
                    check,
                    cost,
                    "You don't have enough credits to run this template.",
                ),
            )

    try:
        # Execute via execution service (async); output shape is from template's output_schema
        execution, output_dict = await ExecutionService.execute(
            db,
            template=template,
            template_version=latest_version,
            input_data=payload.data,
            user_id=user_id,
            tenant_id=tenant_id,
            is_demo=False,
        )
    except RuntimeError as e:
        logger.warning(f"Template execute LLM failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "message": "LLM is unavailable. Check OPENAI_API_KEY (or provider key) and network, then try again.",
                "error_type": "llm_unavailable",
                "hint": str(e),
            },
        )
    except ValueError as e:
        if "USE_REAL_LLM" in str(e) or "API key" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"message": str(e), "error_type": "llm_config"},
            )
        raise

    # Charge credits after successful execution
    if current_user:
        try:
            credit_service = CreditService(db)
            credit_service.charge(
                user_id=current_user.id,
                feature_key="template_generate",
                llm_response=None,
                description=f"Template · {template.name}",
            )
        except Exception:
            pass  # never block the response if credit charge fails

    return TemplateExecuteResponse(
        execution_id=execution.id,
        template_id=execution.template_id,
        template_version=execution.template_version or latest_version.version,
        output=output_dict,
        model_used=execution.model_used,
        provider_used=execution.provider_used,
        token_usage=execution.token_usage,
        latency_ms=execution.latency_ms,
    )


@router.post(
    "/api/v1/templates/{slug}/execute-stream",
    status_code=status.HTTP_200_OK,
)
async def execute_template_stream(
    slug: str,
    payload: TemplateExecuteRequest,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
) -> StreamingResponse:
    """
    Execute a template with streaming output (Server-Sent Events).

    Returns an SSE stream with schema-based section events only:
    meta, section_start, section_content (per output_schema), done, or error.
    Does not stream raw JSON or "content" chunks.
    """
    template: Optional[Template] = (
        db.query(Template)
        .filter(Template.slug == slug, Template.is_active.is_(True))
        .first()
    )
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template with slug '{slug}' not found or is not active.",
        )

    latest_version = _get_latest_published_version(db, template.id)
    if not latest_version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No published version found for template '{slug}'. Please ensure at least one version is published.",
        )

    # Lightweight validation based on input_schema
    _validate_against_input_schema(latest_version.input_schema or {}, payload.data)

    # Get user_id and tenant_id from auth if available
    user_id = current_user.id if current_user else None
    tenant_id = current_user.tenant_id if current_user else None

    # Credit check before stream opens — must be done here (can't send 402 mid-stream)
    if current_user:
        credit_service = CreditService(db)
        check = credit_service.check_balance(current_user.id)
        cost = credit_service.get_feature_cost("template_generate")
        if not check.allowed or check.balance < cost:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=insufficient_credits_detail(
                    check,
                    cost,
                    "You don't have enough credits to run this template.",
                ),
            )

    async def generate_sse_events() -> AsyncIterator[str]:
        """Generate SSE-formatted events from ExecutionService domain events.

        CRITICAL: Send events immediately without buffering for smooth streaming like GPT.
        Each chunk from the LLM is sent as soon as it arrives.
        """
        try:
            async for event in ExecutionService.execute_stream(
                db,
                template=template,
                template_version=latest_version,
                input_data=payload.data,
                user_id=user_id,
                tenant_id=tenant_id,
                is_demo=False,
            ):
                # Only forward schema-based events; never send raw "content" (legacy/prevents JSON leak)
                if isinstance(event, dict) and event.get("type") == "content":
                    continue
                # CRITICAL: Format and send immediately without buffering
                event_json = json.dumps(event)
                yield f"data: {event_json}\n\n"

            # Charge credits after stream completes successfully
            if current_user:
                try:
                    credit_service = CreditService(db)
                    credit_service.charge(
                        user_id=current_user.id,
                        feature_key="template_generate",
                        llm_response=None,
                        description=f"Template · {template.name}",
                    )
                except Exception:
                    pass
        except Exception as e:
            # Emit error event
            error_event = {
                "type": "error",
                "message": f"Streaming error: {str(e)}",
                "template_slug": slug,
            }
            yield f"data: {json.dumps(error_event)}\n\n"

    return StreamingResponse(
        generate_sse_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/api/v1/templates/{template_id}/favorite", status_code=status.HTTP_201_CREATED)
def add_favorite(
    template_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
) -> Dict[str, Any]:
    """Add a template to favorites."""
    try:
        # Verify template exists
        template = db.query(Template).filter(
            Template.id == template_id,
            Template.is_active.is_(True)
        ).first()
        
        if not template:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Template not found"
            )

        session_id = _get_session_id(request)
        
        # Require either auth or session_id
        if not current_user and not session_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Authentication or Session ID required. Send Authorization header or X-Session-Id header."
            )

        # Check if already favorited - prefer user_id if authenticated
        if current_user:
            existing = db.query(TemplateFavorite).filter(
                TemplateFavorite.template_id == template_id,
                TemplateFavorite.user_id == current_user.id
            ).first()
        else:
            existing = db.query(TemplateFavorite).filter(
                TemplateFavorite.template_id == template_id,
                TemplateFavorite.session_id == session_id
            ).first()

        if existing:
            return {"message": "Template already in favorites", "is_favorite": True}

        # Create favorite
        favorite = TemplateFavorite(
            template_id=template_id,
            session_id=session_id,
            user_id=current_user.id if current_user else None,
        )
        db.add(favorite)
        db.commit()
        db.refresh(favorite)

        return {"message": "Template added to favorites", "is_favorite": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding favorite: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error adding favorite: {str(e)[:200]}"
        )


@router.delete("/api/v1/templates/{template_id}/favorite", status_code=status.HTTP_200_OK)
def remove_favorite(
    template_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
) -> Dict[str, Any]:
    """Remove a template from favorites."""
    try:
        session_id = _get_session_id(request)
        
        # Require either auth or session_id
        if not current_user and not session_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Authentication or Session ID required. Send Authorization header or X-Session-Id header."
            )

        # Find favorite - prefer user_id if authenticated
        if current_user:
            favorite = db.query(TemplateFavorite).filter(
                TemplateFavorite.template_id == template_id,
                TemplateFavorite.user_id == current_user.id
            ).first()
        else:
            favorite = db.query(TemplateFavorite).filter(
                TemplateFavorite.template_id == template_id,
                TemplateFavorite.session_id == session_id
            ).first()

        if not favorite:
            return {"message": "Template not in favorites", "is_favorite": False}

        db.delete(favorite)
        db.commit()

        return {"message": "Template removed from favorites", "is_favorite": False}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing favorite: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error removing favorite: {str(e)[:200]}"
        )


@router.post("/api/v1/templates/{template_id}/favorite/toggle", status_code=status.HTTP_200_OK)
def toggle_favorite(
    template_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),  # Require authentication
) -> Dict[str, Any]:
    """Toggle favorite status of a template. Requires authentication."""
    from sqlalchemy.exc import IntegrityError
    
    try:
        # Authentication is required - get_current_user will raise 401 if not authenticated
        # Check if already favorited by user_id
        favorite = db.query(TemplateFavorite).filter(
            TemplateFavorite.template_id == template_id,
            TemplateFavorite.user_id == current_user.id
        ).first()

        if favorite:
            # Remove favorite (user-based or session-based)
            db.delete(favorite)
            db.commit()
            return {"message": "Template removed from favorites", "is_favorite": False}
        else:
            # Add favorite
            # Verify template exists
            template = db.query(Template).filter(
                Template.id == template_id,
                Template.is_active.is_(True)
            ).first()
            
            if not template:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Template not found"
                )

            # Create new favorite - use only user_id (no session_id needed since auth is required)
            new_favorite = TemplateFavorite(
                template_id=template_id,
                user_id=current_user.id,
                session_id=None,  # Not needed when authenticated
            )
            
            try:
                db.add(new_favorite)
                db.commit()
                db.refresh(new_favorite)
                return {"message": "Template added to favorites", "is_favorite": True}
            except IntegrityError as e:
                # Handle unique constraint violation gracefully (race condition)
                db.rollback()
                
                # Check if it's a unique constraint violation
                error_str = str(e.orig) if hasattr(e, 'orig') else str(e)
                if 'uq_template_favorite_user' in error_str:
                    # Favorite already exists due to race condition - verify and return
                    logger.warning(f"Unique constraint violation for favorite {template_id}, rechecking")
                    
                    # Re-check for existing favorite (might have been created between our check and insert)
                    existing = db.query(TemplateFavorite).filter(
                        TemplateFavorite.template_id == template_id,
                        TemplateFavorite.user_id == current_user.id
                    ).first()
                    if existing:
                        return {"message": "Template already in favorites", "is_favorite": True}
                
                # Re-raise if not a unique constraint violation we can handle
                logger.error(f"Unhandled integrity error: {e}")
                raise
                
    except HTTPException:
        raise
    except IntegrityError as e:
        logger.error(f"Integrity error toggling favorite: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Favorite already exists or constraint violation occurred"
        )
    except Exception as e:
        logger.error(f"Error toggling favorite: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error toggling favorite: {str(e)[:200]}"
        )


@router.get(
    "/api/v1/template-executions/{execution_id}",
    response_model=TemplateExecutionPublic,
)
def get_template_execution(
    execution_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TemplateExecutionPublic:
    """Return a saved template execution for the current user (history restore)."""
    row = (
        db.query(TemplateExecution)
        .filter(
            TemplateExecution.id == execution_id,
            TemplateExecution.user_id == current_user.id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found")

    template = db.query(Template).filter(Template.id == row.template_id).first()
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")

    return TemplateExecutionPublic(
        id=row.id,
        template_id=row.template_id,
        template_slug=template.slug,
        template_version=row.template_version,
        input_data=row.input_data or {},
        output_data=row.output_data,
        model_used=row.model_used,
        provider_used=row.provider_used,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.delete("/api/v1/template-executions/{execution_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template_execution(
    execution_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a template execution owned by the current user (history cleanup)."""
    row = (
        db.query(TemplateExecution)
        .filter(
            TemplateExecution.id == execution_id,
            TemplateExecution.user_id == current_user.id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found")
    db.delete(row)
    db.commit()
    return None


