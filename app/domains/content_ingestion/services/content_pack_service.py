"""
Content Pack service.
"""
from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.logging import get_logger
from app.domains.content_ingestion.models import ContentPack, Document
from app.domains.content_ingestion.schemas import ContentPackCreate

logger = get_logger(__name__)


class ContentPackService:
    """Service for managing content packs."""
    
    def __init__(self, db: Session):
        """Initialize content pack service."""
        self.db = db
    
    def create_pack(
        self,
        data: ContentPackCreate,
        tenant_id: UUID,
        created_by: Optional[UUID] = None
    ) -> ContentPack:
        """Create a new content pack."""
        pack = ContentPack(
            name=data.name,
            description=data.description,
            subject=data.subject,
            grade=data.grade,
            curriculum=data.curriculum,
            ocr_policy=getattr(data, "ocr_policy", None),
            pack_metadata=data.metadata,  # Map schema 'metadata' to model 'pack_metadata'
            tenant_id=tenant_id,
            created_by=created_by
        )
        self.db.add(pack)
        self.db.commit()
        self.db.refresh(pack)
        logger.info(f"Created content pack: {pack.id} - {pack.name}")
        return pack
    
    def get_pack(self, pack_id: UUID, tenant_id: UUID) -> Optional[ContentPack]:
        """Get content pack by ID."""
        pack = self.db.query(ContentPack).filter(
            ContentPack.id == pack_id,
            ContentPack.tenant_id == tenant_id
        ).first()
        return pack
    
    def list_packs(
        self,
        tenant_id: UUID,
        skip: int = 0,
        limit: int = 100,
        is_active: Optional[bool] = None
    ) -> tuple[List[ContentPack], int]:
        """List content packs."""
        query = self.db.query(ContentPack).filter(
            ContentPack.tenant_id == tenant_id
        )
        
        if is_active is not None:
            query = query.filter(ContentPack.is_active == is_active)
        
        total = query.count()
        packs = query.order_by(ContentPack.created_at.desc()).offset(skip).limit(limit).all()
        
        # Add document count for API response
        for pack in packs:
            doc_count = self.db.query(func.count(Document.id)).filter(
                Document.pack_id == pack.id
            ).scalar()
            pack.document_count = doc_count
        
        return packs, total
    
    def update_pack(
        self,
        pack_id: UUID,
        tenant_id: UUID,
        **kwargs
    ) -> Optional[ContentPack]:
        """Update content pack."""
        pack = self.get_pack(pack_id, tenant_id)
        if not pack:
            return None
        
        for key, value in kwargs.items():
            if hasattr(pack, key):
                # Map 'metadata' to 'pack_metadata' for the model
                if key == 'metadata':
                    setattr(pack, 'pack_metadata', value)
                else:
                    setattr(pack, key, value)
        
        self.db.commit()
        self.db.refresh(pack)
        logger.info(f"Updated content pack: {pack.id}")
        return pack
    
    def delete_pack(self, pack_id: UUID, tenant_id: UUID) -> bool:
        """Delete content pack (soft delete by setting is_active=False)."""
        pack = self.get_pack(pack_id, tenant_id)
        if not pack:
            return False
        
        pack.is_active = False
        self.db.commit()
        logger.info(f"Deactivated content pack: {pack.id}")
        return True
