"""
FastAPI router for Quiz Catalog endpoints.

Provides read-only catalog browsing used by the quiz-generation flow:
  GET  /api/v1/quiz/catalog
  POST /api/v1/quiz/catalog/topics
  POST /api/v1/quiz/catalog/scope-preview
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.session import get_db
from app.domains.auth.dependencies import get_current_user, require_any_role
from app.domains.auth.models import User
from app.domains.content_ingestion.quiz_catalog_schemas import (
    CatalogBookCard,
    CatalogListParams,
    CatalogListResponse,
    CatalogStructureRequest,
    CatalogStructureResponse,
    ScopePreviewRequest,
    ScopePreviewResponse,
    TopicsRequest,
    TopicsResponse,
)
from app.domains.content_ingestion.quiz_catalog_service import QuizCatalogService

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/quiz", tags=["quiz-catalog"])

# Roles that are permitted to browse the quiz catalog
_ALLOWED_ROLES = ("teacher", "school_admin", "super_admin", "org_admin")


# ---------------------------------------------------------------------------
# GET /api/v1/quiz/catalog
# ---------------------------------------------------------------------------

@router.get(
    "/catalog",
    response_model=CatalogListResponse,
    summary="List available content-pack books for quiz generation",
)
def list_catalog(
    subject: Optional[str] = Query(None, description="Filter by subject (case-insensitive, partial match)"),
    grade: Optional[str] = Query(None, description="Filter by grade (case-insensitive, partial match)"),
    curriculum: Optional[str] = Query(None, description="Filter by curriculum (exact match)"),
    q: Optional[str] = Query(None, description="Free-text search across name, description, subject"),
    page: int = Query(1, ge=1, description="1-indexed page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: User = Depends(require_any_role(*_ALLOWED_ROLES)),
    db: Session = Depends(get_db),
) -> CatalogListResponse:
    """
    Return a paginated list of active content packs that have at least one
    published document.  Results are scoped to the caller's tenant.
    """
    params = CatalogListParams(
        subject=subject,
        grade=grade,
        curriculum=curriculum,
        q=q,
        page=page,
        page_size=page_size,
    )

    try:
        service = QuizCatalogService(db)
        packs, total = service.get_catalog(
            tenant_id=current_user.tenant_id,
            params=params,
        )
        items = [
            service.build_catalog_card(pack, current_user.tenant_id)
            for pack in packs
        ]

        logger.info(
            "quiz_catalog_list",
            extra={
                "tenant_id": str(current_user.tenant_id),
                "subject": subject,
                "q": q,
                "total": total,
                "page": page,
                "page_size": page_size,
            },
        )

        return CatalogListResponse(
            total=total,
            page=page,
            page_size=page_size,
            items=items,
        )

    except HTTPException:
        raise
    except Exception:
        logger.error(
            "quiz_catalog_list_error",
            extra={"tenant_id": str(current_user.tenant_id)},
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


# ---------------------------------------------------------------------------
# POST /api/v1/quiz/catalog/topics
# ---------------------------------------------------------------------------

@router.post(
    "/catalog/topics",
    response_model=TopicsResponse,
    summary="Get aggregated topic strands for the given content packs",
    deprecated=True,
    description="Deprecated: use POST /catalog/structure for hierarchical topic trees with stable IDs.",
)
def get_catalog_topics(
    body: TopicsRequest,
    current_user: User = Depends(require_any_role(*_ALLOWED_ROLES)),
    db: Session = Depends(get_db),
) -> TopicsResponse:
    """
    Return all topics (from chapter maps and chunk topic titles) found across
    the requested content packs.  Unknown / unauthorised pack IDs are silently
    skipped.
    """
    try:
        service = QuizCatalogService(db)
        response = service.get_topics_for_packs(
            tenant_id=current_user.tenant_id,
            pack_ids=body.pack_ids,
        )

        logger.info(
            "quiz_catalog_topics",
            extra={
                "tenant_id": str(current_user.tenant_id),
                "requested_pack_count": len(body.pack_ids),
                "topic_count": len(response.topics),
            },
        )

        return response

    except HTTPException:
        raise
    except Exception:
        logger.error(
            "quiz_catalog_topics_error",
            extra={"tenant_id": str(current_user.tenant_id)},
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


# ---------------------------------------------------------------------------
# POST /api/v1/quiz/catalog/structure
# ---------------------------------------------------------------------------

@router.post(
    "/catalog/structure",
    response_model=CatalogStructureResponse,
    summary="Get hierarchical book-chapter-topic structure for content packs",
)
def get_catalog_structure(
    body: CatalogStructureRequest,
    current_user: User = Depends(require_any_role(*_ALLOWED_ROLES)),
    db: Session = Depends(get_db),
) -> CatalogStructureResponse:
    """Return per-document topic trees with stable document_topics.id UUIDs."""
    try:
        service = QuizCatalogService(db)
        return service.get_catalog_structure(
            tenant_id=current_user.tenant_id,
            pack_ids=body.pack_ids,
        )
    except HTTPException:
        raise
    except Exception:
        logger.error(
            "quiz_catalog_structure_error",
            extra={"tenant_id": str(current_user.tenant_id)},
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


# ---------------------------------------------------------------------------
# POST /api/v1/quiz/catalog/scope-preview
# ---------------------------------------------------------------------------

@router.post(
    "/catalog/scope-preview",
    response_model=ScopePreviewResponse,
    summary="Preview the scope of a quiz generation request",
)
def get_scope_preview(
    body: ScopePreviewRequest,
    current_user: User = Depends(require_any_role(*_ALLOWED_ROLES)),
    db: Session = Depends(get_db),
) -> ScopePreviewResponse:
    """
    Return a lightweight summary of how many sources, topics, and segments
    would be covered by the given pack + topic selection.
    """
    try:
        service = QuizCatalogService(db)
        response = service.get_scope_preview(
            tenant_id=current_user.tenant_id,
            req=body,
        )

        logger.info(
            "quiz_catalog_scope_preview",
            extra={
                "tenant_id": str(current_user.tenant_id),
                "pack_count": len(body.pack_ids),
                "estimated_segments": response.estimated_segments,
            },
        )

        return response

    except HTTPException:
        raise
    except Exception:
        logger.error(
            "quiz_catalog_scope_preview_error",
            extra={"tenant_id": str(current_user.tenant_id)},
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )
