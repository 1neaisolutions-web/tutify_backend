"""
Content Registry API routes.
"""
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domains.auth.dependencies import get_current_user, require_any_role
from app.domains.auth.models import User
from app.domains.content_registry import schemas as reg_schemas
from app.domains.content_registry.services import (
    ContentRegistryService,
    ContentRegistryServiceError,
)

router = APIRouter(prefix="/api/v1/content-registry", tags=["content-registry"])


@router.post(
    "/items",
    response_model=reg_schemas.ContentRegistryResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_item(
    data: reg_schemas.ContentRegistryCreate,
    current_user: User = Depends(require_any_role("super_admin", "org_admin")),
    db: Session = Depends(get_db),
):
    """Create a content registry item (admin)."""
    service = ContentRegistryService(db)
    try:
        item = service.create_item(data)
        return item
    except ContentRegistryServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/items", response_model=List[reg_schemas.ContentRegistryListItem])
def list_items(
    content_type: Optional[str] = None,
    item_status: Optional[str] = Query(None, alias="status"),
    locale: Optional[str] = None,
    category: Optional[str] = None,
    difficulty: Optional[str] = None,
    source_type: Optional[str] = Query(
        None,
        description="Filter by registry source_type (e.g. starter_seed, content_factory).",
    ),
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List content registry items with optional filters."""
    if source_type is not None and len(source_type) > 50:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="source_type filter too long",
        )
    service = ContentRegistryService(db)
    items = service.list_items(
        content_type=content_type,
        status=item_status,
        locale=locale,
        category=category,
        difficulty=difficulty,
        source_type=source_type if source_type else None,
        skip=skip,
        limit=limit,
    )
    return items


@router.get("/items/{id}", response_model=reg_schemas.ContentRegistryResponse)
def get_item(
    id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a content registry item by id."""
    service = ContentRegistryService(db)
    item = service.get_item_by_id(id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Content item not found")
    return item


@router.get("/by-content-id/{content_id}", response_model=reg_schemas.ContentRegistryResponse)
def get_by_content_id(
    content_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a content registry item by content_id."""
    service = ContentRegistryService(db)
    item = service.get_item_by_content_id(content_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Content item not found")
    return item


@router.put("/items/{id}", response_model=reg_schemas.ContentRegistryResponse)
def update_item(
    id: UUID,
    data: reg_schemas.ContentRegistryUpdate,
    current_user: User = Depends(require_any_role("super_admin", "org_admin")),
    db: Session = Depends(get_db),
):
    """Update a content registry item (admin)."""
    service = ContentRegistryService(db)
    item = service.update_item(id, data)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Content item not found")
    return item


@router.delete("/items/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(
    id: UUID,
    current_user: User = Depends(require_any_role("super_admin", "org_admin")),
    db: Session = Depends(get_db),
):
    """Delete a content registry item (admin)."""
    service = ContentRegistryService(db)
    if not service.delete_item(id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Content item not found")


@router.post("/items/{id}/publish", response_model=reg_schemas.ContentRegistryResponse)
def publish_item(
    id: UUID,
    current_user: User = Depends(require_any_role("super_admin", "org_admin")),
    db: Session = Depends(get_db),
):
    """Publish a content registry item (admin)."""
    service = ContentRegistryService(db)
    item = service.publish_item(id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Content item not found")
    return item
