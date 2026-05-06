"""
Background jobs for content ingestion.
"""
import asyncio
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.core.config import settings
from app.db.session import SessionLocal
from app.domains.content_ingestion.services.ingestion_service import IngestionService

logger = get_logger(__name__)


async def ingest_document_job(document_id: UUID):
    """
    Background job to ingest a document through the processing pipeline.
    
    This function is designed to be called from FastAPI BackgroundTasks.
    For production, consider using Celery or similar task queue.
    
    Args:
        document_id: Document UUID to process
    """
    db = SessionLocal()
    try:
        logger.info(f"Starting background ingestion job for document {document_id}")
        
        ingestion_service = IngestionService(db)
        timeout_s = int(getattr(settings, "INGESTION_JOB_TIMEOUT_SECONDS", 21600))
        document = await asyncio.wait_for(
            ingestion_service.ingest_document(document_id),
            timeout=timeout_s,
        )
        
        logger.info(f"Background ingestion job completed for document {document_id}: {document.status}")
        
    except asyncio.TimeoutError:
        e = RuntimeError(
            f"Ingestion timed out after {int(getattr(settings, 'INGESTION_JOB_TIMEOUT_SECONDS', 21600))} seconds."
        )
        logger.error(f"Background ingestion job timed out for document {document_id}", exc_info=True)
        # Continue to shared failure update path below.
        try:
            from app.domains.content_ingestion.models import Document
            from app.domains.content_ingestion.enums import DocumentStatus
            document = db.query(Document).filter(Document.id == document_id).first()
            if document:
                document.status = DocumentStatus.FAILED.value
                document.error_code = "JOB_TIMEOUT"
                document.error_message = str(e)
                document.remediation_hint = (
                    "Processing exceeded time limit. Retry once, or reduce PDF size / OCR scope. "
                    "If this persists, increase INGESTION_JOB_TIMEOUT_SECONDS."
                )
                db.commit()
        except Exception as commit_error:
            logger.error(f"Failed to update timed-out document status: {commit_error}", exc_info=True)
    except Exception as e:
        logger.error(f"Background ingestion job failed for document {document_id}: {e}", exc_info=True)
        # Ensure session is usable after any flush/commit failure before querying.
        try:
            db.rollback()
        except Exception:
            pass
        # Update document status to failed with detailed error information
        try:
            from app.domains.content_ingestion.models import Document
            from app.domains.content_ingestion.enums import DocumentStatus
            document = db.query(Document).filter(Document.id == document_id).first()
            if document:
                # Preserve detailed failure produced by ingestion service.
                if (
                    str(document.status or "").lower() == DocumentStatus.FAILED.value
                    and (document.error_code or "").strip()
                    and (document.error_message or "").strip()
                ):
                    logger.info(
                        f"Document {document_id} already marked failed by ingestion service "
                        f"(error_code={document.error_code}); preserving original error."
                    )
                    return
                document.status = DocumentStatus.FAILED.value
                document.error_code = "JOB_ERROR"
                
                # Provide more detailed error messages
                error_str = str(e)
                if "OPENAI_API_KEY" in error_str or "api key" in error_str.lower():
                    document.error_message = "OpenAI API key is missing or invalid. Please set OPENAI_API_KEY in .env file."
                    document.remediation_hint = "Set OPENAI_API_KEY in your .env file and restart the backend."
                elif "OCR_STRICT_GOOGLE_ONLY=true" in error_str or "google document ai" in error_str.lower():
                    document.error_message = f"Google OCR processing failed: {error_str}"
                    document.remediation_hint = (
                        "Verify GOOGLE_APPLICATION_CREDENTIALS, DOCUMENT_AI_PROJECT_ID, DOCUMENT_AI_LOCATION, "
                        "DOCUMENT_AI_PROCESSOR_ID, and Document AI IAM permissions/billing. "
                        "Then retry processing."
                    )
                elif "tesseract" in error_str.lower() or "ocr" in error_str.lower():
                    document.error_message = f"OCR processing failed: {error_str}"
                    document.remediation_hint = "Install Tesseract OCR: https://github.com/UB-Mannheim/tesseract/wiki"
                elif "file not found" in error_str.lower() or "file_path" in error_str.lower():
                    document.error_message = f"Document file not found: {error_str}"
                    document.remediation_hint = "The uploaded file may have been deleted or moved. Try re-uploading."
                elif "embedding" in error_str.lower():
                    document.error_message = f"Embedding generation failed: {error_str}"
                    document.remediation_hint = "Check OPENAI_API_KEY and network connectivity."
                elif "vector" in error_str.lower() or "pgvector" in error_str.lower():
                    document.error_message = f"Vector storage failed: {error_str}"
                    document.remediation_hint = "Check database connection and pgvector extension."
                else:
                    document.error_message = error_str
                    document.remediation_hint = "Check backend logs for detailed error information."
                
                db.commit()
                logger.info(f"Updated document {document_id} status to FAILED with error: {document.error_message}")
        except Exception as commit_error:
            logger.error(f"Failed to update document status: {commit_error}", exc_info=True)
    finally:
        db.close()


def run_ingestion_job_sync(document_id: UUID):
    """
    Synchronous wrapper for ingestion job (FastAPI BackgroundTasks).

    Tasks run in a worker thread without a running asyncio loop; use asyncio.run.
    Avoid get_event_loop/create_task patterns — they caused duplicate or orphaned tasks.
    """
    asyncio.run(ingest_document_job(document_id))
