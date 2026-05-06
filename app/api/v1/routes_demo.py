"""
Demo template execution routes (v1).
"""
import json
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.template import Template
from app.models.template_version import TemplateVersionStatus, TemplateVersion
from app.schemas.template import TemplateExecuteRequest, TemplateExecuteResponse
from app.services.execution_service import ExecutionService


router = APIRouter(tags=["demo"])


def _get_latest_published_version(
    db: Session,
    template_id,
) -> TemplateVersion | None:
    return (
        db.query(TemplateVersion)
        .filter(
            TemplateVersion.template_id == template_id,
            TemplateVersion.status == TemplateVersionStatus.PUBLISHED,
        )
        .order_by(TemplateVersion.version.desc())
        .first()
    )


@router.post(
    "/api/v1/demo/templates/{slug}/execute",
    response_model=TemplateExecuteResponse,
    status_code=status.HTTP_200_OK,
)
async def execute_demo_template(
    slug: str,
    payload: TemplateExecuteRequest,
    db: Session = Depends(get_db),
) -> TemplateExecuteResponse:
    """
    Demo execution endpoint for templates.

    - No auth (intended for demo / trial usage).
    - Tenant is marked as a special demo tenant (currently stored as NULL).
    - TODO: Add rate limiting / abuse protection for demo usage.
    """
    template: Template | None = (
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

    # Note: We deliberately keep validation lightweight here as well.
    execution, output_dict = await ExecutionService.execute(
        db,
        template=template,
        template_version=latest_version,
        input_data=payload.data,
        user_id=None,
        tenant_id=None,  # Could be a dedicated demo tenant ID in the future
        is_demo=True,
    )

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
    "/api/v1/demo/templates/{slug}/execute-stream",
    status_code=status.HTTP_200_OK,
)
async def execute_demo_template_stream(
    slug: str,
    payload: TemplateExecuteRequest,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """
    Demo streaming execution endpoint for templates.

    - No auth (intended for demo / trial usage).
    - Tenant is marked as a special demo tenant (currently stored as NULL).
    - TODO: Add rate limiting / abuse protection for demo usage.
    """
    template: Template | None = (
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

    async def generate_sse_events() -> AsyncIterator[str]:
        """Generate SSE-formatted events from ExecutionService domain events."""
        try:
            async for event in ExecutionService.execute_stream(
                db,
                template=template,
                template_version=latest_version,
                input_data=payload.data,
                user_id=None,
                tenant_id=None,  # Demo tenant
                is_demo=True,
            ):
                # Format as SSE event
                event_json = json.dumps(event)
                yield f"data: {event_json}\n\n"
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


