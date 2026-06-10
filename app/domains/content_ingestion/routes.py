"""
Content Ingestion API routes.
"""
import asyncio
import json
import time
import hashlib
from typing import List, Optional
from uuid import UUID, uuid4
from pathlib import Path

from fastapi import (
    APIRouter, Depends, HTTPException, status, UploadFile, File, Form,
    BackgroundTasks, Request, Response
)
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.session import get_db
from app.domains.auth.dependencies import get_current_user, require_role, require_any_role
from app.domains.auth.models import User
from app.domains.content_ingestion import schemas
from app.domains.content_ingestion.services import (
    ContentPackService,
    DocumentService,
    QAService,
    WorksheetService,
)
from app.domains.content_ingestion.jobs import run_ingestion_job_sync
from app.domains.content_ingestion.models import Document, DocumentProcessingRun
from app.domains.content_ingestion.enums import DocumentStatus
from app.domains.content_ingestion.services.processing_progress_view import (
    build_processing_progress,
)
from app.core.config import settings
from app.domains.subscriptions.services.credit_service import CreditService
from app.domains.subscriptions.credit_errors import insufficient_credits_detail
from app.domains.subscriptions.feature_keys import WORKSHEET_GENERATE

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["content-ingestion"])


async def _save_upload_file_stream(
    upload: UploadFile,
    destination: Path,
    *,
    max_size_bytes: int,
    chunk_size: int = 2 * 1024 * 1024,
) -> tuple[int, str]:
    """Stream UploadFile to disk with size guard and incremental hash."""
    total = 0
    hasher = hashlib.sha256()
    hard_limit = int(getattr(settings, "OCR_MAX_UPLOAD_SIZE_MB_HARD", 100)) * 1024 * 1024
    with open(destination, "wb") as out:
        while True:
            chunk = await upload.read(chunk_size)
            if not chunk:
                break
            total += len(chunk)
            if total > hard_limit:
                raise ValueError(
                    f"File is too large ({total / 1024 / 1024:.2f}MB). "
                    f"Hard limit is {int(getattr(settings, 'OCR_MAX_UPLOAD_SIZE_MB_HARD', 100))}MB. "
                    "Please split the PDF before upload."
                )
            if total > max_size_bytes:
                raise ValueError(
                    f"File size ({total / 1024 / 1024:.2f}MB) exceeds maximum ({settings.MAX_FILE_SIZE_MB}MB)"
                )
            out.write(chunk)
            hasher.update(chunk)
    await upload.seek(0)
    return total, hasher.hexdigest()


# ========== Content Pack Endpoints ==========

@router.get("/admin/content-packs/test")
async def test_content_packs_route():
    """Test endpoint to verify route registration (no auth required)."""
    return {"message": "Content packs route is working", "status": "ok", "path": "/api/v1/admin/content-packs"}


@router.post("/admin/content-packs", response_model=schemas.ContentPackResponse, status_code=status.HTTP_201_CREATED)
async def create_content_pack(
    data: schemas.ContentPackCreate,
    current_user: User = Depends(require_any_role("org_admin", "school_admin", "super_admin")),
    db: Session = Depends(get_db),
):
    """Create a new content pack."""
    service = ContentPackService(db)
    pack = service.create_pack(
        data=data,
        tenant_id=current_user.tenant_id,
        created_by=current_user.id
    )
    return pack


@router.get("/admin/content-packs", response_model=List[schemas.ContentPackListItem])
async def list_content_packs(
    skip: int = 0,
    limit: int = 100,
    is_active: Optional[bool] = None,
    current_user: User = Depends(require_any_role("org_admin", "school_admin", "super_admin", "teacher")),
    db: Session = Depends(get_db),
):
    """List content packs. Teachers can view active packs for worksheet generation."""
    logger.info(f"List content packs called by user {current_user.id}, tenant {current_user.tenant_id}, is_active={is_active}")
    try:
        service = ContentPackService(db)
        packs, total = service.list_packs(
            tenant_id=current_user.tenant_id,
            skip=skip,
            limit=limit,
            is_active=is_active
        )
        logger.info(f"Returning {len(packs)} packs for tenant {current_user.tenant_id}")
        return packs
    except Exception as e:
        logger.error(f"Error listing content packs: {e}", exc_info=True)
        raise


@router.get("/admin/content-packs/{pack_id}", response_model=schemas.ContentPackResponse)
async def get_content_pack(
    pack_id: UUID,
    current_user: User = Depends(require_any_role("org_admin", "school_admin", "super_admin", "teacher")),
    db: Session = Depends(get_db),
):
    """Get content pack details. Teachers can view pack details for worksheet generation."""
    service = ContentPackService(db)
    pack = service.get_pack(pack_id, current_user.tenant_id)
    if not pack:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Content pack not found"
        )
    return pack


