"""
Document service.
"""
from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.domains.content_ingestion.models import Document
from app.domains.content_ingestion.enums import DocumentStatus
from app.domains.content_ingestion.services.processing_progress_view import (
    build_processing_progress,
)

logger = get_logger(__name__)


class DocumentService:
    """Service for managing documents."""
    
    def __init__(self, db: Session):
        """Initialize document service."""
        self.db = db
    
    def create_document(
        self,
        pack_id: UUID,
        filename: str,
        file_path: str,
        file_size: Optional[int],
        mime_type: Optional[str],
        source_type: str,
        tenant_id: UUID,
        uploaded_by: Optional[UUID] = None,
        title: Optional[str] = None,
        author: Optional[str] = None,
        chapter_map: Optional[List[dict]] = None,
        document_hash: Optional[str] = None
    ) -> Document:
        """Create a new document record."""
        document = Document(
            pack_id=pack_id,
            filename=filename,
            file_path=file_path,
            file_size=file_size,
            mime_type=mime_type,
            source_type=source_type,
            status=DocumentStatus.UPLOADED.value,
            tenant_id=tenant_id,
            uploaded_by=uploaded_by,
            title=title,
            author=author,
            chapter_map=chapter_map,
            document_hash=document_hash
        )
        self.db.add(document)
        self.db.commit()
        self.db.refresh(document)
        logger.info(f"Created document: {document.id} - {document.filename}")
        return document
    
    def get_document(self, document_id: UUID, tenant_id: UUID) -> Optional[Document]:
        """Get document by ID."""
        document = self.db.query(Document).filter(
            Document.id == document_id,
            Document.tenant_id == tenant_id
        ).first()
        return document
    
    def list_documents(
        self,
        tenant_id: UUID,
        pack_id: Optional[UUID] = None,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 100
    ) -> tuple[List[Document], int]:
        """List documents."""
        query = self.db.query(Document).filter(
            Document.tenant_id == tenant_id
        )
        
        if pack_id:
            query = query.filter(Document.pack_id == pack_id)
        
        if status:
            query = query.filter(Document.status == status)
        
        total = query.count()
        documents = query.order_by(Document.created_at.desc()).offset(skip).limit(limit).all()
        
        return documents, total
    
    def update_document_status(
        self,
        document_id: UUID,
        status: str,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
        remediation_hint: Optional[str] = None,
        processing_metadata: Optional[dict] = None
    ) -> Optional[Document]:
        """Update document processing status."""
        document = self.db.query(Document).filter(
            Document.id == document_id
        ).first()
        
        if not document:
            return None
        
        document.status = status
        if error_code:
            document.error_code = error_code
        if error_message:
            document.error_message = error_message
        if remediation_hint:
            document.remediation_hint = remediation_hint
        if processing_metadata:
            if document.processing_metadata:
                document.processing_metadata.update(processing_metadata)
            else:
                document.processing_metadata = processing_metadata
        
        self.db.commit()
        self.db.refresh(document)
        logger.info(f"Updated document {document_id} status to {status}")
        return document
    
    def get_document_with_progress(self, document_id: UUID) -> Optional[dict]:
        """Get document with current processing progress."""
        document = self.db.query(Document).filter(
            Document.id == document_id
        ).first()
        
        if not document:
            return None
        
        # Get latest processing run
        from app.domains.content_ingestion.models import DocumentProcessingRun
        latest_run = self.db.query(DocumentProcessingRun).filter(
            DocumentProcessingRun.document_id == document_id
        ).order_by(DocumentProcessingRun.started_at.desc()).first()
        
        progress = None
        if latest_run:
            progress = build_processing_progress(document, latest_run)
        
        return {
            "document": document,
            "progress": progress
        }
    
    def reset_for_reingestion(self, document_id: UUID, tenant_id: UUID) -> Optional[Document]:
        """
        Remove partial pipeline rows and set document back to UPLOADED so ingestion can run cleanly.

        Used when retrying from failed or stuck in-flight statuses (e.g. worker died during extraction).
        """
        document = self.get_document(document_id, tenant_id)
        if not document:
            return None

        from app.domains.content_ingestion.models import (
            Chunk,
            DocumentProcessingRun,
            MathBlock,
            PageText,
            QAValidation,
        )

        deleted: dict[str, int] = {}
        for model, key in (
            (Chunk, "chunks"),
            (PageText, "page_texts"),
            (MathBlock, "math_blocks"),
            (QAValidation, "qa_validations"),
            (DocumentProcessingRun, "processing_runs"),
        ):
            n = self.db.query(model).filter(model.document_id == document_id).delete(synchronize_session=False)
            deleted[key] = n

        document.status = DocumentStatus.UPLOADED.value
        document.total_pages = None
        document.error_code = None
        document.error_message = None
        document.remediation_hint = None
        document.processed_at = None

        self.db.commit()
        self.db.refresh(document)
        logger.info(
            "document_reset_for_reingestion",
            extra={"document_id": str(document_id), **deleted},
        )
        return document

    def delete_document(self, document_id: UUID, tenant_id: UUID) -> bool:
        """Delete a document and all its related data."""
        document = self.get_document(document_id, tenant_id)
        if not document:
            return False
        
        try:
            # Delete associated chunks from database (cascade will handle related records)
            from app.domains.content_ingestion.models import Chunk
            chunks_deleted = self.db.query(Chunk).filter(
                Chunk.document_id == document_id
            ).delete()
            logger.info(f"Deleted {chunks_deleted} chunks for document {document_id}")
            
            # Delete the document (cascade will handle pages, processing_runs, qa_validations)
            self.db.delete(document)
            self.db.commit()
            logger.info(f"Deleted document: {document_id} - {document.filename}")
            return True
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to delete document {document_id}: {e}", exc_info=True)
            return False
