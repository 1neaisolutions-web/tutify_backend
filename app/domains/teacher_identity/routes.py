"""
Teacher Identity API routes.
"""
from typing import List
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domains.auth.dependencies import get_current_user
from app.domains.auth.models import User
from app.domains.teacher_identity import schemas
from app.domains.teacher_identity.services import (
    ExperienceService,
    EducationService,
    CertificationService,
    AchievementService,
    CareerDocumentService,
)
from app.domains.personalization.schemas import PersonalizationSyncReceipt
from app.domains.personalization.services.personalization_sync_service import (
    build_full_snapshot,
    enqueue_sync_with_db,
)
from app.domains.teacher_identity.enums import CareerDocumentType
from app.domains.teacher_identity.services.career_document_service import (
    CareerDocumentServiceError,
)

router = APIRouter(prefix="/api/v1/teacher-identity", tags=["teacher-identity"])


def _enqueue_identity_personalization_sync(
    db: Session,
    background_tasks: BackgroundTasks,
    user_id: UUID,
    snapshot_before: dict,
    trigger: str,
) -> PersonalizationSyncReceipt:
    """Compare pre-mutation snapshot to current DB state and enqueue personalization work."""
    new_snap = build_full_snapshot(db, user_id)
    raw = enqueue_sync_with_db(
        background_tasks,
        db,
        user_id,
        snapshot_before,
        new_snap,
        trigger=trigger,
    )
    return PersonalizationSyncReceipt(**raw)


def _parse_document_type(value: str) -> CareerDocumentType:
    """Parse document type from form string."""
    try:
        return CareerDocumentType(value.strip().lower())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid document_type. Must be one of: {[e.value for e in CareerDocumentType]}",
        )