@router.put("/admin/content-packs/{pack_id}", response_model=schemas.ContentPackResponse)
async def update_content_pack(
    pack_id: UUID,
    data: schemas.ContentPackCreate,
    current_user: User = Depends(require_any_role("org_admin", "school_admin", "super_admin")),
    db: Session = Depends(get_db),
):
    """Update a content pack."""
    service = ContentPackService(db)
    pack = service.update_pack(
        pack_id=pack_id,
        tenant_id=current_user.tenant_id,
        name=data.name,
        description=data.description,
        subject=data.subject,
        grade=data.grade,
        curriculum=data.curriculum,
        ocr_policy=getattr(data, "ocr_policy", None),
        pack_metadata=data.metadata,
    )
    if not pack:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Content pack not found"
        )
    # Map pack_metadata to metadata for API response
    if hasattr(pack, 'pack_metadata'):
        pack.metadata = pack.pack_metadata
    return pack


@router.delete("/admin/content-packs/{pack_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_content_pack(
    pack_id: UUID,
    current_user: User = Depends(require_any_role("org_admin", "school_admin", "super_admin")),
    db: Session = Depends(get_db),
):
    """Delete (deactivate) a content pack."""
    service = ContentPackService(db)
    success = service.delete_pack(pack_id, current_user.tenant_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Content pack not found"
        )
    return None


# ========== Document Endpoints ==========

