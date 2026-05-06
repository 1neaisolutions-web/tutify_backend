"""
Teacher Intelligence API routes.
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domains.auth.dependencies import get_current_user
from app.domains.auth.models import User
from app.domains.teacher_intelligence import schemas
from app.domains.teacher_intelligence.services import (
    CTPAssemblerService,
    FeatureSnapshotService,
    MLOutputService,
)

router = APIRouter(prefix="/api/v1/teacher-intelligence", tags=["teacher-intelligence"])


@router.post("/assemble", response_model=schemas.CTPAssembled)
def assemble_ctp(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Build Comprehensive Teacher Profile for the current user."""
    service = CTPAssemblerService(db)
    ctp = service.assemble(current_user.id)
    return schemas.CTPAssembled(
        teacher_id=UUID(ctp["teacher_id"]),
        profile_version=ctp["profile_version"],
        identity=schemas.CTPIdentity(**ctp["identity"]),
        environment=schemas.CTPEnvironment(**ctp["environment"]),
        career=schemas.CTPCareer(**ctp["career"]),
        goals=ctp["goals"],
    )


@router.post("/feature-snapshot", response_model=schemas.FeatureSnapshotResponse, status_code=status.HTTP_201_CREATED)
def generate_feature_snapshot(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate latest ML-ready feature snapshot for the current user."""
    service = FeatureSnapshotService(db)
    snapshot = service.generate_snapshot(current_user.id)
    return snapshot


@router.get("/feature-snapshot/latest", response_model=schemas.FeatureSnapshotResponse)
def get_latest_feature_snapshot(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get the latest feature snapshot for the current user."""
    service = FeatureSnapshotService(db)
    snapshot = service.get_latest(current_user.id)
    if not snapshot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No feature snapshot found. Generate one via POST /feature-snapshot first.",
        )
    return snapshot


@router.post("/ml-output", response_model=schemas.MLOutputResponse, status_code=status.HTTP_201_CREATED)
def save_ml_output(
    body: schemas.MLOutputSaveRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Save ML pipeline output (used by ML pipeline service)."""
    service = MLOutputService(db)
    output = service.save_output(
        teacher_id=current_user.id,
        pipeline_name=body.pipeline_name,
        pipeline_version=body.pipeline_version,
        model_version=body.model_version,
        results=body.results,
        feature_snapshot_id=body.feature_snapshot_id,
        confidence_score=body.confidence_score,
    )
    return output


@router.get("/ml-output/latest", response_model=schemas.MLOutputResponse)
def get_latest_ml_output(
    pipeline_name: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get the latest ML output for the current user, optionally for a specific pipeline."""
    service = MLOutputService(db)
    output = service.get_latest(current_user.id, pipeline_name=pipeline_name)
    if not output:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No ML output found.",
        )
    return output
