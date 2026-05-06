"""
Repository helpers for persisted YouTube quiz generations.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.domains.youtube_quiz.models import YoutubeQuizGeneration


def save_generation(
    db: Session,
    *,
    user_id: uuid.UUID,
    payload_dict: dict,
    result_dict: dict,
) -> YoutubeQuizGeneration:
    now = datetime.now(timezone.utc)

    row = YoutubeQuizGeneration(
        user_id=user_id,
        video_url=payload_dict["video_url"],
        grade_band=payload_dict["grade_band"],
        subject_lens=payload_dict["subject_lens"],
        learning_focus=payload_dict["learning_focus"],
        quiz_language=payload_dict["quiz_language"],
        question_styles=payload_dict.get("question_styles") or [],
        question_count=payload_dict["question_count"],
        lesson_strategy_id=payload_dict.get("lesson_strategy_id"),
        difficulty_level=payload_dict.get("difficultyLevel") or payload_dict.get("difficulty_level"),
        accessibility_mode=bool(payload_dict.get("accessibilityMode") or payload_dict.get("accessibility_mode") or False),
        video_id=payload_dict.get("video_id") or payload_dict.get("videoId"),
        title=result_dict.get("title") or "YouTube quiz",
        result_json=result_dict,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_generation(db: Session, generation_id: str, user_id: uuid.UUID) -> YoutubeQuizGeneration | None:
    try:
        gid = uuid.UUID(generation_id)
    except ValueError:
        return None
    return (
        db.query(YoutubeQuizGeneration)
        .filter(YoutubeQuizGeneration.id == gid, YoutubeQuizGeneration.user_id == user_id)
        .first()
    )


def bump_usage(db: Session, row: YoutubeQuizGeneration) -> YoutubeQuizGeneration:
    """Update usage tracking when a generation is restored/opened."""
    now = datetime.now(timezone.utc)
    row.usage_count = int(row.usage_count or 0) + 1
    row.last_used_at = now
    row.updated_at = now
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_generation_and_bump_usage(
    db: Session,
    *,
    generation_id: str,
    user_id: uuid.UUID,
) -> YoutubeQuizGeneration | None:
    row = get_generation(db, generation_id=generation_id, user_id=user_id)
    if not row:
        return None
    return bump_usage(db, row)


def delete_generation(db: Session, generation_id: str, user_id: uuid.UUID) -> bool:
    row = get_generation(db, generation_id=generation_id, user_id=user_id)
    if not row:
        return False
    db.delete(row)
    db.commit()
    return True