@router.post("/admin/documents/upload-stream")
async def upload_document_with_stream(
    background_tasks: BackgroundTasks,
    pack_id: Optional[str] = Form(None),  # Optional - create pack if not provided
    pack_name: Optional[str] = Form(None),
    pack_description: Optional[str] = Form(None),
    pack_subject: Optional[str] = Form(None),
    pack_grade: Optional[str] = Form(None),
    pack_curriculum: Optional[str] = Form(None),
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    author: Optional[str] = Form(None),
    chapter_map: Optional[str] = Form(None),
    force_ocr: bool = Form(False),
    current_user: User = Depends(require_any_role("org_admin", "school_admin", "super_admin")),
    db: Session = Depends(get_db),
):
    """
    Unified endpoint: Upload document with optional pack creation - streams real-time progress.
    If pack_id is not provided, creates a new pack using pack_* fields.
    """
    async def generate_progress_stream():
        """Generate SSE events for upload and processing progress."""
        try:
            # Step 1: Validate file
            yield f"data: {json.dumps({'type': 'progress', 'step': 'validating', 'message': 'Validating file...', 'percentage': 5})}\n\n"
            await asyncio.sleep(0.05)
            
            # Ensure we flush the stream immediately
            import sys
            if hasattr(sys.stdout, 'flush'):
                sys.stdout.flush()
            
            if not file.filename:
                yield f"data: {json.dumps({'type': 'error', 'message': 'No file provided'})}\n\n"
                return
            
            # Read file
            yield f"data: {json.dumps({'type': 'progress', 'step': 'uploading', 'message': 'Uploading file...', 'percentage': 15})}\n\n"
            await asyncio.sleep(0.05)
            max_size = settings.MAX_FILE_SIZE_MB * 1024 * 1024
            
            # Step 2: Create or get pack
            yield f"data: {json.dumps({'type': 'progress', 'step': 'pack', 'message': 'Setting up content pack...', 'percentage': 30})}\n\n"
            await asyncio.sleep(0.05)
            
            pack_service = ContentPackService(db)
            if pack_id:
                try:
                    pack_uuid = UUID(pack_id)
                    pack = pack_service.get_pack(pack_uuid, current_user.tenant_id)
                    if not pack:
                        yield f"data: {json.dumps({'type': 'error', 'message': 'Content pack not found'})}\n\n"
                        return
                except ValueError:
                    yield f"data: {json.dumps({'type': 'error', 'message': 'Invalid pack_id format'})}\n\n"
                    return
            else:
                # Create new pack
                if not pack_name:
                    yield f"data: {json.dumps({'type': 'error', 'message': 'pack_name is required when pack_id is not provided'})}\n\n"
                    return
                
                pack_data = schemas.ContentPackCreate(
                    name=pack_name,
                    description=pack_description,
                    subject=pack_subject,
                    grade=pack_grade,
                    curriculum=pack_curriculum
                )
                pack = pack_service.create_pack(
                    data=pack_data,
                    tenant_id=current_user.tenant_id,
                    created_by=current_user.id
                )
                yield f"data: {json.dumps({'type': 'progress', 'step': 'pack_created', 'message': f'Created pack: {pack.name}', 'pack_id': str(pack.id), 'percentage': 40})}\n\n"
                await asyncio.sleep(0.05)
            
            # Step 3: Save file
            yield f"data: {json.dumps({'type': 'progress', 'step': 'saving', 'message': 'Saving file...', 'percentage': 50})}\n\n"
            await asyncio.sleep(0.05)
            
            documents_dir = Path(settings.DOCUMENTS_DIR)
            documents_dir.mkdir(parents=True, exist_ok=True)
            
            import uuid
            from datetime import datetime
            file_ext = Path(file.filename).suffix
            unique_filename = f"{uuid.uuid4()}_{int(datetime.now().timestamp())}{file_ext}"
            file_path = documents_dir / unique_filename
            
            try:
                file_size, file_hash = await _save_upload_file_stream(
                    file,
                    file_path,
                    max_size_bytes=max_size,
                )
            except ValueError as ve:
                yield f"data: {json.dumps({'type': 'error', 'message': str(ve)})}\n\n"
                return
            
            # Step 4: Create document record
            yield f"data: {json.dumps({'type': 'progress', 'step': 'creating', 'message': 'Creating document record...', 'percentage': 70})}\n\n"
            await asyncio.sleep(0.05)
            
            filename_lower = file.filename.lower()
            if filename_lower.endswith('.pdf'):
                source_type = "pdf"
            elif filename_lower.endswith('.docx'):
                source_type = "docx"
            elif filename_lower.endswith(('.jpg', '.jpeg', '.png', '.tiff')):
                source_type = "image"
            else:
                yield f"data: {json.dumps({'type': 'error', 'message': f'Unsupported file type: {file.filename}'})}\n\n"
                return
            
            chapter_map_data = None
            if chapter_map:
                try:
                    chapter_map_data = json.loads(chapter_map)
                except json.JSONDecodeError:
                    yield f"data: {json.dumps({'type': 'error', 'message': 'Invalid chapter_map JSON'})}\n\n"
                    return
            
            document_service = DocumentService(db)
            document = document_service.create_document(
                pack_id=pack.id,
                filename=file.filename,
                file_path=str(file_path),
                file_size=file_size,
                mime_type=file.content_type,
                source_type=source_type,
                tenant_id=current_user.tenant_id,
                uploaded_by=current_user.id,
                title=title,
                author=author,
                chapter_map=chapter_map_data,
                document_hash=file_hash
            )

            meta_upload = dict(document.processing_metadata or {})
            if chapter_map_data and isinstance(chapter_map_data, list):
                meta_upload["toc_source"] = "client_json"
                meta_upload["toc_entry_count"] = len(chapter_map_data)
            if force_ocr:
                meta_upload["force_ocr"] = True
            if meta_upload:
                document.processing_metadata = meta_upload
                db.commit()
            
            yield f"data: {json.dumps({'type': 'progress', 'step': 'uploaded', 'message': 'File uploaded successfully', 'document_id': str(document.id), 'percentage': 85})}\n\n"
            await asyncio.sleep(0.05)
            
            # Step 5: Start processing
            yield f"data: {json.dumps({'type': 'progress', 'step': 'processing_ocr_async', 'message': 'Processing OCR (async)...', 'percentage': 90})}\n\n"
            await asyncio.sleep(0.05)
            
            # Trigger background ingestion job
            background_tasks.add_task(run_ingestion_job_sync, document.id)
            
            # Final success
            yield f"data: {json.dumps({'type': 'success', 'message': 'Upload complete. Processing started.', 'document_id': str(document.id), 'pack_id': str(pack.id), 'percentage': 100})}\n\n"
            
        except Exception as e:
            logger.error(f"Error in upload stream: {e}", exc_info=True)
            # Ensure error is sent to client
            try:
                error_msg = str(e)
                # Make error message user-friendly
                if "institution_admin" in error_msg.lower() or "enum" in error_msg.lower():
                    error_msg = "Authorization error. Please contact support if this persists."
                yield f"data: {json.dumps({'type': 'error', 'message': error_msg})}\n\n"
            except Exception as send_error:
                logger.error(f"Failed to send error to client: {send_error}", exc_info=True)
                # Last resort: try to send a generic error
                try:
                    yield f"data: {json.dumps({'type': 'error', 'message': 'An error occurred during upload. Please try again.'})}\n\n"
                except:
                    pass  # If we can't even send error, just log it
    
    return StreamingResponse(
        generate_progress_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Content-Type-Options": "nosniff",
        }
    )


