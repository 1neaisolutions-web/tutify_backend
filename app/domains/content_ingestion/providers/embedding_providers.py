"""
Embedding provider implementations.
"""
import hashlib
import os
from typing import List

from app.core.logging import get_logger
from app.core.config import settings
from app.domains.content_ingestion.providers.base import EmbeddingProvider
from app.llm.config import llm_settings

logger = get_logger(__name__)


class FakeEmbeddingProvider(EmbeddingProvider):
    """
    Deterministic fake embedding provider (no AI, no network).
    Uses hashing to produce stable float vectors for free-mode ingestion.
    """
    provider_name = "fake"

    def __init__(self):
        self._dim = getattr(settings, "FAKE_EMBEDDING_DIM", 384)

    def get_embedding_dimension(self) -> int:
        return self._dim

    def validate_config(self) -> bool:
        return True

    async def embed(self, texts: List[str], **kwargs) -> List[List[float]]:
        if not texts:
            return []
        dim = self._dim
        out = []
        for t in texts:
            h = hashlib.sha256(t.encode("utf-8")).hexdigest()
            # Deterministic: seed from hash, fill dim floats in [0,1]
            vec = []
            for i in range(dim):
                seed = f"{h}_{i}".encode()
                b = hashlib.sha256(seed).digest()
                val = int.from_bytes(b[:4], "big") / (2**32 - 1)
                vec.append(val)
            out.append(vec)
        logger.info(f"Fake embeddings: {len(out)} vectors, dim={dim}")
        return out


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """OpenAI embedding provider using text-embedding-3-small."""
    
    provider_name = "openai"
    embedding_dimension = 1536  # text-embedding-3-small dimension
    
    def __init__(self):
        """Initialize OpenAI embedding provider."""
        try:
            from openai import AsyncOpenAI
            self.client = AsyncOpenAI(api_key=llm_settings.OPENAI_API_KEY)
        except ImportError:
            logger.warning("openai package not installed")
            self.client = None
        except Exception as e:
            logger.warning(f"Failed to initialize OpenAI client: {e}")
            self.client = None
    
    def validate_config(self) -> bool:
        """Check if OpenAI API key is configured."""
        if not llm_settings.OPENAI_API_KEY:
            return False
        if self.client is None:
            return False
        return True
    
    def get_embedding_dimension(self) -> int:
        """Return embedding dimension."""
        return self.embedding_dimension
    
    async def embed(
        self,
        texts: List[str],
        **kwargs
    ) -> List[List[float]]:
        """
        Generate embeddings using OpenAI.
        
        Args:
            texts: List of text strings to embed
            
        Returns:
            List of embedding vectors
        """
        if not self.validate_config():
            raise RuntimeError("OpenAI embedding provider not properly configured")

        if not texts:
            return []
        
        logger.info(f"Generating embeddings for {len(texts)} texts using OpenAI")
        
        try:
            # Batch process (OpenAI supports up to 2048 texts per request)
            batch_size = 100
            all_embeddings = []
            
            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]
                
                response = await self.client.embeddings.create(
                    model="text-embedding-3-small",
                    input=batch
                )
                
                batch_embeddings = [item.embedding for item in response.data]
                all_embeddings.extend(batch_embeddings)
                
                logger.debug(f"Embedded batch {i//batch_size + 1}: {len(batch)} texts")
            
            logger.info(f"Generated {len(all_embeddings)} embeddings")
            return all_embeddings
            
        except Exception as e:
            logger.error(f"OpenAI embedding generation failed: {e}")
            raise RuntimeError(f"Embedding generation failed: {str(e)}")


class LocalSentenceTransformersEmbeddingProvider(EmbeddingProvider):
    """
    Local embedding provider using sentence-transformers (CPU, no API key).
    """
    provider_name = "local"

    def __init__(self):
        self._model = None
        self._model_name = getattr(settings, "LOCAL_EMBEDDING_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2")
        self._dim = None

    def _get_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                logger.info(f"Loading sentence-transformers model: {self._model_name}")
                self._model = SentenceTransformer(self._model_name)
                self._dim = self._model.get_sentence_embedding_dimension()
            except Exception as e:
                logger.error(f"Failed to load sentence-transformers: {e}")
                raise RuntimeError(
                    f"Local embedding provider not available: {e}. "
                    "Install: pip install sentence-transformers torch"
                )
        return self._model

    def get_embedding_dimension(self) -> int:
        if self._dim is None:
            self._get_model()
        return self._dim or 384

    def validate_config(self) -> bool:
        try:
            self._get_model()
            return True
        except Exception:
            return False

    async def embed(self, texts: List[str], **kwargs) -> List[List[float]]:
        if not texts:
            return []
        model = self._get_model()
        # Run in thread to avoid blocking event loop
        import asyncio
        def _encode():
            return model.encode(texts, convert_to_numpy=True).tolist()
        loop = asyncio.get_event_loop()
        vectors = await loop.run_in_executor(None, _encode)
        logger.info(f"Local embeddings: {len(vectors)} vectors, dim={len(vectors[0]) if vectors else 0}")
        return vectors