# ---------- Experience ----------
@router.get("/experience", response_model=List[schemas.ExperienceResponse])
async def list_experience(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all experience records for the current user."""
    service = ExperienceService(db)
    items = service.list_experience(current_user.id)
    return items


@router.get("/experience/{id}", response_model=schemas.ExperienceResponse)
async def get_experience(
    id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a single experience record."""
    service = ExperienceService(db)
    item = service.get_experience(id, current_user.id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Experience not found")
    return item


@router.post("/experience", response_model=schemas.ExperienceResponse, status_code=status.HTTP_201_CREATED)
async def create_experience(
    data: schemas.ExperienceCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create an experience record."""
    pre = build_full_snapshot(db, current_user.id)
    service = ExperienceService(db)
    item = service.create_experience(current_user.id, data)
    sync = _enqueue_identity_personalization_sync(
        db, background_tasks, current_user.id, pre, "teacher_identity_experience_create"
    )
    d = schemas.ExperienceResponse.model_validate(item).model_dump()
    d["personalization_sync"] = sync
    return schemas.ExperienceResponse(**d)


@router.put("/experience/{id}", response_model=schemas.ExperienceResponse)
async def update_experience(
    id: UUID,
    data: schemas.ExperienceUpdate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update an experience record."""
    pre = build_full_snapshot(db, current_user.id)
    service = ExperienceService(db)
    item = service.update_experience(id, current_user.id, data)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Experience not found")
    sync = _enqueue_identity_personalization_sync(
        db, background_tasks, current_user.id, pre, "teacher_identity_experience_update"
    )
    d = schemas.ExperienceResponse.model_validate(item).model_dump()
    d["personalization_sync"] = sync
    return schemas.ExperienceResponse(**d)


@router.delete("/experience/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_experience(
    id: UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete an experience record."""
    pre = build_full_snapshot(db, current_user.id)
    service = ExperienceService(db)
    if not service.delete_experience(id, current_user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Experience not found")
    _enqueue_identity_personalization_sync(
        db, background_tasks, current_user.id, pre, "teacher_identity_experience_delete"
    )


# ---------- Education ----------
@router.get("/education", response_model=List[schemas.EducationResponse])
async def list_education(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all education records for the current user."""
    service = EducationService(db)
    return service.list_education(current_user.id)


@router.get("/education/{id}", response_model=schemas.EducationResponse)
async def get_education(
    id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a single education record."""
    service = EducationService(db)
    item = service.get_education(id, current_user.id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Education not found")
    return item


@router.post("/education", response_model=schemas.EducationResponse, status_code=status.HTTP_201_CREATED)
async def create_education(
    data: schemas.EducationCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create an education record."""
    pre = build_full_snapshot(db, current_user.id)
    service = EducationService(db)
    item = service.create_education(current_user.id, data)
    sync = _enqueue_identity_personalization_sync(
        db, background_tasks, current_user.id, pre, "teacher_identity_education_create"
    )
    d = schemas.EducationResponse.model_validate(item).model_dump()
    d["personalization_sync"] = sync
    return schemas.EducationResponse(**d)


@router.put("/education/{id}", response_model=schemas.EducationResponse)
async def update_education(
    id: UUID,
    data: schemas.EducationUpdate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update an education record."""
    pre = build_full_snapshot(db, current_user.id)
    service = EducationService(db)
    item = service.update_education(id, current_user.id, data)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Education not found")
    sync = _enqueue_identity_personalization_sync(
        db, background_tasks, current_user.id, pre, "teacher_identity_education_update"
    )
    d = schemas.EducationResponse.model_validate(item).model_dump()
    d["personalization_sync"] = sync
    return schemas.EducationResponse(**d)


@router.delete("/education/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_education(
    id: UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete an education record."""
    pre = build_full_snapshot(db, current_user.id)
    service = EducationService(db)
    if not service.delete_education(id, current_user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Education not found")
    _enqueue_identity_personalization_sync(
        db, background_tasks, current_user.id, pre, "teacher_identity_education_delete"
    )


# ---------- Certifications ----------
@router.get("/certifications", response_model=List[schemas.CertificationResponse])
async def list_certifications(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all certification records for the current user."""
    service = CertificationService(db)
    return service.list_certifications(current_user.id)


@router.get("/certifications/{id}", response_model=schemas.CertificationResponse)
async def get_certification(
    id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a single certification record."""
    service = CertificationService(db)
    item = service.get_certification(id, current_user.id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Certification not found")
    return item


@router.post("/certifications", response_model=schemas.CertificationResponse, status_code=status.HTTP_201_CREATED)
async def create_certification(
    data: schemas.CertificationCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a certification record."""
    pre = build_full_snapshot(db, current_user.id)
    service = CertificationService(db)
    item = service.create_certification(current_user.id, data)
    sync = _enqueue_identity_personalization_sync(
        db, background_tasks, current_user.id, pre, "teacher_identity_certification_create"
    )
    d = schemas.CertificationResponse.model_validate(item).model_dump()
    d["personalization_sync"] = sync
    return schemas.CertificationResponse(**d)


@router.put("/certifications/{id}", response_model=schemas.CertificationResponse)
async def update_certification(
    id: UUID,
    data: schemas.CertificationUpdate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a certification record."""
    pre = build_full_snapshot(db, current_user.id)
    service = CertificationService(db)
    item = service.update_certification(id, current_user.id, data)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Certification not found")
    sync = _enqueue_identity_personalization_sync(
        db, background_tasks, current_user.id, pre, "teacher_identity_certification_update"
    )
    d = schemas.CertificationResponse.model_validate(item).model_dump()
    d["personalization_sync"] = sync
    return schemas.CertificationResponse(**d)


@router.delete("/certifications/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_certification(
    id: UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a certification record."""
    pre = build_full_snapshot(db, current_user.id)
    service = CertificationService(db)
    if not service.delete_certification(id, current_user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Certification not found")
    _enqueue_identity_personalization_sync(
        db, background_tasks, current_user.id, pre, "teacher_identity_certification_delete"
    )


# ---------- Achievements ----------
@router.get("/achievements", response_model=List[schemas.AchievementResponse])
async def list_achievements(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all achievement records for the current user."""
    service = AchievementService(db)
    return service.list_achievements(current_user.id)


@router.get("/achievements/{id}", response_model=schemas.AchievementResponse)
async def get_achievement(
    id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a single achievement record."""
    service = AchievementService(db)
    item = service.get_achievement(id, current_user.id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Achievement not found")
    return item


@router.post("/achievements", response_model=schemas.AchievementResponse, status_code=status.HTTP_201_CREATED)
async def create_achievement(
    data: schemas.AchievementCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create an achievement record."""
    pre = build_full_snapshot(db, current_user.id)
    service = AchievementService(db)
    item = service.create_achievement(current_user.id, data)
    sync = _enqueue_identity_personalization_sync(
        db, background_tasks, current_user.id, pre, "teacher_identity_achievement_create"
    )
    d = schemas.AchievementResponse.model_validate(item).model_dump()
    d["personalization_sync"] = sync
    return schemas.AchievementResponse(**d)


@router.put("/achievements/{id}", response_model=schemas.AchievementResponse)
async def update_achievement(
    id: UUID,
    data: schemas.AchievementUpdate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update an achievement record."""
    pre = build_full_snapshot(db, current_user.id)
    service = AchievementService(db)
    item = service.update_achievement(id, current_user.id, data)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Achievement not found")
    sync = _enqueue_identity_personalization_sync(
        db, background_tasks, current_user.id, pre, "teacher_identity_achievement_update"
    )
    d = schemas.AchievementResponse.model_validate(item).model_dump()
    d["personalization_sync"] = sync
    return schemas.AchievementResponse(**d)


@router.delete("/achievements/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_achievement(
    id: UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete an achievement record."""
    pre = build_full_snapshot(db, current_user.id)
    service = AchievementService(db)
    if not service.delete_achievement(id, current_user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Achievement not found")
    _enqueue_identity_personalization_sync(
        db, background_tasks, current_user.id, pre, "teacher_identity_achievement_delete"
    )


# ---------- Career documents ----------
@router.post(
    "/documents/upload",
    response_model=schemas.CareerDocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_career_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    document_type: str = Form(...),
    title: str | None = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload a career document (CV, resume, portfolio, etc.)."""
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No file provided",
        )
    pre = build_full_snapshot(db, current_user.id)
    doc_type = _parse_document_type(document_type)
    file_content = await file.read()
    service = CareerDocumentService(db)
    try:
        document = service.upload_document(
            user_id=current_user.id,
            file_content=file_content,
            file_name=file.filename,
            mime_type=file.content_type or "application/octet-stream",
            document_type=doc_type,
            title=title,
        )
    except CareerDocumentServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    sync = _enqueue_identity_personalization_sync(
        db, background_tasks, current_user.id, pre, "teacher_identity_career_document_upload"
    )
    d = schemas.CareerDocumentResponse.model_validate(document).model_dump()
    d["personalization_sync"] = sync
    return schemas.CareerDocumentResponse(**d)


@router.get("/documents", response_model=List[schemas.CareerDocumentListItem])
async def list_career_documents(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all career documents for the current user."""
    service = CareerDocumentService(db)
    return service.list_documents(current_user.id)


@router.get("/documents/{id}", response_model=schemas.CareerDocumentResponse)
async def get_career_document(
    id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a single career document by id."""
    service = CareerDocumentService(db)
    item = service.get_document(id, current_user.id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return item


@router.delete("/documents/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_career_document(
    id: UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a career document and its file."""
    pre = build_full_snapshot(db, current_user.id)
    service = CareerDocumentService(db)
    if not service.delete_document(id, current_user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    _enqueue_identity_personalization_sync(
        db, background_tasks, current_user.id, pre, "teacher_identity_career_document_delete"
    )