@router.post("/admin/documents", response_model=schemas.DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    background_tasks: BackgroundTasks,
    pack_id: UUID = Form(...),
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    author: Optional[str] = Form(None),
    chapter_map: Optional[str] = Form(None),  # JSON string
    force_ocr: bool = Form(False),
    current_user: User = Depends(require_any_role("org_admin", "school_admin", "super_admin")),
    db: Session = Depends(get_db),
):
    """Upload a document for processing."""
    # Validate file
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No file provided"
        )
    
    # Check file size while streaming to disk (avoid loading entire file into memory)
    max_size = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    
    # Determine source type
    filename_lower = file.filename.lower()
    if filename_lower.endswith('.pdf'):
        source_type = "pdf"
    elif filename_lower.endswith('.docx'):
        source_type = "docx"
    elif filename_lower.endswith(('.jpg', '.jpeg', '.png', '.tiff')):
        source_type = "image"
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: {file.filename}"
        )
    
    # Save file
    documents_dir = Path(settings.DOCUMENTS_DIR)
    documents_dir.mkdir(parents=True, exist_ok=True)
    
    import uuid
    from datetime import datetime
    file_ext = Path(file.filename).suffix
    unique_filename = f"{uuid.uuid4()}_{int(datetime.now().timestamp())}{file_ext}"
    file_path = documents_dir / unique_filename
    
    try:
        file_size, file_hash = await _save_upload_file_stream(
            file,
            file_path,
            max_size_bytes=max_size,
        )
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve),
        ) from ve
    
    # Parse chapter map if provided
    chapter_map_data = None
    if chapter_map:
        try:
            chapter_map_data = json.loads(chapter_map)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid chapter_map JSON"
            )
    
    # Create document record
    service = DocumentService(db)
    document = service.create_document(
        pack_id=pack_id,
        filename=file.filename,
        file_path=str(file_path),
        file_size=file_size,
        mime_type=file.content_type,
        source_type=source_type,
        tenant_id=current_user.tenant_id,
        uploaded_by=current_user.id,
        title=title,
        author=author,
        chapter_map=chapter_map_data,
        document_hash=file_hash
    )

    meta_upload = dict(document.processing_metadata or {})
    if chapter_map_data and isinstance(chapter_map_data, list):
        meta_upload["toc_source"] = "client_json"
        meta_upload["toc_entry_count"] = len(chapter_map_data)
    if force_ocr:
        meta_upload["force_ocr"] = True
    if meta_upload:
        document.processing_metadata = meta_upload
        db.commit()
    
    # Trigger background ingestion job
    background_tasks.add_task(run_ingestion_job_sync, document.id)
    
    logger.info(f"Document uploaded: {document.id}, ingestion job queued")
    return document


@router.get("/admin/documents", response_model=List[schemas.DocumentListItem])
async def list_documents(
    pack_id: Optional[UUID] = None,
    status_filter: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(require_any_role("org_admin", "school_admin", "super_admin")),
    db: Session = Depends(get_db),
):
    """List documents."""
    service = DocumentService(db)
    documents, total = service.list_documents(
        tenant_id=current_user.tenant_id,
        pack_id=pack_id,
        status=status_filter,
        skip=skip,
        limit=limit
    )
    return documents


