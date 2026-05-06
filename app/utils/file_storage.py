"""
File storage utility for handling profile picture uploads.
"""
import os
import uuid
from pathlib import Path
from typing import Optional, Tuple
from datetime import datetime

from fastapi import UploadFile, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class FileStorageService:
    """Service for handling file uploads and storage."""
    
    def __init__(self):
        self.upload_dir = Path(settings.UPLOAD_DIR)
        self.profile_pictures_dir = Path(settings.PROFILE_PICTURES_DIR)
        self.max_file_size = settings.MAX_FILE_SIZE_MB * 1024 * 1024  # Convert MB to bytes
        self.allowed_extensions = settings.ALLOWED_IMAGE_EXTENSIONS
        self._ensure_directories()
    
    def _ensure_directories(self) -> None:
        """Ensure upload directories exist."""
        try:
            self.profile_pictures_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Upload directories ensured: {self.profile_pictures_dir}")
        except Exception as e:
            logger.error(f"Failed to create upload directories: {e}")
            raise
    
    def validate_file(self, file: UploadFile) -> Tuple[bool, Optional[str]]:
        """
        Validate uploaded file.
        
        Args:
            file: UploadFile object
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not file.filename:
            return False, "No filename provided"
        
        # Check file extension
        file_ext = Path(file.filename).suffix.lower()
        if file_ext not in self.allowed_extensions:
            allowed = ", ".join(ext.upper() for ext in self.allowed_extensions)
            return False, f"Invalid file type. Allowed formats: {allowed}"
        
        # Check file size (we need to read the file to check size)
        # Note: We'll check size during actual save to avoid reading file twice
        return True, None
    
    async def save_profile_picture(
        self,
        file: UploadFile,
        old_file_url: Optional[str] = None
    ) -> str:
        """
        Save profile picture file and return the relative URL.
        
        Args:
            file: UploadFile object
            old_file_url: Optional URL of old file to delete
            
        Returns:
            Relative file path (e.g., "filename.jpg")
            
        Raises:
            HTTPException: If validation fails or file save fails
        """
        # Validate file
        is_valid, error_msg = self.validate_file(file)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_msg
            )
        
        # Read file content to check size and save
        try:
            logger.info(f"Reading file content for: {file.filename}")
            content = await file.read()
            file_size = len(content)
            logger.info(f"File read successfully, size: {file_size} bytes")
            
            # Check file size
            if file_size > self.max_file_size:
                max_mb = settings.MAX_FILE_SIZE_MB
                actual_mb = file_size / (1024 * 1024)
                logger.error(f"File too large: {actual_mb:.2f}MB > {max_mb}MB")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"File size ({actual_mb:.2f}MB) exceeds maximum allowed size ({max_mb}MB)"
                )
            
            # Check if file is empty
            if file_size == 0:
                logger.error("File is empty")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="File is empty"
                )
            
            # Check if it's actually an image (basic check)
            if not file.content_type or not file.content_type.startswith('image/'):
                logger.error(f"Invalid content type: {file.content_type}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="File is not a valid image"
                )
            
            # Generate unique filename
            file_ext = Path(file.filename).suffix.lower()
            unique_filename = f"{uuid.uuid4()}_{int(datetime.now().timestamp())}{file_ext}"
            file_path = self.profile_pictures_dir / unique_filename
            
            logger.info(f"Saving file to: {file_path}")
            
            # Save file
            try:
                with open(file_path, 'wb') as f:
                    f.write(content)
                logger.info(f"Profile picture saved successfully: {file_path}")
                # Verify file was saved
                if file_path.exists():
                    saved_size = file_path.stat().st_size
                    logger.info(f"File saved and verified, size: {saved_size} bytes")
                else:
                    logger.error(f"File was not saved despite no error: {file_path}")
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="File save verification failed"
                    )
            except IOError as e:
                logger.error(f"Failed to save profile picture: {e}", exc_info=True)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to save file"
                )
            
            # Delete old file if provided
            if old_file_url:
                logger.info(f"Deleting old profile picture: {old_file_url}")
                self.delete_profile_picture(old_file_url)
            
            # Return relative path (just the filename)
            logger.info(f"Returning filename: {unique_filename}")
            return unique_filename
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error saving profile picture: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to process file upload"
            )
    
    def delete_profile_picture(self, file_url: Optional[str]) -> bool:
        """
        Delete a profile picture file.
        
        Args:
            file_url: Relative file path or filename
            
        Returns:
            True if deleted successfully, False otherwise
        """
        if not file_url:
            return False
        
        try:
            # Extract filename from URL if it's a full path
            filename = Path(file_url).name if '/' in file_url else file_url
            file_path = self.profile_pictures_dir / filename
            
            if file_path.exists() and file_path.is_file():
                file_path.unlink()
                logger.info(f"Deleted profile picture: {file_path}")
                return True
            else:
                logger.warning(f"Profile picture file not found: {file_path}")
                return False
        except Exception as e:
            logger.error(f"Error deleting profile picture {file_url}: {e}", exc_info=True)
            return False
    
    def get_file_url(self, filename: Optional[str]) -> Optional[str]:
        """
        Get full URL for a profile picture filename.
        
        Args:
            filename: Profile picture filename
            
        Returns:
            Full URL path or None
        """
        if not filename:
            return None
        
        # Return relative path that can be served by static file mount
        return f"/static/profile_pictures/{filename}"


# Global instance
file_storage_service = FileStorageService()
