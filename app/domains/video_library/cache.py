"""In-memory recommendation cache (per process)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional
from uuid import UUID

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class _CacheEntry:
    payload: Any
    expires_at_epoch: float
    subjects_fingerprint: tuple[str, ...]


_store: dict[UUID, _CacheEntry] = {}


def invalidate_recommendations(user_id: UUID) -> None:
    """Drop cached recommendations for a user (e.g. after profile subjects change)."""
    if _store.pop(user_id, None):
        logger.debug("video_library cache invalidated user_id=%s", user_id)


def get_cached(user_id: UUID, fingerprint: tuple[str, ...], now_epoch: float) -> Optional[Any]:
    entry = _store.get(user_id)
    if not entry:
        return None
    if entry.subjects_fingerprint != fingerprint:
        return None
    if now_epoch >= entry.expires_at_epoch:
        _store.pop(user_id, None)
        return None
    return entry.payload


def set_cached(user_id: UUID, fingerprint: tuple[str, ...], expires_at_epoch: float, payload: Any) -> None:
    _store[user_id] = _CacheEntry(
        payload=payload,
        expires_at_epoch=expires_at_epoch,
        subjects_fingerprint=fingerprint,
    )