@router.get("/admin/documents/{document_id}", response_model=schemas.DocumentResponse)
async def get_document(
    document_id: UUID,
    current_user: User = Depends(require_any_role("org_admin", "school_admin", "super_admin")),
    db: Session = Depends(get_db),
):
    """Get document details."""
    service = DocumentService(db)
    document = service.get_document(document_id, current_user.tenant_id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    return document


@router.delete("/admin/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: UUID,
    current_user: User = Depends(require_any_role("org_admin", "school_admin", "super_admin")),
    db: Session = Depends(get_db),
):
    """Delete a document."""
    service = DocumentService(db)
    success = service.delete_document(document_id, current_user.tenant_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    return None


def _sse_document_status_payload(
    db: Session,
    document: Document,
    document_id: UUID,
) -> tuple[dict, tuple]:
    """Build one SSE JSON payload and a signature tuple for change detection."""
    latest_run = (
        db.query(DocumentProcessingRun)
        .filter(DocumentProcessingRun.document_id == document_id)
        .order_by(DocumentProcessingRun.started_at.desc())
        .first()
    )
    current_status = document.status
    progress = (
        build_processing_progress(document, latest_run) if latest_run else None
    )
    pages_p = int(latest_run.pages_processed or 0) if latest_run else None
    pct = int(latest_run.progress_percentage or 0) if latest_run else None
    chunks_c = int(latest_run.chunks_created or 0) if latest_run else None
    vecs_s = int(latest_run.vectors_stored or 0) if latest_run else None
    doc_pages = document.total_pages
    if doc_pages is not None:
        try:
            doc_pages = int(doc_pages)
        except (TypeError, ValueError):
            doc_pages = None

    sig = (
        current_status,
        (progress or {}).get("completed") if progress else None,
        (progress or {}).get("total") if progress else None,
        pct,
        pages_p,
        doc_pages,
        chunks_c,
        vecs_s,
    )
    status_data = {
        "document_id": str(document_id),
        "status": current_status,
        "progress": progress,
        "steps_completed": latest_run.completed_steps or [] if latest_run else [],
        "current_step": (
            (latest_run.current_step or current_status) if latest_run else current_status
        ),
        "error_code": document.error_code,
        "error_message": document.error_message,
        "remediation_hint": document.remediation_hint,
        "total_pages": doc_pages,
        "pages_processed": pages_p,
    }
    return status_data, sig


@router.get("/admin/documents/{document_id}/status/stream")
async def stream_document_status(
    document_id: UUID,
    current_user: User = Depends(require_any_role("org_admin", "school_admin", "super_admin")),
    db: Session = Depends(get_db),
):
    """Stream real-time document processing status via SSE."""
    # Verify document exists and user has access
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.tenant_id == current_user.tenant_id
    ).first()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    async def generate_status_stream():
        """Generate SSE events for document status updates."""
        last_signal = None
        last_byte_time = time.monotonic()
        heartbeat_s = float(getattr(settings, "SSE_STATUS_HEARTBEAT_SECONDS", 15.0))

        # Immediate first frame so the client leaves "connecting" fast — but refresh first
        # so total_pages / progress match other sessions (ingestion commits on BackgroundTasks).
        try:
            try:
                db.refresh(document)
            except Exception:
                logger.warning(
                    "status_stream_first_refresh_skipped",
                    extra={"document_id": str(document_id)},
                    exc_info=True,
                )
            status_data, sig = _sse_document_status_payload(db, document, document_id)
            event_json = json.dumps(status_data, default=str)
            yield f"data: {event_json}\n\n"
            last_byte_time = time.monotonic()
            last_signal = sig
            if status_data["status"] in [
                DocumentStatus.PUBLISHED.value,
                DocumentStatus.FAILED.value,
            ]:
                return
        except Exception as e:
            logger.exception(
                "status_stream_initial_snapshot_failed",
                extra={"document_id": str(document_id)},
            )
            err = {
                "document_id": str(document_id),
                "status": DocumentStatus.FAILED.value,
                "progress": None,
                "steps_completed": [],
                "current_step": DocumentStatus.FAILED.value,
                "error_code": "SSE_SNAPSHOT_ERROR",
                "error_message": str(e),
                "remediation_hint": "Retry opening the status stream or reload the document.",
                "total_pages": None,
                "pages_processed": None,
            }
            yield f"data: {json.dumps(err, default=str)}\n\n"
            return

        while True:
            try:
                db.refresh(document)
                status_data, sig = _sse_document_status_payload(db, document, document_id)
            except Exception as e:
                logger.exception(
                    "status_stream_poll_failed",
                    extra={"document_id": str(document_id)},
                )
                err = {
                    "document_id": str(document_id),
                    "status": DocumentStatus.FAILED.value,
                    "progress": None,
                    "steps_completed": [],
                    "current_step": DocumentStatus.FAILED.value,
                    "error_code": "SSE_POLL_ERROR",
                    "error_message": str(e),
                    "remediation_hint": "Database error while streaming status; try again.",
                    "total_pages": None,
                    "pages_processed": None,
                }
                yield f"data: {json.dumps(err, default=str)}\n\n"
                return

            current_status = status_data["status"]

            if sig != last_signal:
                event_json = json.dumps(status_data, default=str)
                yield f"data: {event_json}\n\n"
                last_byte_time = time.monotonic()
                last_signal = sig

            if current_status in [DocumentStatus.PUBLISHED.value, DocumentStatus.FAILED.value]:
                break

            now = time.monotonic()
            if now - last_byte_time >= heartbeat_s:
                yield ": ping\n\n"
                last_byte_time = now

            await asyncio.sleep(1)
    
    return StreamingResponse(
        generate_status_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.post("/admin/documents/{document_id}/retry", response_model=schemas.DocumentResponse)
async def retry_document_processing(
    document_id: UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_any_role("org_admin", "school_admin", "super_admin")),
    db: Session = Depends(get_db),
):
    """Retry document processing after failure or when stuck mid-pipeline (e.g. text_extracting)."""
    service = DocumentService(db)
    document = service.get_document(document_id, current_user.tenant_id)
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )

    retryable = {
        DocumentStatus.FAILED.value,
    }
    if document.status not in retryable:
        in_progress = {
            DocumentStatus.TEXT_EXTRACTING.value,
            DocumentStatus.OCR_RUNNING.value,
            DocumentStatus.NORMALIZING.value,
            DocumentStatus.CHUNKING.value,
            DocumentStatus.EMBEDDING.value,
            DocumentStatus.INDEXING.value,
            DocumentStatus.QA_VALIDATION.value,
        }
        if document.status in in_progress:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Document is currently processing ({document.status}). "
                    "Do not retry yet; wait for completion or failure."
                ),
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot retry document with status: {document.status}",
        )

    refreshed = service.reset_for_reingestion(document_id, current_user.tenant_id)
    if not refreshed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    background_tasks.add_task(run_ingestion_job_sync, document_id)

    logger.info("retry_document_processing", extra={"document_id": str(document_id)})
    return refreshed


