"""
Base provider interfaces for content ingestion.
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field


@dataclass
class OCRPageResult:
    """Single page result from OCR (unified across providers)."""
    page_no: int
    text: str
    latex_text: Optional[str] = None  # Optional for math-heavy providers


@dataclass
class OCRResult:
    """Unified OCR result (international-grade, provider-agnostic)."""
    pages: List[OCRPageResult]
    meta: Dict[str, Any] = field(default_factory=dict)  # provider, duration_ms, warnings


@dataclass
class PageText:
    """Represents extracted text from a single page."""
    page_no: int  # 1-indexed
    text: str
    char_count: int
    ocr_confidence: Optional[float] = None
    ocr_engine: Optional[str] = None


@dataclass
class Chunk:
    """Represents a text chunk for embedding."""
    chunk_id: str
    text: str
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    topic_id: Optional[str] = None
    topic_title: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class VectorHit:
    """Represents a vector search result."""
    chunk_id: str
    document_id: str
    text: str
    similarity_score: float
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class MathBlock:
    """Represents an extracted math block (equation, expression, etc.)."""
    document_id: str
    page_no: int
    block_type: str  # equation | expression | table | unknown
    raw_text: str
    normalized_text: str
    bbox_json: Optional[Dict[str, Any]] = None
    confidence: Optional[float] = None
    provider_name: str = "baseline"


class MathExtractionProvider(ABC):
    """Abstract base class for math extraction providers."""
    provider_name: str

    @abstractmethod
    def extract_math(
        self,
        document_id: str,
        pages_text: List[PageText],
        **kwargs
    ) -> List[MathBlock]:
        """Extract math blocks from page texts. Returns list of MathBlock."""
        pass

    @abstractmethod
    def validate_config(self) -> bool:
        """Return True if provider is properly configured."""
        pass


class OCRProvider(ABC):
    """Abstract base class for OCR providers."""
    
    provider_name: str
    
    @abstractmethod
    async def run_ocr(
        self,
        pdf_path: str,
        language: str = "eng",
        **kwargs
    ) -> List[PageText]:
        """
        Run OCR on a PDF file.
        
        Args:
            pdf_path: Path to PDF file
            language: Language code (default: "eng")
            **kwargs: Additional provider-specific parameters
            
        Returns:
            List of PageText objects
        """
        pass
    
    @abstractmethod
    def validate_config(self) -> bool:
        """Return True if provider is properly configured."""
        pass


class TextExtractor(ABC):
    """Abstract base class for text extractors."""
    
    provider_name: str
    
    @abstractmethod
    async def extract_text(
        self,
        file_path: str,
        **kwargs
    ) -> List[PageText]:
        """
        Extract text from a document file.
        
        Args:
            file_path: Path to document file
            **kwargs: Additional provider-specific parameters
            
        Returns:
            List of PageText objects
        """
        pass
    
    @abstractmethod
    def validate_config(self) -> bool:
        """Return True if provider is properly configured."""
        pass


class Chunker(ABC):
    """Abstract base class for text chunkers."""
    
    provider_name: str
    
    @abstractmethod
    def chunk(
        self,
        pages: List[PageText],
        chunk_size_tokens: int = 500,
        overlap_tokens: int = 50,
        chapter_map: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> List[Chunk]:
        """
        Chunk text from pages into smaller pieces.
        
        Args:
            pages: List of PageText objects
            chunk_size_tokens: Target chunk size in tokens
            overlap_tokens: Overlap between chunks in tokens
            chapter_map: Optional chapter map for topic assignment
            **kwargs: Additional provider-specific parameters
            
        Returns:
            List of Chunk objects
        """
        pass


class EmbeddingProvider(ABC):
    """Abstract base class for embedding providers."""
    
    provider_name: str
    
    @abstractmethod
    async def embed(
        self,
        texts: List[str],
        **kwargs
    ) -> List[List[float]]:
        """
        Generate embeddings for a list of texts.
        
        Args:
            texts: List of text strings to embed
            **kwargs: Additional provider-specific parameters
            
        Returns:
            List of embedding vectors (each is a list of floats)
        """
        pass
    
    @abstractmethod
    def get_embedding_dimension(self) -> int:
        """Return the dimension of embeddings produced by this provider."""
        pass
    
    @abstractmethod
    def validate_config(self) -> bool:
        """Return True if provider is properly configured."""
        pass


class VectorStore(ABC):
    """Abstract base class for vector stores."""
    
    provider_name: str
    
    @abstractmethod
    async def upsert(
        self,
        chunks: List[Chunk],
        vectors: List[List[float]],
        document_id: str,
        pack_id: str,
        **kwargs
    ) -> int:
        """
        Upsert chunks with their embeddings into the vector store.
        
        Args:
            chunks: List of Chunk objects
            vectors: List of embedding vectors (same order as chunks)
            document_id: Document UUID
            pack_id: Content pack UUID
            **kwargs: Additional provider-specific parameters
            
        Returns:
            Number of chunks successfully stored
        """
        pass
    
    @abstractmethod
    async def query(
        self,
        query_vector: List[float],
        pack_id: str,
        top_k: int = 10,
        topic_id: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> List[VectorHit]:
        """
        Query the vector store for similar chunks.
        
        Args:
            query_vector: Query embedding vector
            pack_id: Filter by content pack ID
            top_k: Number of results to return
            topic_id: Optional topic ID filter
            filters: Additional filters
            **kwargs: Additional provider-specific parameters
            
        Returns:
            List of VectorHit objects sorted by similarity
        """
        pass
    
    @abstractmethod
    async def delete_document(
        self,
        document_id: str,
        **kwargs
    ) -> bool:
        """
        Delete all chunks for a document.
        
        Args:
            document_id: Document UUID
            
        Returns:
            True if successful
        """
        pass
    
    @abstractmethod
    def validate_config(self) -> bool:
        """Return True if provider is properly configured."""
        pass
