"""
Content Factory services.

This package uses lazy imports to avoid circular-import issues between:
content_factory services -> content_registry services -> recommendation services -> content_factory services.
"""

from __future__ import annotations

import importlib
from typing import Any


_LAZY_EXPORTS = {
    # content_factory_service
    "ContentFactoryService": "app.domains.content_factory.services.content_factory_service",
    "ContentFactoryServiceError": "app.domains.content_factory.services.content_factory_service",
    # generation orchestration
    "GenerationOrchestratorService": "app.domains.content_factory.services.generation_orchestrator_service",
    # publishing
    "PublishingService": "app.domains.content_factory.services.publishing_service",
    "PublishingPolicyService": "app.domains.content_factory.services.publishing_policy_service",
    # review
    "ContentReviewService": "app.domains.content_factory.services.review_service",
    "ContentReviewServiceError": "app.domains.content_factory.services.review_service",
    # validation
    "ValidationService": "app.domains.content_factory.services.validation_service",
    "ValidationServiceError": "app.domains.content_factory.services.validation_service",
    # gap detection
    "GapGenerationService": "app.domains.content_factory.services.gap_generation_service",
    "GapGenerationWorker": "app.domains.content_factory.services.gap_generation_worker",
}


def __getattr__(name: str) -> Any:
    if name not in _LAZY_EXPORTS:
        raise AttributeError(name)
    module_path = _LAZY_EXPORTS[name]
    module = importlib.import_module(module_path)
    return getattr(module, name)


def __dir__() -> list[str]:
    return sorted(set(list(globals().keys()) + list(_LAZY_EXPORTS.keys())))


__all__ = list(_LAZY_EXPORTS.keys())
