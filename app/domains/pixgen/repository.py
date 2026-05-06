"""
Repository helpers for PixGen generations.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.domains.pixgen.models import PixGenGeneration


def get_generation(db: Session, generation_id: UUID, user_id: UUID) -> PixGenGeneration | None:
    return (
        db.query(PixGenGeneration)
        .filter(PixGenGeneration.id == generation_id, PixGenGeneration.user_id == user_id)
        .first()
    )


def delete_generation(db: Session, generation_id: UUID, user_id: UUID) -> bool:
    row = get_generation(db, generation_id, user_id)
    if not row:
        return False
    db.delete(row)
    db.commit()
    return True

