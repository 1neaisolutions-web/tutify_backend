"""
Recommendation engine services (lazy exports).
"""

from __future__ import annotations

import importlib
from typing import Any


_LAZY_EXPORTS = {
    "RecommendationRankingService": "app.domains.recommendation_engine.services.recommendation_ranking_service",
    "RecommendationScoringService": "app.domains.recommendation_engine.services.recommendation_scoring_service",
}


def __getattr__(name: str) -> Any:
    if name not in _LAZY_EXPORTS:
        raise AttributeError(name)
    module = importlib.import_module(_LAZY_EXPORTS[name])
    return getattr(module, name)


def __dir__() -> list[str]:
    return sorted(set(list(globals().keys()) + list(_LAZY_EXPORTS.keys())))


__all__ = list(_LAZY_EXPORTS.keys())