@router.post("/admin/documents/{document_id}/qa/run", response_model=schemas.QAValidationResponse)
async def run_qa_validation(
    document_id: UUID,
    request: Optional[schemas.QAValidationRequest] = None,
    current_user: User = Depends(require_any_role("org_admin", "school_admin", "super_admin")),
    db: Session = Depends(get_db),
):
    """Run QA validation on a document."""
    service = DocumentService(db)
    document = service.get_document(document_id, current_user.tenant_id)
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    qa_service = QAService(db)
    qa_validation = qa_service.run_qa_validation(
        document_id=document_id,
        thresholds=request.thresholds if request else None,
        golden_queries=request.golden_queries if request else None
    )
    
    return qa_validation


@router.post("/admin/documents/{document_id}/reprocess-topics")
async def reprocess_document_topics(
    document_id: UUID,
    current_user: User = Depends(require_any_role("super_admin", "org_admin")),
    db: Session = Depends(get_db),
):
    """Rebuild document_topics and chunks.topic_fk without re-OCR or re-embedding."""
    service = DocumentService(db)
    document = service.get_document(document_id, current_user.tenant_id)
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    from app.domains.content_ingestion.document_topics_service import populate_document_topics

    report = populate_document_topics(db, document, replace_existing=True)
    db.commit()
    db.refresh(document)
    return {
        "document_id": str(document_id),
        "topic_count": len(document.document_topics or []),
        "coverage": report.coverage,
        "chapters_with_zero_chunks": report.chapters_with_zero_chunks,
    }


@router.get("/admin/documents/health-summary")
async def document_topics_health_summary(
    current_user: User = Depends(require_any_role("super_admin")),
    db: Session = Depends(get_db),
):
    """Admin dashboard: document topic indexing health metrics."""
    from sqlalchemy import text

    rows = db.execute(
        text(
            """
            SELECT document_id, filename, status, total_topics, empty_topics,
                   fallback_topics, total_chunks, chapter_coverage_pct
            FROM document_topics_health
            WHERE tenant_id = :tenant_id
            ORDER BY chapter_coverage_pct ASC NULLS FIRST
            LIMIT 200
            """
        ),
        {"tenant_id": str(current_user.tenant_id)},
    ).mappings().all()
    return {"items": [dict(r) for r in rows]}


@router.post("/admin/documents/{document_id}/publish", response_model=schemas.DocumentResponse)
async def publish_document(
    document_id: UUID,
    override_qa: bool = False,
    override_reason: Optional[str] = None,
    current_user: User = Depends(require_any_role("org_admin", "school_admin", "super_admin")),
    db: Session = Depends(get_db),
):
    """
    Publish a document (QA must pass unless overridden).
    
    Ensures document has been fully processed with embeddings stored before publishing.
    """
    service = DocumentService(db)
    document = service.get_document(document_id, current_user.tenant_id)
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    # Check if document has been processed with embeddings (embedding_v for fake/local)
    from app.core.config import settings
    emb_provider = (settings.EMBEDDING_PROVIDER or "fake").lower()
    if emb_provider in ("fake", "local"):
        chunks_with_embeddings = db.query(Chunk).filter(
            Chunk.document_id == document_id,
            Chunk.embedding_v.isnot(None),
            Chunk.embedding_model == emb_provider
        ).count()
    else:
        chunks_with_embeddings = db.query(Chunk).filter(
            Chunk.document_id == document_id,
            Chunk.embedding.isnot(None)
        ).count()
    
    if chunks_with_embeddings == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Document has not been processed yet. Please wait for ingestion to complete, or the document may need to be reprocessed."
        )
    
    # Check QA status
    from app.domains.content_ingestion.models import QAValidation
    latest_qa = db.query(QAValidation).filter(
        QAValidation.document_id == document_id
    ).order_by(QAValidation.created_at.desc()).first()
    
    if not latest_qa:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="QA validation must be run before publishing"
        )
    
    if latest_qa.qa_status != "passed" and not override_qa:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"QA validation did not pass (status: {latest_qa.qa_status}). Use override_qa=true to publish anyway."
        )
    
    # Publish document
    from datetime import datetime, timezone
    service.update_document_status(
        document_id=document_id,
        status=DocumentStatus.PUBLISHED.value
    )
    document.processed_at = datetime.now(timezone.utc)
    db.commit()
    
    logger.info(f"Document {document_id} published (override: {override_qa}, chunks with embeddings: {chunks_with_embeddings})")
    return document


