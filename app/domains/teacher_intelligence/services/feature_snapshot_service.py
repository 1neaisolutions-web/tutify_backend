"""
Feature Snapshot: build ML-ready features from CTP and persist snapshots.
"""
import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.domains.teacher_intelligence.models import TeacherFeatureSnapshot
from app.domains.teacher_intelligence.services.ctp_assembler_service import CTPAssemblerService
from app.domains.teacher_intelligence.enums import FeatureSchemaVersion
from app.core.logging import get_logger

logger = get_logger(__name__)

FEATURE_SCHEMA_VERSION = FeatureSchemaVersion.V1.value


def _normalize_degree_to_level(degree: Optional[str]) -> str:
    """Map degree string to education_level bucket."""
    if not degree:
        return "unknown"
    d = (degree or "").strip().lower()
    if "phd" in d or "doctoral" in d or "doctorate" in d:
        return "doctoral"
    if "master" in d or "ms " in d or "ma " in d or "m.ed" in d or "mba" in d:
        return "masters"
    if "bachelor" in d or "ba " in d or "bs " in d or "b.ed" in d:
        return "bachelors"
    if "associate" in d or "a.a" in d:
        return "associate"
    return "other"


def _ctp_to_features(ctp: Dict[str, Any]) -> Dict[str, Any]:
    """Transform CTP dict into ML-ready feature dict. Normalize and bucket."""
    identity = ctp.get("identity") or {}
    environment = ctp.get("environment") or {}
    career = ctp.get("career") or {}

    country = (identity.get("country") or "").strip() or "unknown"
    region = (identity.get("region") or "").strip() or "unknown"
    subjects = identity.get("subjects") or []
    subject_primary = subjects[0] if subjects else "unknown"
    grade_band = (identity.get("grade_band") or "").strip() or "unknown"
    curriculum_framework = (environment.get("curriculum_framework") or "").strip() or "unknown"
    years_experience_bucket = (environment.get("years_experience") or "").strip() or "unknown"
    school_type = (environment.get("school_type") or "").strip() or "unknown"

    experience_records = career.get("experience_records") or 0
    certifications_count = career.get("certifications_count") or 0
    education_count = career.get("education_count") or 0
    education_level = _normalize_degree_to_level(career.get("highest_degree"))

    features = {
        "country": country,
        "region": region,
        "subject_primary": subject_primary,
        "grade_band": grade_band,
        "curriculum_framework": curriculum_framework,
        "years_experience_bucket": years_experience_bucket,
        "certifications_count": certifications_count,
        "education_level": education_level,
        "experience_records": experience_records,
        "school_type": school_type,
        "has_resume": False,
        "has_portfolio": False,
    }

    document_types = career.get("document_types") or []
    features["has_resume"] = "resume" in document_types
    features["has_portfolio"] = "portfolio" in document_types
    return features


def _source_hash(ctp: Dict[str, Any]) -> str:
    """Deterministic hash of CTP for reproducibility."""
    canonical = json.dumps(ctp, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:128]


class FeatureSnapshotService:
    """Build and store ML-ready feature snapshots from CTP."""

    def __init__(self, db: Session):
        self.db = db

    def generate_snapshot(self, teacher_id: UUID) -> TeacherFeatureSnapshot:
        """
        Build CTP, transform to features, create new snapshot row, mark previous is_latest=False.
        """
        assembler = CTPAssemblerService(self.db)
        ctp = assembler.assemble(teacher_id)

        features = _ctp_to_features(ctp)
        source_hash_val = _source_hash(ctp)
        generated_at = datetime.now(timezone.utc)

        self.db.query(TeacherFeatureSnapshot).filter(
            TeacherFeatureSnapshot.teacher_id == teacher_id
        ).update({"is_latest": False})

        snapshot = TeacherFeatureSnapshot(
            teacher_id=teacher_id,
            feature_schema_version=FEATURE_SCHEMA_VERSION,
            source_hash=source_hash_val,
            generated_at=generated_at,
            features=features,
            is_latest=True,
        )
        self.db.add(snapshot)
        self.db.commit()
        self.db.refresh(snapshot)
        logger.info(
            "Feature snapshot generated id=%s teacher_id=%s schema=%s",
            snapshot.id,
            teacher_id,
            FEATURE_SCHEMA_VERSION,
        )
        return snapshot

    def get_latest(self, teacher_id: UUID) -> Optional[TeacherFeatureSnapshot]:
        """Get the latest feature snapshot for a teacher."""
        return (
            self.db.query(TeacherFeatureSnapshot)
            .filter(
                TeacherFeatureSnapshot.teacher_id == teacher_id,
                TeacherFeatureSnapshot.is_latest == True,
            )
            .first()
        )
