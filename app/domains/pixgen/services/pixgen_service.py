"""
Service layer for PixGen generation workflows.
"""
from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.domains.pixgen.models import PixGenGeneration
from app.domains.pixgen.schemas import (
    GenerateBatchRequest,
    GenerateImageRequest,
    GenerationResponse,
    GenerationStatusResponse,
)
from app.domains.pixgen.services.model_adapter import generate_image_with_model

logger = get_logger(__name__)


class PixGenService:
    """
    Handles PixGen generation orchestration and persistence.

    Designed for async evolution:
    - today: immediate model invocation
    - later: queue + worker updates same status fields
    """

    def __init__(self, db: Session):
        self.db = db

    def generate_single(
        self,
        user_id: UUID,
        payload: GenerateImageRequest,
        raise_on_error: bool = True,
    ) -> GenerationResponse:
        generation = PixGenGeneration(
            user_id=user_id,
            prompt=payload.prompt,
            style_preset=payload.stylePreset,
            aspect_ratio=payload.aspectRatio,
            status="processing",
        )
        self.db.add(generation)
        self.db.flush()

        try:
            model_result = generate_image_with_model(
                {
                    "prompt": payload.prompt,
                    "stylePreset": payload.stylePreset,
                    "aspectRatio": payload.aspectRatio,
                }
            )
            generation.image_url = model_result["imageUrl"]
            generation.status = model_result["status"]
            generation.provider = model_result.get("provider")
            generation.model = model_result.get("model")
            generation.generation_metadata = model_result.get("metadata")
            generation.error = None
        except Exception as exc:
            logger.error(f"PixGen single generation failed: {exc}", exc_info=True)
            generation.status = "failed"
            generation.error = str(exc)
            if raise_on_error:
                raise
        finally:
            # Persist the generation row (even on failure) so history can display it.
            self.db.commit()
            self.db.refresh(generation)

        return GenerationResponse(
            id=generation.id,
            imageUrl=generation.image_url,
            status=generation.status,
            createdAt=generation.created_at,
        )

    def generate_batch(self, user_id: UUID, payload: GenerateBatchRequest) -> List[GenerationResponse]:
        results: List[GenerationResponse] = []
        for _ in range(payload.batchSize):
            single_payload = GenerateImageRequest(
                prompt=payload.prompt,
                stylePreset=payload.stylePreset,
                aspectRatio=payload.aspectRatio,
            )
            # Do not abort the whole batch if one generation fails.
            result = self.generate_single(
                user_id=user_id,
                payload=single_payload,
                raise_on_error=False,
            )
            results.append(result)
        return results

    def get_generation_status(self, user_id: UUID, generation_id: UUID) -> Optional[GenerationStatusResponse]:
        generation = (
            self.db.query(PixGenGeneration)
            .filter(PixGenGeneration.id == generation_id, PixGenGeneration.user_id == user_id)
            .first()
        )
        if not generation:
            return None

        return GenerationStatusResponse(
            id=generation.id,
            imageUrl=generation.image_url,
            status=generation.status,
            createdAt=generation.created_at,
            provider=generation.provider,
            model=generation.model,
            error=generation.error,
            metadata=generation.generation_metadata,
        )

    def list_user_generations(self, user_id: UUID, limit: int = 50, offset: int = 0) -> List[GenerationResponse]:
        items = (
            self.db.query(PixGenGeneration)
            .filter(PixGenGeneration.user_id == user_id)
            .order_by(PixGenGeneration.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [
            GenerationResponse(
                id=item.id,
                imageUrl=item.image_url,
                status=item.status,
                createdAt=item.created_at,
            )
            for item in items
        ]
