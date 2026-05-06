"""Content Registry domain services (lazy exports)."""

from __future__ import annotations

import importlib
from typing import Any


_LAZY_EXPORTS = {
    "ContentRegistryService": "app.domains.content_registry.services.content_registry_service",
    "ContentRegistryServiceError": "app.domains.content_registry.services.content_registry_service",
    "RecommendationMappingService": "app.domains.content_registry.services.recommendation_mapping_service",
}


def __getattr__(name: str) -> Any:
    if name not in _LAZY_EXPORTS:
        raise AttributeError(name)
    module = importlib.import_module(_LAZY_EXPORTS[name])
    return getattr(module, name)


def __dir__() -> list[str]:
    return sorted(set(list(globals().keys()) + list(_LAZY_EXPORTS.keys())))


__all__ = list(_LAZY_EXPORTS.keys())
