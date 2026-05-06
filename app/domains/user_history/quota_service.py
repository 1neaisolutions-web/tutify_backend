"""
History quota enforcement and LRU eviction.

All creation paths for history-tracked sources must call `check_and_enforce(...)`
before inserting a new row and then attach the returned info via `X-History-*` headers.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session


WARNING_THRESHOLD = 0.80


# Limits keyed by subscription tier key. The subscriptions domain currently uses:
#   free | premium | enterprise
HISTORY_LIMITS_BY_TIER: dict[str, dict[str, int]] = {
    "free": {"per_type": 30, "total": 150},
    "premium": {"per_type": 200, "total": 1000},
    "enterprise": {"per_type": 1000, "total": 6000},
    "_default": {"per_type": 30, "total": 150},
}


# source_type -> (table, user_id_column, created_at_column, title_column_expr)
# title_column_expr can be a column name or SQL expression.
SOURCE_TABLE_MAP: dict[str, tuple[str, str, str, str]] = {
    "quiz": ("teacher_quizzes", "owner_user_id", "created_at", "title"),
    "assignment": ("teacher_assignments", "owner_user_id", "created_at", "title"),
    "worksheet": ("teacher_worksheets", "owner_user_id", "created_at", "title"),
    "exam": ("teacher_exams", "owner_user_id", "created_at", "title"),
    "chatbot_conversation": ("chatbot_conversations", "user_id", "created_at", "COALESCE(title, 'Conversation')"),
    "pixgen_generation": ("pixgen_generations", "user_id", "created_at", "prompt"),
    "youtube_quiz": ("youtube_quiz_generations", "user_id", "created_at", "title"),
    "template_execution": (
        "template_executions",
        "user_id",
        "created_at",
        "COALESCE(t.output_data->>'title', 'Template execution')",
    ),
}


@dataclass
class QuotaCheckResult:
    allowed: bool
    evicted_id: str | None
    evicted_title: str | None
    warning_level: str  # ok | warning | full
    current_count: int
    limit: int


def _get_limits(tier: str) -> dict[str, int]:
    return HISTORY_LIMITS_BY_TIER.get(tier, HISTORY_LIMITS_BY_TIER["_default"])


def _count_items(db: Session, *, user_id: str, source_type: str) -> int:
    table, uid_col, _, _ = SOURCE_TABLE_MAP[source_type]
    row = db.execute(
        text(f"SELECT COUNT(*) FROM {table} WHERE {uid_col} = CAST(:uid AS uuid)"),
        {"uid": user_id},
    ).scalar()
    return int(row or 0)


def _find_oldest_unpinned(db: Session, *, user_id: str, source_type: str) -> dict | None:
    table, uid_col, created_col, title_expr = SOURCE_TABLE_MAP[source_type]
    row = db.execute(
        text(
            f"""
            SELECT t.id::text AS id, {title_expr} AS title
            FROM {table} t
            WHERE t.{uid_col} = CAST(:uid AS uuid)
              AND NOT EXISTS (
                  SELECT 1 FROM user_content_pins p
                  WHERE p.user_id = CAST(:uid AS uuid)
                    AND p.source_type = :source_type
                    AND p.source_id = t.id
              )
            ORDER BY t.{created_col} ASC
            LIMIT 1
            """
        ),
        {"uid": user_id, "source_type": source_type},
    ).mappings().first()
    return dict(row) if row else None


def _evict_item(db: Session, *, user_id: str, source_type: str, item_id: str) -> None:
    table, uid_col, _, _ = SOURCE_TABLE_MAP[source_type]
    db.execute(
        text(f"DELETE FROM {table} WHERE id = CAST(:item_id AS uuid) AND {uid_col} = CAST(:uid AS uuid)"),
        {"item_id": item_id, "uid": user_id},
    )
    db.commit()


def check_and_enforce(db: Session, *, user_id: str, source_type: str, tier: str) -> QuotaCheckResult:
    """
    Call BEFORE inserting a new history item.

    - Under limit: allowed=True, warning_level ok|warning.
    - At limit: evict oldest non-pinned item, allowed=True, warning_level full.
    - At limit and all pinned: raises HTTP 429 (caller must NOT save the item).
    """

    limits = _get_limits(tier)
    per_type_limit = limits["per_type"]
    current = _count_items(db, user_id=user_id, source_type=source_type)

    if current < per_type_limit:
        ratio = (current + 1) / per_type_limit
        level = "warning" if ratio >= WARNING_THRESHOLD else "ok"
        return QuotaCheckResult(
            allowed=True,
            evicted_id=None,
            evicted_title=None,
            warning_level=level,
            current_count=current,
            limit=per_type_limit,
        )

    oldest = _find_oldest_unpinned(db, user_id=user_id, source_type=source_type)
    if oldest is None:
        raise HTTPException(
            status_code=429,
            detail={
                "code": "HISTORY_LIMIT_REACHED",
                "reason": "all_items_pinned",
                "source_type": source_type,
                "limit": per_type_limit,
                "message": (
                    f"You have reached the limit of {per_type_limit} {source_type} items "
                    f"and all existing items are pinned. Unpin some items to make room."
                ),
            },
        )

    _evict_item(db, user_id=user_id, source_type=source_type, item_id=oldest["id"])
    return QuotaCheckResult(
        allowed=True,
        evicted_id=oldest["id"],
        evicted_title=oldest.get("title"),
        warning_level="full",
        current_count=current,
        limit=per_type_limit,
    )


def get_quota_status(db: Session, *, user_id: str, tier: str) -> dict:
    limits = _get_limits(tier)
    usage = []
    total_used = 0
    for source_type in SOURCE_TABLE_MAP:
        count = _count_items(db, user_id=user_id, source_type=source_type)
        total_used += count
        ratio = (count / limits["per_type"]) if limits["per_type"] else 0.0
        if ratio >= 1.0:
            level = "full"
        elif ratio >= WARNING_THRESHOLD:
            level = "warning"
        else:
            level = "ok"
        usage.append({"source_type": source_type, "used": count, "limit": limits["per_type"], "warning_level": level})

    return {
        "tier": tier,
        "per_type_limit": limits["per_type"],
        "total_limit": limits["total"],
        "total_used": total_used,
        "usage": usage,
    }

