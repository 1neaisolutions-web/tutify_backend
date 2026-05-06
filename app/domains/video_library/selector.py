"""Deterministic weekly random selection: 6 channels × 3 videos."""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from datetime import datetime
from typing import List, Sequence
from uuid import UUID

from app.domains.video_library.schemas import (
    LibraryChannel,
    LibraryVideo,
    RecommendationChannel,
    RecommendationVideo,
    VideoLibraryFile,
)


@dataclass(frozen=True)
class SelectionConfig:
    channel_count: int = 6
    videos_per_channel: int = 3


def _week_seed(user_id: UUID, dt: datetime) -> int:
    iso = dt.isocalendar()
    raw = f"{user_id}:{iso.year:04d}:W{iso.week:02d}".encode()
    return int.from_bytes(hashlib.sha256(raw).digest()[:8], "big")


def _allocate_channel_slots(library_keys: Sequence[str], total_slots: int) -> List[str]:
    """Even distribution of channel slots across subjects (remainder to earlier keys)."""
    n = len(library_keys)
    if n == 0:
        return []
    base, extra = divmod(total_slots, n)
    slots: list[str] = []
    for i, key in enumerate(library_keys):
        count = base + (1 if i < extra else 0)
        slots.extend([key] * count)
    return slots[:total_slots]


def _pick_videos(rng: random.Random, channel: LibraryChannel, k: int) -> List[LibraryVideo]:
    vids = list(channel.videos)
    if len(vids) <= k:
        return vids
    return rng.sample(vids, k)


def select_recommendations(
    library: VideoLibraryFile,
    library_subject_keys: Sequence[str],
    user_id: UUID,
    now: datetime,
    config: SelectionConfig | None = None,
) -> List[RecommendationChannel]:
    """
    Build exactly `config.channel_count` channels with `config.videos_per_channel` videos each.
    Channels are chosen only from `library_subject_keys` buckets.
    """
    cfg = config or SelectionConfig()
    keys = [k for k in library_subject_keys if k in library.subjects]
    if not keys:
        keys = list(library.subjects.keys())

    rng = random.Random(_week_seed(user_id, now))
    slot_assignments = _allocate_channel_slots(keys, cfg.channel_count)

    # Pool channels per subject
    pools: dict[str, list[LibraryChannel]] = {}
    for key in set(slot_assignments):
        bucket = library.subjects.get(key)
        if not bucket:
            continue
        pools[key] = list(bucket.channels)

    selected: list[RecommendationChannel] = []
    used_channel_ids: set[str] = set()

    for subject_key in slot_assignments:
        pool = pools.get(subject_key, [])
        candidates = [c for c in pool if c.id not in used_channel_ids]
        if not candidates:
            # borrow from any pool that still has channels
            for alt_key in library.subjects:
                alt_pool = [c for c in library.subjects[alt_key].channels if c.id not in used_channel_ids]
                if alt_pool:
                    candidates = alt_pool
                    break
        if not candidates:
            break
        ch = rng.choice(candidates)
        used_channel_ids.add(ch.id)
        vids = _pick_videos(rng, ch, cfg.videos_per_channel)
        selected.append(
            RecommendationChannel(
                id=ch.id,
                name=ch.name,
                focus=ch.focus,
                gradeBand=ch.gradeBand,
                videos=[
                    RecommendationVideo(
                        id=v.id,
                        title=v.title,
                        youtubeUrl=v.youtubeUrl,
                        gradeBand=v.gradeBand,
                        subject=v.subject,
                        duration=v.duration,
                        tags=v.tags,
                        transcript=v.transcript,
                        bestQuizType=v.bestQuizType,
                    )
                    for v in vids
                ],
            )
        )

    return selected
