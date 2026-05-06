"""
Recommendation Mapping Service: thin adapter that delegates ranking to recommendation_engine.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.domains.content_registry.schemas import RecommendationMappingResponse
from app.domains.recommendation_engine.services.recommendation_ranking_service import (
    RecommendationRankingService,
)


class RecommendationMappingService:
    """Preserve the existing Learning Hub contract while delegating ranking elsewhere."""

    def __init__(self, db: Session):
        self.db = db

    def get_learning_hub_recommendations(
        self,
        teacher_id: UUID,
        locale: str = "en",
        limit: int = 6,
        mode: str = "personalized",
    ) -> RecommendationMappingResponse:
        return RecommendationRankingService(self.db).get_learning_hub_recommendations(
            teacher_id=teacher_id,
            locale=locale,
            limit=limit,
            mode=mode,
        )