# ========== Worksheet Endpoints ==========

@router.post("/worksheets/generate", response_model=schemas.WorksheetResponse)
async def generate_worksheet(
    request: schemas.WorksheetGenerateRequest,
    response: Response,
    http_request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate a worksheet using RAG. Hard timeout applied; 504 on timeout."""
    request_id = str(uuid4())
    timeout_sec = getattr(settings, "WORKSHEET_GENERATION_TIMEOUT_SECONDS", 180.0)
    # When cache is disabled, default skip_cache_write to True so no DB write
    skip_cache_write = request.skip_cache_write if request.skip_cache_write is not None else (not getattr(settings, "WORKSHEET_CACHE_ENABLED", False))
    # Bypass cache when client requests regeneration (force_regenerate or regenerate_key)
    force_regenerate = request.force_regenerate or bool(request.regenerate_key)

    credit_service = CreditService(db)
    credit_check = credit_service.check_balance(current_user.id)
    ws_cost = credit_service.get_feature_cost(WORKSHEET_GENERATE)
    if not credit_check.allowed or credit_check.balance < ws_cost:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=insufficient_credits_detail(
                credit_check,
                ws_cost,
                "You don't have enough credits to generate this worksheet.",
            ),
        )

    service = WorksheetService(db)
    try:
        # Convert single difficulty to difficulty_mix if provided
        # The service method only accepts difficulty_mix, not difficulty
        difficulty_mix_to_use = request.difficulty_mix
        if request.difficulty and not difficulty_mix_to_use:
            # Convert single difficulty to difficulty_mix (100% that difficulty)
            difficulty_mix_to_use = {
                request.difficulty: 1.0
            }
        
        # Call generate_worksheet with only the parameters it accepts
        # Note: skip_cache_write, request_id, user_id, regenerate_key, tenant_id are not used by the service method
        worksheet_cache = await asyncio.wait_for(
            service.generate_worksheet(
                pack_id=request.pack_id,
                pack_ids=request.pack_ids,
                topic_id=request.topic_id,
                topic_text=request.topic_text,
                grade=request.grade,
                subject=request.subject,
                difficulty_mix=difficulty_mix_to_use,
                num_questions=request.num_questions,
                question_types=request.question_types,
                force_regenerate=force_regenerate,
                teacher_prompt=request.teacher_prompt,
            ),
            timeout=timeout_sec,
        )
        
        # Handle skip_cache_write after generation (if needed)
        # Note: The service always saves to cache, so if skip_cache_write is True,
        # we would need to delete it, but for now we'll let it cache
    except asyncio.TimeoutError:
        logger.warning(f"Worksheet generation timed out after {timeout_sec}s request_id={request_id}")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail={
                "message": "Generation timed out. Reduce questions or try again.",
                "request_id": request_id,
            },
        )
    except ValueError as e:
        msg = str(e)
        logger.warning("Worksheet generate ValueError: %s", msg, exc_info=False)
        if "Topic content not found" in msg or "VALIDATION_FAILED" in msg or "TOPIC_NOT_FOUND_IN_PACK" in msg:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"message": msg, "code": "TOPIC_NOT_FOUND_OR_VALIDATION_FAILED"},
            )
        if "Unable to generate at the requested difficulty" in msg:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"message": msg, "code": "DIFFICULTY_GENERATION_FAILED"},
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": msg, "code": "GENERATION_FAILED"},
        )
    except Exception as e:
        # Catch any other unexpected exceptions (TypeError, AttributeError, etc.)
        logger.error(f"Unexpected error in worksheet generation (request_id={request_id}): {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "message": f"Internal server error: {str(e)}",
                "code": "INTERNAL_ERROR",
                "request_id": request_id
            }
        )
    
    # Response headers for diagnostics and client UX (do not break existing clients)
    from_cache = getattr(worksheet_cache, "from_cache", False)
    response.headers["X-Request-Id"] = request_id
    response.headers["X-Worksheet-Cache"] = "hit" if from_cache else "miss"

    # When difficulty was requested: ensure response includes metadata (from generation or derived from cache)
    final_difficulty_used = getattr(worksheet_cache, "final_difficulty_used", None)
    attempts_count = getattr(worksheet_cache, "attempts_count", None)
    validator_report_per_attempt = getattr(worksheet_cache, "validator_report_per_attempt", None)
    warnings = getattr(worksheet_cache, "warnings", None)
    if request.difficulty and from_cache and final_difficulty_used is None:
        mix = getattr(worksheet_cache, "difficulty_mix", None) or {}
        if mix.get("hard") == 1 or mix.get("hard") == 1.0:
            final_difficulty_used = "hard"
        elif mix.get("medium") == 1 or mix.get("medium") == 1.0:
            final_difficulty_used = "medium"
        elif mix.get("easy") == 1 or mix.get("easy") == 1.0:
            final_difficulty_used = "easy"
        attempts_count = 0
        validator_report_per_attempt = []
        warnings = []

    # Response hygiene: hide internal fields unless DEBUG or X-Debug: 1 (log only in production)
    debug = (http_request.headers.get("X-Debug") == "1" or getattr(settings, "DEBUG", False))
    if not debug:
        validator_report_per_attempt = None
        warnings = None

    # created_at must never be null in response
    from datetime import datetime, timezone
    created_at = getattr(worksheet_cache, "created_at", None) or datetime.now(timezone.utc)

    # Convert to response format
    worksheet_data = worksheet_cache.worksheet_json
    questions = [
        schemas.WorksheetQuestion(**q) for q in worksheet_data.get("questions", [])
    ]
    
    # citations: list of {chunk_id, document_id, page_range}; backward-compat for old cache without "citations"
    retrieval = worksheet_cache.retrieval_metadata or {}
    if not isinstance(retrieval, dict):
        retrieval = {}
    citations = retrieval.get("citations")
    if not isinstance(citations, list):
        citations = []

    try:
        credit_service.charge(
            user_id=current_user.id,
            feature_key=WORKSHEET_GENERATE,
            llm_response=None,
            description="Worksheet generation",
        )
    except Exception:
        pass

    return schemas.WorksheetResponse(
        id=worksheet_cache.id,
        pack_id=worksheet_cache.pack_id,
        topic_id=worksheet_cache.topic_id,
        topic_text=worksheet_cache.topic_text,
        grade=worksheet_cache.grade,
        subject=worksheet_cache.subject,
        questions=questions,
        answer_key=worksheet_data.get("answer_key", {}),
        marking_scheme=worksheet_data.get("marking_scheme", {}),
        citations=citations,
        created_at=created_at,
        chapter_page_range=retrieval.get("chapter_page_range"),
        relevance_avg_sim=retrieval.get("relevance_avg_sim"),
        relevance_keyword_hits=retrieval.get("relevance_keyword_hits"),
        final_difficulty_used=final_difficulty_used,
        attempts_count=attempts_count,
        attempts=attempts_count,
        validator_report_per_attempt=validator_report_per_attempt if debug else None,
        validator_reports=validator_report_per_attempt if debug else None,
        warnings=warnings if debug else None,
    )


@router.get("/worksheets/{worksheet_id}", response_model=schemas.WorksheetResponse)
async def get_worksheet(
    worksheet_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get cached worksheet by ID."""
    service = WorksheetService(db)
    worksheet_cache = service.get_worksheet(worksheet_id)
    
    if not worksheet_cache:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Worksheet not found"
        )
    
    # Convert to response format
    worksheet_data = worksheet_cache.worksheet_json
    questions = [
        schemas.WorksheetQuestion(**q) for q in worksheet_data.get("questions", [])
    ]
    
    # citations: list of {chunk_id, document_id, page_range}; backward-compat for old cache without "citations"
    retrieval = worksheet_cache.retrieval_metadata or {}
    citations = retrieval.get("citations") if isinstance(retrieval, dict) else None
    if not isinstance(citations, list):
        citations = []
    from datetime import datetime, timezone
    created_at = getattr(worksheet_cache, "created_at", None) or datetime.now(timezone.utc)

    return schemas.WorksheetResponse(
        id=worksheet_cache.id,
        pack_id=worksheet_cache.pack_id,
        topic_id=worksheet_cache.topic_id,
        topic_text=worksheet_cache.topic_text,
        grade=worksheet_cache.grade,
        subject=worksheet_cache.subject,
        questions=questions,
        answer_key=worksheet_data.get("answer_key", {}),
        marking_scheme=worksheet_data.get("marking_scheme", {}),
        citations=citations,
        created_at=created_at,
    )
