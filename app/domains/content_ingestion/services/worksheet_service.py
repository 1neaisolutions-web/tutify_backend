"""
Worksheet generation service using RAG.
"""
import hashlib
import json
import re
import time
from typing import List, Dict, Any, Optional, Tuple
from uuid import UUID
from collections import defaultdict

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
try:
    from app.core.rag_logging import rag_log, rag_log_chunk_list
except ImportError:
    # rag_logging is optional - use no-op functions if not available
    def rag_log(*args, **kwargs):
        pass
    def rag_log_chunk_list(*args, **kwargs):
        pass
from app.domains.content_ingestion.models import WorksheetCache, ContentPack
from app.domains.content_ingestion.providers.vector_stores import PgVectorStore
from app.domains.content_ingestion.providers.embedding_providers import (
    OpenAIEmbeddingProvider,
    FakeEmbeddingProvider,
    LocalSentenceTransformersEmbeddingProvider,
)
from app.domains.content_ingestion.providers.base import VectorHit
from app.domains.content_ingestion.models import Chunk, Document
from app.llm.router import ModelRouter
from app.llm.config import llm_settings

logger = get_logger(__name__)


class WorksheetService:
    """Service for generating worksheets using RAG."""
    
    def __init__(self, db: Session):
        """Initialize worksheet service."""
        self.db = db
        self.vector_store = PgVectorStore(db=db)
        # Embedding provider will be determined dynamically based on pack's stored embeddings
        self.llm_router = ModelRouter(config=llm_settings)
    
    def _summarize_context(self, context_with_metadata: str, max_tokens: int = 1000) -> str:
        """
        Summarize context to limit token count. Rough estimate: 1 token ≈ 4 characters.
        Target: ~800-1000 tokens ≈ 3200-4000 characters.
        """
        if len(context_with_metadata) <= max_tokens * 4:
            return context_with_metadata
        
        # Split by chunks (separated by ---)
        chunks = context_with_metadata.split("\n\n---\n\n")
        summarized_chunks = []
        current_length = 0
        
        for chunk in chunks:
            chunk_length = len(chunk)
            # If adding this chunk would exceed limit, truncate it
            if current_length + chunk_length > max_tokens * 4:
                remaining = (max_tokens * 4) - current_length - 200  # Reserve 200 chars for separators
                if remaining > 500:  # Only include if meaningful
                    # Truncate chunk to remaining space, keeping start and end
                    half = remaining // 2
                    truncated = chunk[:half] + "\n[... content truncated for brevity ...]\n" + chunk[-half:]
                    summarized_chunks.append(truncated)
                break
            summarized_chunks.append(chunk)
            current_length += chunk_length + 10  # +10 for separator
        
        return "\n\n---\n\n".join(summarized_chunks)
    
    def _detect_pack_embedding_provider(self, pack_id: UUID) -> tuple[Any, str]:
        """
        Detect which embedding provider/model was used for chunks in this pack.
        Returns (embedding_provider_instance, embedding_model_string).
        """
        # Find a chunk from this pack to detect embedding provider
        chunk = self.db.query(Chunk).join(Document).filter(
            Document.pack_id == pack_id,
            Document.status == "published",
            Chunk.embedding_v.isnot(None)
        ).first()
        
        if not chunk:
            # Fallback to OpenAI if no chunks found
            logger.warning(f"No chunks found for pack {pack_id}, defaulting to OpenAI embeddings")
            return OpenAIEmbeddingProvider(), "openai"
        
        provider_name = chunk.embedding_provider or "fake"
        embedding_model = chunk.embedding_model or provider_name
        
        # Instantiate the correct provider
        if provider_name == "openai":
            return OpenAIEmbeddingProvider(), embedding_model
        elif provider_name == "local":
            return LocalSentenceTransformersEmbeddingProvider(), embedding_model
        else:
            # Default to fake for free mode
            return FakeEmbeddingProvider(), embedding_model
    
    # Pages 1..N are typically cover, TOC, copyright. Chunks from these are excluded for worksheet context.
    FRONT_MATTER_MAX_PAGE = 8

    async def generate_worksheet(
        self,
        pack_id: UUID,
        topic_id: Optional[str] = None,
        topic_text: Optional[str] = None,
        grade: Optional[str] = None,
        subject: Optional[str] = None,
        difficulty_mix: Optional[Dict[str, float]] = None,
        num_questions: int = 10,
        question_types: Optional[List[str]] = None,
        force_regenerate: bool = False,
        pack_ids: Optional[List[UUID]] = None,
        teacher_prompt: Optional[str] = None,
    ) -> WorksheetCache:
        """
        Generate a worksheet using RAG.
        
        Args:
            pack_id: Content pack UUID
            topic_id: Optional topic ID from chapter map
            topic_text: Optional topic text (alternative to topic_id)
            grade: Grade level
            subject: Subject
            difficulty_mix: Difficulty distribution
            num_questions: Number of questions
            question_types: List of question types
            
        Returns:
            WorksheetCache object
        """
        # Check cache first (skip if force_regenerate)
        signature_hash = self._generate_signature_hash(
            pack_id, topic_id, topic_text, grade, subject, difficulty_mix, num_questions,
            pack_ids=pack_ids, teacher_prompt=teacher_prompt,
        )
        
        if not force_regenerate:
            cached = self.db.query(WorksheetCache).filter(
                WorksheetCache.signature_hash == signature_hash
            ).first()
            if cached:
                # Used by API layer to set X-Worksheet-Cache header
                setattr(cached, "from_cache", True)
                logger.info(f"Returning cached worksheet: {cached.id}")
                rag_log("worksheet_cached", pack_id=str(pack_id), topic_text=topic_text or "", worksheet_id=str(cached.id))
                return cached
        else:
            # Remove existing cache so we can insert the new worksheet (avoids 409 on unique signature_hash)
            self.db.query(WorksheetCache).filter(
                WorksheetCache.signature_hash == signature_hash
            ).delete()
            self.db.commit()
        
        # Generate new worksheet
        request_start_time = time.monotonic()
        logger.info(f"Generating worksheet for pack {pack_id}, topic: {topic_text or topic_id}")
        rag_log("worksheet_start", pack_id=str(pack_id), topic_id=topic_id or "", topic_text=topic_text or "", num_questions=num_questions, force_regenerate=force_regenerate)
        
        # Normalize topic and expand query terms for retrieval (typo correction + synonyms)
        normalized_topic_text = self._normalize_topic_for_keywords(topic_text or "")
        expanded_query_terms = self._expand_query_synonyms(topic_text or "")
        base_query = topic_text or f"topic {topic_id}" if topic_id else "curriculum content"
        # Use expanded terms for vector search so we hit correct chapter (e.g. algebraic expression -> variable, coefficient, simplify)
        query_text = " ".join(expanded_query_terms[:20]) + " chapter section explanation examples" if expanded_query_terms else f"{base_query} chapter section explanation examples"
        rag_log("query_expand", pack_id=str(pack_id), normalized_topic_text=normalized_topic_text, expanded_terms_count=len(expanded_query_terms), expanded_terms_sample=expanded_query_terms[:12])
        
        # Effective packs for retrieval: multi-pack or single
        effective_pack_ids = list(pack_ids) if pack_ids else [pack_id]
        # Detect which embedding provider was used (first pack when multi-pack)
        embedding_provider, embedding_model = self._detect_pack_embedding_provider(effective_pack_ids[0])
        logger.info(f"Using embedding provider: {embedding_provider.provider_name}, model: {embedding_model}")
        rag_log("embedding_provider", pack_id=str(pack_id), provider=embedding_provider.provider_name, model=embedding_model)
        
        skip_pages = self.FRONT_MATTER_MAX_PAGE
        top_k = min(20, num_questions * 3)
        context_min_chunks = 6
        context_max_chunks = 10
        relevance_sim_threshold = 0.32
        relevance_keyword_min = 2
        page_window_size = 4  # 4-page bins for cluster-by-page
        stage_a_top_k = 80
        max_chapter_ranges = 3
        high_sim_cutoff = 0.35  # chunk passes "keyword or high sim" if sim >= this

        # Stage A: cluster-by-page — top 80 hits, 4-page bins, densest high-similarity cluster(s)
        hits_broad: List[VectorHit] = []
        if embedding_provider.provider_name != "fake":
            try:
                query_embeddings = await embedding_provider.embed([query_text])
                if query_embeddings and len(query_embeddings) > 0:
                    hits_broad = await self.vector_store.query(
                        query_vector=query_embeddings[0],
                        pack_id=str(effective_pack_ids[0]),
                        pack_ids=[str(p) for p in effective_pack_ids] if len(effective_pack_ids) > 1 else None,
                        top_k=stage_a_top_k,
                        topic_id=topic_id,
                        embedding_model=embedding_model,
                    )
            except Exception as e:
                logger.warning(f"Vector search failed: {e}, falling back to text search")
        if not hits_broad:
            hits_broad = self._text_based_search(
                pack_id=effective_pack_ids[0],
                pack_ids=effective_pack_ids if len(effective_pack_ids) > 1 else None,
                query_text=query_text,
                topic_id=topic_id,
                top_k=stage_a_top_k,
            )
        hits_after_front = [h for h in hits_broad if (h.metadata or {}).get("page_start_pdf", 0) > skip_pages]
        if not hits_after_front:
            any_have_page = any((h.metadata or {}).get("page_start_pdf") is not None for h in hits_broad)
            if hits_broad and any_have_page:
                raise ValueError(
                    "Topic content not found in this book pack. All retrieved content is from early pages (cover/TOC). Try another topic."
                )
            hits_after_front = hits_broad[:stage_a_top_k]
        keywords_topic = self._extract_topic_keywords(topic_text or "")
        # Cluster by 4-page bins; score = density (count) + avg similarity + keyword bonus
        window_scores: Dict[Tuple[int, int], Tuple[float, int, float]] = defaultdict(lambda: (0.0, 0, 0.0))  # total_sim, count, keyword_bonus
        for h in hits_after_front:
            p = (h.metadata or {}).get("page_start_pdf")
            if p is None:
                continue
            window_start = ((p - 1) // page_window_size) * page_window_size + 1
            window_end = window_start + page_window_size - 1
            key = (window_start, window_end)
            sim = getattr(h, "similarity_score", 0)
            prev_sim, prev_count, prev_kw = window_scores[key]
            kw_bonus = 0.1 if any(kw in (h.text or "").lower() for kw in keywords_topic) else 0.0
            window_scores[key] = (prev_sim + sim, prev_count + 1, prev_kw + kw_bonus)
        scored_ranges: List[Tuple[Tuple[int, int], float]] = []
        for (lo, hi), (total_sim, count, kw_bonus) in window_scores.items():
            if count == 0:
                continue
            avg_sim = total_sim / count
            score = avg_sim + 0.05 * min(count, 8) + kw_bonus
            scored_ranges.append(((lo, hi), score))
        scored_ranges.sort(key=lambda x: -x[1])
        top5_ranges_for_debug = [(r[0], r[1]) for r in scored_ranges[:5]]
        chosen_ranges = [r[0] for r in scored_ranges[:max_chapter_ranges]]
        if not chosen_ranges:
            min_page_range = 0
            max_page_range = 99999
            chosen_ranges = [(0, 99999)]
        else:
            min_page_range = min(r[0] for r in chosen_ranges)
            max_page_range = max(r[1] for r in chosen_ranges)
        logger.info(f"Worksheet Stage A: chosen chapter page ranges {chosen_ranges} (using {min_page_range}-{max_page_range}), top5 scores={[(r, round(s,3)) for r,s in top5_ranges_for_debug]}")
        rag_log("stage_a", pack_id=str(pack_id), topic_text=topic_text or "", hits_broad=len(hits_broad), hits_after_front=len(hits_after_front), chosen_ranges=chosen_ranges, min_page=min_page_range, max_page=max_page_range, top5_ranges_scores=[(r, round(s, 4)) for r, s in top5_ranges_for_debug])

        # Stage B: retrieve within best cluster range (more candidates, then filter to 6-10)
        hits: List[VectorHit] = []
        for attempt in range(2):
            if embedding_provider.provider_name != "fake":
                try:
                    query_embeddings = await embedding_provider.embed([query_text])
                    if query_embeddings and len(query_embeddings) > 0:
                        hits = await self.vector_store.query(
                            query_vector=query_embeddings[0],
                            pack_id=str(effective_pack_ids[0]),
                            pack_ids=[str(p) for p in effective_pack_ids] if len(effective_pack_ids) > 1 else None,
                            top_k=25,
                            topic_id=topic_id,
                            embedding_model=embedding_model,
                            filters={"min_page": min_page_range - 1, "max_page": max_page_range},
                        )
                except Exception as e:
                    logger.warning(f"Stage B vector search failed: {e}")
            if not hits:
                hits = [h for h in hits_after_front if (h.metadata or {}).get("page_start_pdf") is not None and min_page_range <= (h.metadata or {}).get("page_start_pdf", 0) <= max_page_range][:25]
            if hits:
                break
            if attempt == 0 and len(chosen_ranges) < 3 and len(scored_ranges) >= 3:
                min_page_range = min(r[0] for r in scored_ranges[:3])
                max_page_range = max(r[1] for r in scored_ranges[:3])
                continue
            break
        if not hits:
            self._raise_topic_not_found(
                top5_ranges_for_debug, chosen_ranges, hits_after_front, topic_text or "", None, 0.0, 0
            )
        # Tighten: only 6-10 chunks with topic keyword hit OR high similarity
        keywords_topic_list = self._extract_topic_keywords(topic_text or "")
        def chunk_relevance(h: VectorHit) -> Tuple[float, int]:
            sim = getattr(h, "similarity_score", 0)
            text_lower = (h.text or "").lower()
            kw_hits = sum(1 for kw in keywords_topic_list if kw in text_lower)
            return (sim + 0.1 * min(kw_hits, 3), kw_hits)
        filtered = [h for h in hits if chunk_relevance(h)[1] >= 1 or getattr(h, "similarity_score", 0) >= high_sim_cutoff]
        if not filtered:
            filtered = hits
        filtered.sort(key=lambda h: -chunk_relevance(h)[0])
        hits = filtered[:context_max_chunks]
        if len(hits) < context_min_chunks and len(filtered) >= context_min_chunks:
            hits = filtered[:context_min_chunks]
        avg_sim, keyword_hits = self._relevance_score(hits, topic_text or "")
        logger.info(f"Worksheet Stage B: {len(hits)} chunks (6-10), relevance avg_sim={avg_sim:.3f}, keyword_hits={keyword_hits}")
        rag_log("stage_b", pack_id=str(pack_id), topic_text=topic_text or "", chunks_count=len(hits), avg_sim=round(avg_sim, 4), keyword_hits=keyword_hits, relevance_threshold=relevance_sim_threshold, keyword_min=relevance_keyword_min)
        rag_log_chunk_list("stage_b_chunks", hits)
        if avg_sim < relevance_sim_threshold or keyword_hits < relevance_keyword_min:
            if len(chosen_ranges) < 3 and len(scored_ranges) >= 3:
                min_page_range = min(r[0] for r in scored_ranges[:3])
                max_page_range = max(r[1] for r in scored_ranges[:3])
                hits = [h for h in hits_after_front if (h.metadata or {}).get("page_start_pdf") is not None and min_page_range <= (h.metadata or {}).get("page_start_pdf", 0) <= max_page_range]
                filtered = [h for h in hits if chunk_relevance(h)[1] >= 1 or getattr(h, "similarity_score", 0) >= high_sim_cutoff]
                if not filtered:
                    filtered = hits
                filtered.sort(key=lambda h: -chunk_relevance(h)[0])
                hits = filtered[:context_max_chunks]
                if hits:
                    avg_sim, keyword_hits = self._relevance_score(hits, topic_text or "")
            if avg_sim < relevance_sim_threshold or keyword_hits < relevance_keyword_min:
                # Shallow-topic broadening: do not hard-fail; broaden retrieval and continue best-effort.
                logger.warning(
                    f"Low relevance for topic '{topic_text or topic_id}': avg_sim={avg_sim:.3f}, "
                    f"keyword_hits={keyword_hits}. Broadening retrieval instead of raising."
                )
                rag_log(
                    "topic_low_relevance_broaden",
                    pack_id=str(pack_id),
                    topic_text=topic_text or "",
                    avg_sim=round(avg_sim, 4),
                    keyword_hits=keyword_hits,
                    chosen_ranges=chosen_ranges,
                )
                broaden_pool = hits_after_front[:] if hits_after_front else hits[:]
                broaden_pool.sort(key=lambda h: -chunk_relevance(h)[0])
                hits = broaden_pool[:context_max_chunks] if broaden_pool else hits
                if hits:
                    avg_sim, keyword_hits = self._relevance_score(hits, topic_text or "")
        for i, h in enumerate(hits[:5]):
            meta = h.metadata or {}
            logger.info(
                f"Worksheet chunk[{i}] id={h.chunk_id} page_start_pdf={meta.get('page_start_pdf')} "
                f"page_end_pdf={meta.get('page_end_pdf')} score={getattr(h, 'similarity_score', None)}"
            )

        # De-duplicate hits (especially important for multi-pack retrieval)
        seen_hit_keys = set()
        deduped_hits: List[VectorHit] = []
        for h in hits:
            key = (h.document_id, h.chunk_id)
            if key in seen_hit_keys:
                continue
            seen_hit_keys.add(key)
            # Ensure pack_id is always available for citations (multi-pack requirement)
            meta = dict(h.metadata or {})
            if "pack_id" not in meta:
                meta["pack_id"] = str(pack_id)
            h.metadata = meta
            deduped_hits.append(h)
        hits = deduped_hits

        # Role-aware, two-context retrieval: concept vs assessment
        concept_roles = ["concept", "worked_example"]
        assessment_roles = ["exercise_prompt", "exam_question"]
        concept_hits: List[VectorHit] = []
        assessment_hits: List[VectorHit] = []

        # If we have embeddings, run two targeted retrieval queries by role; otherwise split current hits by role.
        try:
            if embedding_provider.provider_name != "fake":
                query_embeddings = await embedding_provider.embed([query_text])
                query_vector = query_embeddings[0] if query_embeddings else None
                if query_vector is not None:
                    min_page_filter = max(int(skip_pages), int(min_page_range or 0))
                    max_page_filter = int(max_page_range or 99999)
                    concept_hits = await self.vector_store.query(
                        query_vector=query_vector,
                        pack_id=str(effective_pack_ids[0]),
                        pack_ids=[str(p) for p in effective_pack_ids] if len(effective_pack_ids) > 1 else None,
                        top_k=8,
                        topic_id=topic_id,
                        filters={"min_page": min_page_filter, "max_page": max_page_filter, "roles": concept_roles},
                        embedding_model=embedding_model,
                    )
                    assessment_hits = await self.vector_store.query(
                        query_vector=query_vector,
                        pack_id=str(effective_pack_ids[0]),
                        pack_ids=[str(p) for p in effective_pack_ids] if len(effective_pack_ids) > 1 else None,
                        top_k=8,
                        topic_id=topic_id,
                        filters={"min_page": min_page_filter, "max_page": max_page_filter, "roles": assessment_roles},
                        embedding_model=embedding_model,
                    )
        except Exception as e:
            logger.warning(f"Role-aware retrieval failed; falling back to split hits: {e}")

        if not concept_hits:
            concept_hits = [h for h in hits if (h.metadata or {}).get("role") in concept_roles][:8]
        if not assessment_hits:
            assessment_hits = [h for h in hits if (h.metadata or {}).get("role") in assessment_roles][:8]

        # Deduplicate within each context; allow overlap across contexts if corpus is small.
        # (We dedupe citations later.)
        # Backfill from top remaining chunks (by relevance) when bucket < BUCKET_MIN_TARGET
        bucket_min_target = getattr(settings, "BUCKET_MIN_TARGET", 4)
        fill_from_sorted = sorted(hits, key=lambda h: -getattr(h, "similarity_score", 0))

        def _dedupe_and_fill(primary: List[VectorHit], *, fill_from: List[VectorHit], target_min: int, target_max: int) -> Tuple[List[VectorHit], int]:
            seen = set()
            out: List[VectorHit] = []
            for h in primary:
                key = (h.document_id, h.chunk_id)
                if key in seen:
                    continue
                seen.add(key)
                meta = dict(h.metadata or {})
                meta.setdefault("pack_id", str(pack_id))
                h.metadata = meta
                out.append(h)
                if len(out) >= target_max:
                    return out[:target_max], 0
            backfill_count = 0
            if len(out) < target_min:
                for h in fill_from:
                    key = (h.document_id, h.chunk_id)
                    if key in seen:
                        continue
                    seen.add(key)
                    meta = dict(h.metadata or {})
                    meta.setdefault("pack_id", str(pack_id))
                    h.metadata = meta
                    out.append(h)
                    backfill_count += 1
                    if len(out) >= target_min:
                        break
            return out[:target_max], backfill_count

        concept_deduped, concept_backfill = _dedupe_and_fill(
            concept_hits, fill_from=fill_from_sorted, target_min=bucket_min_target, target_max=8
        )
        assessment_deduped, assessment_backfill = _dedupe_and_fill(
            assessment_hits, fill_from=fill_from_sorted, target_min=bucket_min_target, target_max=8
        )
        concept_preferred_count = len(concept_deduped) - concept_backfill
        assessment_preferred_count = len(assessment_deduped) - assessment_backfill
        total_backfill = concept_backfill + assessment_backfill
        logger.info(
            f"Role buckets: concept_preferred={concept_preferred_count}, assessment_preferred={assessment_preferred_count}, "
            f"backfill_count={total_backfill} (concept={concept_backfill}, assessment={assessment_backfill})"
        )

        def _format_hit_for_context(hit: VectorHit) -> str:
            meta = hit.metadata or {}
            start = meta.get("page_start_pdf")
            end = meta.get("page_end_pdf")
            if start is not None and end is not None:
                page_range = f"{start}-{end}"
            elif start is not None:
                page_range = str(start)
            elif end is not None:
                page_range = str(end)
            else:
                page_range = ""
            role = meta.get("role", "")
            pack_id_for_hit = meta.get("pack_id", str(pack_id))
            return (
                f"[chunk_id: {hit.chunk_id}, document_id: {hit.document_id}, pack_id: {pack_id_for_hit}, "
                f"page_range: {page_range}, role: {role}]\n{hit.text}"
            )

        context_with_metadata = (
            "CONCEPT CONTEXT (definitions, explanations):\n"
            + "\n\n---\n\n".join(_format_hit_for_context(h) for h in concept_deduped)
            + "\n\n\nASSESSMENT CONTEXT (examples, exercises, questions):\n"
            + "\n\n---\n\n".join(_format_hit_for_context(h) for h in assessment_deduped)
        )

        context_chunks = [h.text for h in (concept_deduped + assessment_deduped)]
        context_text_flat = " ".join(context_chunks)
        allowed_concepts, forbidden_concepts = self._build_allowed_forbidden(context_text_flat, topic_text or "")
        logger.info(f"Worksheet prompt: allowed_concepts={allowed_concepts[:8]}, forbidden_concepts={forbidden_concepts[:8]}")

        # MCQ vs short count from question_types (e.g. ["mcq", "short_answer"] -> half each)
        question_types_resolved = question_types or ["mcq", "short_answer"]
        wants_mcq = any((t or "").lower() in ("mcq", "multiple_choice") for t in question_types_resolved)
        wants_short = any((t or "").lower() in ("short_answer", "short") for t in question_types_resolved)
        if wants_mcq and wants_short:
            mcq_count = num_questions // 2
            short_count = num_questions - mcq_count
        elif wants_mcq:
            mcq_count = num_questions
            short_count = 0
        else:
            mcq_count = 0
            short_count = num_questions

        # Generate worksheet using LLM; max 1 attempt (no retry for speed)
        worksheet_json = None
        # Summarize context to limit tokens (target ~800-1000 tokens)
        context_summarized = self._summarize_context(context_with_metadata, max_tokens=1000)
        context_for_retry = context_summarized
        hits_for_retry = hits
        
        for attempt in range(1):  # Only 1 attempt - no retry
            try:
                # Determine target difficulty from difficulty_mix
                target_difficulty = None
                if difficulty_mix:
                    if difficulty_mix.get("easy", 0) == 1.0:
                        target_difficulty = "easy"
                    elif difficulty_mix.get("medium", 0) == 1.0:
                        target_difficulty = "medium"
                    elif difficulty_mix.get("hard", 0) == 1.0:
                        target_difficulty = "hard"
                
                worksheet_json = await self._generate_worksheet_with_llm(
                    context_with_metadata=context_for_retry,
                    pack_id=str(pack_id),
                    topic_text=topic_text or f"Topic {topic_id}",
                    normalized_topic_text=normalized_topic_text,
                    grade=grade or "",
                    subject=subject or "",
                    num_questions=num_questions,
                    mcq_count=mcq_count,
                    short_count=short_count,
                    allowed_concepts=allowed_concepts,
                    forbidden_concepts=forbidden_concepts,
                    target_difficulty=target_difficulty,
                    teacher_prompt=teacher_prompt,
                )
            except Exception as llm_error:
                logger.warning(f"LLM worksheet generation failed: {llm_error}", exc_info=True)
                # Only 1 attempt - raise immediately
                raise ValueError(
                    "Worksheet generation failed. Please try again or use a different topic. "
                    "If the error persists, check LLM/OpenAI configuration. Underlying error: " + str(llm_error)
                ) from llm_error
            questions_list = (worksheet_json or {}).get("questions", [])
            if len(questions_list) < num_questions:
                raise ValueError(
                    f"Generator returned {len(questions_list)} questions; required at least {num_questions}."
                )
            
            # Check time guard - if elapsed > 70s, skip validation and return best effort
            elapsed_time = time.monotonic() - request_start_time
            if elapsed_time > 70:
                logger.warning(f"Time guard triggered: elapsed={elapsed_time:.1f}s > 70s, accepting worksheet as-is (skipping strict validation)")
                # Accept worksheet without further validation to avoid timeout
                break
            
            # Early acceptance rule: If MCQ valid + topic valid + difficulty close enough, accept immediately
            from app.domains.content_ingestion.services.mcq_validator import validate_mcq
            mcq_valid, mcq_report = validate_mcq(questions_list)
            valid, report = self._validate_questions_topic(questions_list, topic_text or "")
            
            rag_log("validation", pack_id=str(pack_id), topic_text=topic_text or "", attempt=attempt + 1, valid=valid, report=report, questions_count=len(questions_list), mcq_valid=mcq_valid)
            
            # Early acceptance: MCQ valid + topic valid + difficulty within 10% threshold
            if mcq_valid and valid:
                # Check if difficulty is "close enough" (within 10% threshold)
                # For now, if MCQ and topic are valid, accept (difficulty check can be lenient)
                logger.info("Early acceptance: MCQ valid + topic valid, accepting worksheet")
                break
            
            if not valid:
                self._log_validation_fail_debug(
                    normalized_topic_text, expanded_query_terms, top5_ranges_for_debug,
                    (min_page_range, max_page_range), hits_for_retry[:15]
                )
                rag_log("error", step="VALIDATION_FAILED", pack_id=str(pack_id), topic_text=topic_text or "", report=report, page_range=f"{min_page_range}-{max_page_range}")
                raise ValueError("VALIDATION_FAILED: " + report)
            
            # If we get here, MCQ or topic validation failed but we continue (best effort)
            logger.warning(f"Validation issues but continuing: mcq_valid={mcq_valid}, topic_valid={valid}")
            break
        
        # Build citations list for API (chunk_id, document_id, page_range per hit)
        citations_list = []
        seen_citations = set()
        for hit in (concept_deduped + assessment_deduped):
            meta = hit.metadata or {}
            start = meta.get("page_start_pdf")
            end = meta.get("page_end_pdf")
            if start is not None and end is not None:
                page_range = f"{start}-{end}"
            elif start is not None:
                page_range = str(start)
            elif end is not None:
                page_range = str(end)
            else:
                page_range = ""
            ckey = (hit.document_id, hit.chunk_id, page_range, meta.get("pack_id", str(pack_id)))
            if ckey in seen_citations:
                continue
            seen_citations.add(ckey)
            citations_list.append({
                "chunk_id": hit.chunk_id,
                "document_id": hit.document_id,
                "page_range": page_range,
                "pack_id": meta.get("pack_id", str(pack_id)),
            })

        # Create cache entry
        worksheet_cache = WorksheetCache(
            signature_hash=signature_hash,
            pack_id=pack_id,
            topic_id=topic_id,
            topic_text=topic_text,
            grade=grade,
            subject=subject,
            difficulty_mix=difficulty_mix,
            num_questions=num_questions,
            worksheet_json=worksheet_json,
            chunk_ids_used=[hit.chunk_id for hit in (concept_deduped + assessment_deduped)],
            retrieval_metadata={
                "query": query_text,
                "top_k": top_k,
                "similarity_scores": [hit.similarity_score for hit in (concept_deduped + assessment_deduped)],
                "citations": citations_list,
                "chapter_page_range": f"{min_page_range}-{max_page_range}",
                "relevance_avg_sim": avg_sim,
                "relevance_keyword_hits": keyword_hits,
                "concept_context": {
                    "roles": concept_roles,
                    "chunks": len(concept_deduped),
                    "preferred_count": concept_preferred_count,
                    "backfill": concept_backfill,
                },
                "assessment_context": {
                    "roles": assessment_roles,
                    "chunks": len(assessment_deduped),
                    "preferred_count": assessment_preferred_count,
                    "backfill": assessment_backfill,
                },
            }
        )
        
        self.db.add(worksheet_cache)
        self.db.commit()
        self.db.refresh(worksheet_cache)
        setattr(worksheet_cache, "from_cache", False)
        
        total_request_ms = (time.monotonic() - request_start_time) * 1000
        logger.info(
            f"Generated worksheet: {worksheet_cache.id} | total_request_ms={total_request_ms:.0f} | "
            f"chapter_page_range={min_page_range}-{max_page_range} | relevance_avg_sim={avg_sim:.3f}"
        )
        rag_log(
            "worksheet_done",
            pack_id=str(pack_id),
            topic_text=topic_text or "",
            worksheet_id=str(worksheet_cache.id),
            chapter_page_range=f"{min_page_range}-{max_page_range}",
            relevance_avg_sim=round(avg_sim, 4),
            relevance_keyword_hits=keyword_hits,
            total_request_ms=round(total_request_ms, 0)
        )
        return worksheet_cache
    
    async def _generate_worksheet_with_llm(
        self,
        context_with_metadata: str,
        pack_id: str,
        topic_text: str,
        grade: str,
        subject: str,
        num_questions: int,
        mcq_count: int,
        short_count: int,
        allowed_concepts: Optional[List[str]] = None,
        forbidden_concepts: Optional[List[str]] = None,
        normalized_topic_text: Optional[str] = None,
        target_difficulty: Optional[str] = None,
        teacher_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate worksheet JSON using LLM with international-standard assessment prompt."""
        allowed = (allowed_concepts or [])[:15]
        forbidden = (forbidden_concepts or [])[:12]
        norm = (normalized_topic_text or topic_text or "").lower()
        is_algebraic = "algebra" in norm or "expression" in norm
        algebraic_rules = ""
        if is_algebraic:
            algebraic_rules = """
ALGEBRAIC EXPRESSION TOPIC — STRICT REQUIREMENTS:
- At least 8 out of 10 questions MUST include variables (x, y, a, b) or expressions like 2x+3, 3y-1, coefficients, constants.
- Include exactly: 3 "simplify expression" questions, 2 "evaluate for given variable values", 2 "identify terms/coefficients/constants", 1 "translate words to expression"; remaining can be mixed algebraic.
- MCQ options MUST be algebraic expressions (e.g. 2x+5, 3a-2), NOT number theory (no HCF, LCM, primes, integers).
- Do NOT write questions on prime numbers, factors, HCF, LCM, or integers unless the CONTEXT explicitly is about algebra.
"""

        difficulty_line = (
            f"- Target difficulty: {target_difficulty.upper()}. "
            if target_difficulty
            else "- Difficulty: ~20% easy, ~60% medium, ~20% hard. "
        )
        medium_requirement = ""
        if target_difficulty == "medium":
            medium_requirement = f"""
CRITICAL DIFFICULTY REQUIREMENT FOR MEDIUM:
- At least 2-3 out of {num_questions} questions MUST be multi-step.
- Multi-step means: "First find X, then use X to find Y" OR "Given A and B, find C" OR scenario-based problems requiring multiple operations.
- Examples of multi-step questions:
  * "If set A = {{1,2,3}} and set B = {{3,4,5}}, first find A∩B, then find (A∩B)∪{{6}}."
  * "A student has 5 books. First, identify how many are math books, then calculate the total cost."
- DO NOT write all single-step questions. At least 20% must require multiple steps.
"""
        hard_requirement = ""
        if target_difficulty == "hard":
            hard_requirement = f"""
CRITICAL DIFFICULTY REQUIREMENT FOR HARD:
- At least 3-4 out of {num_questions} questions MUST be multi-step OR require justification/explanation.
- Multi-step: "First find X, then use X to find Y, then verify Z" OR complex scenarios with multiple constraints.
- Justify/explain: Questions asking "justify", "explain why", "show that", "prove", "derive".
- Examples:
  * "Prove that if A⊆B and B⊆C, then A⊆C. Justify each step."
  * "Given sets A, B, C, first find A∪B, then find (A∪B)∩C, then explain why this equals (A∩C)∪(B∩C)."
- DO NOT write all single-step questions. At least 35% must be multi-step or justify/explain.
"""
        easy_requirement = (
            "- EASY difficulty: All questions should be single-step. "
            "No 'justify', 'explain why', 'prove', 'derive'. "
            "Simple recall or one-operation problems only. "
            if target_difficulty == "easy"
            else ""
        )

        system_message = f"""You are an international-standard assessment author and a strict JSON generator.

CRITICAL: You MUST generate questions strictly about the topic: "{topic_text}". Use ONLY the provided book excerpts. If excerpts do not contain the topic, do not invent content from other topics.

HARD RULES:
1) Output MUST be valid JSON only. No markdown, no explanations, no extra text.
2) Use ONLY the provided CONTEXT. Do not use outside knowledge.
3) Do NOT write "Based on the content/passage/context…" and do NOT ask to explain a paragraph.
4) Create real assessment items ONLY on the topic "{topic_text}":
   - MCQ: 4 options (A–D), exactly 1 correct, plausible distractors.
   - Short: concise answer (rule statement or computed result).
5) Return EXACTLY num_questions questions, numbered 1..num_questions.
6) Every question MUST include at least one citation: {{chunk_id, document_id, page_range}}.
7) Answers must NOT be copied verbatim from context. They must be short and student-facing.
8) Keep answers concise. Maximum 2 short sentences per explanation.
9) Marking criteria must be short bullet points, max 2 lines. Do NOT write long paragraphs.
10) Provide a professional marking scheme with mark allocation + acceptable answers + common errors (keep brief).
11) Allowed concepts (use these from the excerpts): {", ".join(allowed) if allowed else "from context"}.
12) FORBIDDEN: Do NOT write questions about: {", ".join(forbidden) if forbidden else "unrelated topics"}.
{algebraic_rules}

Generate an international-level worksheet and marking scheme in JSON. Return ONLY the final JSON."""

        user_prompt = f"""INPUT:
{{
  "pack_id": "{pack_id}",
  "topic_text": "{topic_text}",
  "grade": "{grade}",
  "subject": "{subject}",
  "num_questions": {num_questions},
  "mix": {{ "mcq": {mcq_count}, "short": {short_count} }}
}}

CONTEXT (authoritative book excerpts — use only this; cite chunk_id, document_id, page_range in each question):
{context_with_metadata}

OUTPUT JSON SCHEMA (MUST match exactly). Return ONLY this JSON, no other text:
{{
  "questions": [
    {{
      "question_id": 1,
      "type": "mcq" or "short",
      "difficulty": "easy" or "medium" or "hard",
      "question_text": "<string>",
      "math_content": true or false,
      "options": ["A) ...", "B) ...", "C) ...", "D) ..."],
      "correct_option": "A" or "B" or "C" or "D",
      "answer_text": "<string>",
      "marks": 1 or 2 or 3,
      "citations": [{{"chunk_id": "<string>", "document_id": "<string>", "page_range": "<string>"}}]
    }}
  ],
  "answer_key": [{{"question_id": 1, "answer": "<string>"}}],
  "marking_scheme": [
    {{
      "question_id": 1,
      "total_marks": 1,
      "mark_allocation": [{{"criteria": "<string>", "marks": 1}}],
      "acceptable_answers": ["<string>"],
      "common_errors": ["<string>"]
    }}
  ]
}}

QUESTION RULES:
- Exactly {mcq_count} MCQ and exactly {short_count} short questions.
{difficulty_line}
{medium_requirement}
{hard_requirement}
{easy_requirement}
- MCQ marks = 1. Short marks = 2 or 3.
- Every question must cite relevant chunks from CONTEXT. Use LaTeX for math: $formula$.
- Language: International English, grade-appropriate (Grade {grade}), short sentences, no advanced vocabulary.
""" + (
    """
- ALGEBRAIC TOPIC: At least 8/10 questions must include variables (x, y, a, b) or expressions (2x+3, coefficients, terms). Include: 3 simplify expression, 2 evaluate for given values, 2 identify terms/coefficients/constants, 1 translate words to expression. MCQ options must be algebraic expressions, not number theory."""
    if is_algebraic else ""
) + "\n" + (
    f"\nTEACHER STYLE / CONSTRAINTS (do not override topic or grade safety):\n{teacher_prompt.strip()}\n"
    if teacher_prompt and teacher_prompt.strip() else ""
)

        llm_start_time = time.monotonic()
        try:
            response = await self.llm_router.generate(
                system_message=system_message,
                prompt=user_prompt,
                model_config={
                    # Do not hard-code provider/model so fallback routing works in local/test.
                    # Defaults come from `llm_settings` (.env / environment).
                    "provider": getattr(llm_settings, "DEFAULT_MODEL_PROVIDER", "openai"),
                    "model": getattr(llm_settings, "DEFAULT_MODEL", "gpt-4o-mini"),
                    "temperature": 0.2,  # Reduced from 0.3 for more consistent, concise output
                    "max_tokens": 2200  # Increased to 2200 to avoid truncation while staying under 2500 target
                }
            )
            llm_call_ms = (time.monotonic() - llm_start_time) * 1000

            if not response or not hasattr(response, "content"):
                logger.error("LLM response is empty or missing content")
                raise RuntimeError("LLM returned empty response")

            content = response.content.strip() if response.content else ""
            if not content:
                logger.error("LLM response content is empty")
                raise RuntimeError("LLM returned empty content")

            # Check for truncation indicators
            finish_reason = getattr(response, "finish_reason", None)
            is_truncated = finish_reason == "length" or (len(content) > 1800 and not content.rstrip().endswith("}"))
            
            # Estimate token count (rough: 1 token ≈ 4 characters)
            estimated_tokens = len(content) // 4
            logger.info(f"LLM call completed: llm_call_ms={llm_call_ms:.0f}, estimated_tokens={estimated_tokens}, content_length={len(content)}, finish_reason={finish_reason}, truncated={is_truncated}")
            logger.debug(f"LLM response (first 500 chars): {content[:500]}")

            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            # Fix parsing crash: ensure content is parsed as JSON, not string
            # Add JSON repair for truncated responses
            if isinstance(content, str):
                try:
                    raw = json.loads(content)
                except json.JSONDecodeError as e:
                    # Try to repair truncated JSON
                    logger.warning(f"JSON parse error at char {e.pos}: {str(e)}")
                    logger.debug(f"Content length: {len(content)}, first 500 chars: {content[:500]}")
                    
                    # Try to extract valid JSON by finding the last complete "questions" array
                    if '"questions"' in content:
                        # Find the questions array start
                        q_start = content.find('"questions"')
                        if q_start != -1:
                            # Try to find the end of the questions array
                            bracket_count = 0
                            in_string = False
                            escape_next = False
                            q_array_start = content.find('[', q_start)
                            if q_array_start != -1:
                                bracket_count = 1
                                for i in range(q_array_start + 1, len(content)):
                                    char = content[i]
                                    if escape_next:
                                        escape_next = False
                                        continue
                                    if char == '\\':
                                        escape_next = True
                                        continue
                                    if char == '"' and not escape_next:
                                        in_string = not in_string
                                        continue
                                    if not in_string:
                                        if char == '[':
                                            bracket_count += 1
                                        elif char == ']':
                                            bracket_count -= 1
                                            if bracket_count == 0:
                                                # Found end of questions array
                                                repaired = content[:i+1] + ']}'
                                                try:
                                                    raw = json.loads(repaired)
                                                    logger.info("Successfully repaired truncated JSON")
                                                    break
                                                except Exception as repair_err:
                                                    logger.debug(f"Repair attempt failed: {repair_err}")
                                                    # Continue to next repair attempt
                                                break
                    
                    # If repair failed, try to extract just the questions array
                    if '"questions"' in content and 'raw' not in locals():
                        try:
                            # Extract questions array manually
                            q_start = content.find('"questions"')
                            q_array_start = content.find('[', q_start)
                            if q_array_start != -1:
                                # Find matching closing bracket
                                bracket_count = 1
                                in_string = False
                                escape_next = False
                                for i in range(q_array_start + 1, min(len(content), q_array_start + 50000)):
                                    char = content[i]
                                    if escape_next:
                                        escape_next = False
                                        continue
                                    if char == '\\':
                                        escape_next = True
                                        continue
                                    if char == '"' and not escape_next:
                                        in_string = not in_string
                                        continue
                                    if not in_string:
                                        if char == '[':
                                            bracket_count += 1
                                        elif char == ']':
                                            bracket_count -= 1
                                            if bracket_count == 0:
                                                questions_json = content[q_array_start:i+1]
                                                questions = json.loads(questions_json)
                                                # Build minimal valid structure
                                                raw = {
                                                    "questions": questions,
                                                    "answer_key": {},
                                                    "marking_scheme": {}
                                                }
                                                logger.warning("Extracted questions from truncated JSON, using minimal structure")
                                                break
                        except Exception as repair_error:
                            logger.error(f"JSON repair failed: {repair_error}")
                    
                    # If still failed, raise original error with truncation info
                    if 'raw' not in locals():
                        truncation_hint = ""
                        if is_truncated or finish_reason == "length":
                            truncation_hint = " Response appears truncated. Consider increasing max_tokens or reducing num_questions."
                        raise ValueError(
                            f"Invalid JSON returned from LLM: {str(e)}. "
                            f"Content length: {len(content)}, estimated tokens: {estimated_tokens}. "
                            f"Finish reason: {finish_reason}.{truncation_hint}"
                        )
            else:
                raw = content
            
            # Validate structure
            if not isinstance(raw, dict):
                raise ValueError(f"LLM returned non-dict type: {type(raw)}")
            if "questions" not in raw:
                raise ValueError("Generated worksheet missing 'questions' field")

            # Normalize to existing API format (id "q1", question, correct_answer, answer_key dict, marking_scheme dict)
            worksheet_data = self._normalize_worksheet_to_api_format(raw)
            
            # Log token usage
            estimated_tokens = len(content) // 4
            logger.info(f"Worksheet normalized: estimated_tokens={estimated_tokens}, questions_count={len(worksheet_data.get('questions', []))}")
            
            return worksheet_data

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse worksheet JSON: {e}")
            logger.error(f"Response content: {content[:1000] if 'content' in locals() else 'N/A'}")
            if not content or len(content.strip()) == 0:
                raise RuntimeError(
                    "LLM returned empty response. Check OpenAI API configuration: "
                    "OPENAI_API_KEY and OPENAI_BASE_URL must be valid."
                )
            raise ValueError(f"Invalid JSON in LLM response: {str(e)}. Content: {content[:200]}")
        except Exception as e:
            logger.error(f"Worksheet generation failed: {e}", exc_info=True)
            error_msg = str(e)
            if "api.opeanai.com" in error_msg.lower() or "invalid api key" in error_msg.lower():
                error_msg += ". Check OPENAI_BASE_URL in .env (may have typo: 'opeanai' instead of 'openai')"
            raise RuntimeError(f"Worksheet generation failed: {error_msg}")

    def _normalize_worksheet_to_api_format(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Map LLM output to existing API format. Handles both new schema (question_id, question_text) and legacy (id, question)."""
        questions_raw = raw.get("questions", [])
        if not questions_raw:
            return {"questions": [], "answer_key": {}, "marking_scheme": {}}

        # Legacy format: questions have "id" (e.g. "q1") and "question" (text)
        first = questions_raw[0]
        is_legacy = "id" in first and "question" in first and "question_id" not in first
        if is_legacy:
            return {
                "questions": questions_raw,
                "answer_key": raw.get("answer_key", {}),
                "marking_scheme": raw.get("marking_scheme", {}),
            }

        questions_out = []
        answer_key_out: Dict[str, str] = {}
        marking_scheme_out: Dict[str, Dict[str, Any]] = {}

        for q in questions_raw:
            qid_num = q.get("question_id", len(questions_out) + 1)
            qid_str = f"q{qid_num}"
            q_type = (q.get("type") or "short").lower()
            if q_type not in ("mcq", "short"):
                q_type = "short"
            question_text = q.get("question_text") or q.get("question", "")
            correct_option = q.get("correct_option")
            answer_text = q.get("answer_text") or q.get("correct_answer", "")
            correct_answer = correct_option if q_type == "mcq" and correct_option else answer_text
            options = q.get("options") if q_type == "mcq" else None
            marks = q.get("marks") or q.get("points", 1)
            difficulty = q.get("difficulty") or "medium"
            math_content = bool(q.get("math_content", False))

            questions_out.append({
                "id": qid_str,
                "type": "mcq" if q_type == "mcq" else "short_answer",
                "question": question_text,
                "options": options,
                "correct_answer": correct_answer,
                "explanation": None,
                "points": marks,
                "difficulty": difficulty,
                "math_content": math_content,
            })
            answer_key_out[qid_str] = correct_answer

            ms_entry = None
            for m in raw.get("marking_scheme", []):
                if m.get("question_id") == qid_num:
                    ms_entry = m
                    break
            if ms_entry:
                total_marks = ms_entry.get("total_marks", marks)
                allocation = ms_entry.get("mark_allocation", [])
                criteria_parts = [a.get("criteria", "") for a in allocation if a.get("criteria")]
                acceptable = ms_entry.get("acceptable_answers", [])
                common = ms_entry.get("common_errors", [])
                if acceptable:
                    criteria_parts.append("Acceptable: " + "; ".join(acceptable[:3]))
                if common:
                    criteria_parts.append("Common errors: " + "; ".join(common[:2]))
                marking_scheme_out[qid_str] = {
                    "points": total_marks,
                    "criteria": " ".join(criteria_parts) if criteria_parts else "See mark allocation.",
                }
            else:
                marking_scheme_out[qid_str] = {"points": marks, "criteria": "Answer as per context."}

        return {
            "questions": questions_out,
            "answer_key": answer_key_out,
            "marking_scheme": marking_scheme_out,
        }
    
    def _resolve_difficulty_mix(
        self,
        difficulty: Optional[str],
        difficulty_mix: Optional[Dict[str, float]],
    ) -> Dict[str, float]:
        if difficulty == "easy":
            return {"easy": 1.0, "medium": 0.0, "hard": 0.0}
        if difficulty == "medium":
            return {"easy": 0.0, "medium": 1.0, "hard": 0.0}
        if difficulty == "hard":
            return {"easy": 0.0, "medium": 0.0, "hard": 1.0}
        if difficulty_mix:
            return difficulty_mix
        return {"easy": 0.3, "medium": 0.5, "hard": 0.2}

    def _strip_option_letter_prefix(self, text: str) -> str:
        import re as _re
        return _re.sub(r'^[A-Za-z][).]\s*', '', text)

    def _build_difficulty_contract(
        self,
        difficulty: Optional[str],
        difficulty_mix: Optional[Dict[str, float]],
    ) -> str:
        if not difficulty:
            return ""
        level = difficulty.upper()
        return f"DIFFICULTY CONTRACT: {level}\nAll questions must be {level} difficulty."

    def _generate_signature_hash(
        self,
        pack_id: UUID,
        topic_id: Optional[str],
        topic_text: Optional[str],
        grade: Optional[str],
        subject: Optional[str],
        difficulty_mix: Optional[Dict[str, float]],
        num_questions: int,
        pack_ids: Optional[List[UUID]] = None,
        teacher_prompt: Optional[str] = None,
    ) -> str:
        """Generate cache signature hash."""
        signature_data = {
            "pack_id": str(pack_id),
            "pack_ids": sorted(str(p) for p in (pack_ids or [])),
            "topic_id": topic_id or "",
            "topic_text": topic_text or "",
            "grade": grade or "",
            "teacher_prompt": (teacher_prompt or "")[:200],
            "subject": subject or "",
            "difficulty_mix": json.dumps(difficulty_mix, sort_keys=True) if difficulty_mix else "",
            "num_questions": num_questions,
            "format_version": "1.5"  # 2-stage retrieval, topic relevance gate, prompt contract, post-validation
        }
        
        signature_str = json.dumps(signature_data, sort_keys=True)
        return hashlib.sha256(signature_str.encode()).hexdigest()
    
    def _text_based_search(
        self,
        pack_id: UUID,
        query_text: str,
        topic_id: Optional[str],
        top_k: int,
        pack_ids: Optional[List[UUID]] = None,
    ) -> List[VectorHit]:
        """
        Fallback text-based search when vector search isn't available (e.g., fake embeddings).
        Searches chunks by keyword matching and returns top_k results.
        """
        # Extract keywords from query text
        keywords = [w.lower().strip() for w in query_text.split() if len(w) > 2]
        
        # Query chunks from published documents in this pack (or packs)
        base = self.db.query(Chunk, Document.pack_id).join(Document).filter(
            Document.status == "published",
            Chunk.embedding_v.isnot(None)  # Only chunks with embeddings
        )
        if pack_ids and len(pack_ids) > 0:
            base = base.filter(Document.pack_id.in_(pack_ids))
        else:
            base = base.filter(Document.pack_id == pack_id)
        
        if topic_id:
            base = base.filter(Chunk.topic_id == topic_id)
        
        # Score chunks by keyword matches
        rows = base.limit(top_k * 2).all()  # Get more to filter
        
        scored_chunks = []
        for chunk, doc_pack_id in rows:
            text_lower = chunk.text.lower()
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > 0 or not keywords:  # Include all if no keywords or if matches found
                scored_chunks.append((score, chunk, doc_pack_id))
        
        # Sort by score (descending) and take top_k
        scored_chunks.sort(key=lambda x: x[0], reverse=True)
        top_chunks = [(chunk, doc_pack_id) for _, chunk, doc_pack_id in scored_chunks[:top_k]]
        
        # Convert to VectorHit format (include page range in metadata for citations)
        hits = []
        for chunk, doc_pack_id in top_chunks:
            text_lower = chunk.text.lower()
            match_count = sum(1 for kw in keywords if kw in text_lower) if keywords else 1
            similarity = min(1.0, 0.5 + (match_count / max(len(keywords), 1)) * 0.5)
            meta = dict(chunk.metadata_json or {})
            meta["pack_id"] = str(doc_pack_id or pack_id)
            if chunk.page_start_pdf is not None:
                meta["page_start_pdf"] = chunk.page_start_pdf
            if chunk.page_end_pdf is not None:
                meta["page_end_pdf"] = chunk.page_end_pdf
            hits.append(VectorHit(
                chunk_id=chunk.chunk_id,
                document_id=str(chunk.document_id),
                text=chunk.text,
                similarity_score=similarity,
                metadata=meta if meta else None
            ))
        
        logger.info(f"Text-based search returned {len(hits)} chunks for query: {query_text}")
        return hits
    
    def _generate_simple_worksheet(
        self,
        chunks: List[str],
        topic_text: str,
        num_questions: int
    ) -> Dict[str, Any]:
        """
        Generate a simple worksheet from chunks without LLM.
        Creates basic comprehension questions from the content.
        """
        questions = []
        answer_key = {}
        marking_scheme = {}
        
        # Use first few chunks to generate questions
        content_text = "\n".join(chunks[:5])  # Use first 5 chunks
        
        # Simple question generation: create questions based on sentences in content
        sentences = [s.strip() for s in content_text.split('.') if len(s.strip()) > 20][:num_questions]
        
        for i, sentence in enumerate(sentences[:num_questions], 1):
            q_id = f"q{i}"
            
            # Create a simple comprehension question
            question_text = f"Based on the content, explain: {sentence[:100]}..."
            
            questions.append({
                "id": q_id,
                "type": "short_answer",
                "question": question_text,
                "correct_answer": sentence[:200],  # Required field
                "explanation": f"This answer is based on the content: {sentence[:150]}...",
                "points": 2,
                "difficulty": "medium",
                "math_content": False
            })
            
            answer_key[q_id] = sentence[:200]  # Use sentence as answer
            marking_scheme[q_id] = {
                "points": 2,
                "criteria": "Answer should reference the content provided"
            }
        
        return {
            "questions": questions,
            "answer_key": answer_key,
            "marking_scheme": marking_scheme,
            "citations": [{"chunk_id": f"chunk_{i}", "text": chunk[:100]} for i, chunk in enumerate(chunks[:3])]
        }
    
    def _normalize_topic_for_keywords(self, topic_text: str) -> str:
        """Normalize topic for keyword extraction (e.g. algebric -> algebraic). Keeps display as-is."""
        if not topic_text or not topic_text.strip():
            return topic_text or ""
        t = topic_text.strip().lower()
        # Common misspellings / variants
        replacements = {"algebric": "algebraic", "algabraic": "algebraic", "algerbraic": "algebraic"}
        for wrong, right in replacements.items():
            t = t.replace(wrong, right)
        return t

    def _expand_query_synonyms(self, topic_text: str) -> List[str]:
        """Expand topic with synonyms for retrieval. Normalize typos (algebric -> algebraic)."""
        normalized = self._normalize_topic_for_keywords(topic_text or "")
        topic_lower = (topic_text or "").lower() + " " + normalized
        out = []
        # Base terms from normalized topic
        out.extend(re.findall(r"[a-zA-Z0-9]+", normalized))
        # Algebraic expression: full synonym set
        if "algebra" in topic_lower or "expression" in topic_lower:
            out.extend([
                "algebra", "expression", "algebraic term", "variable", "coefficient", "constant",
                "simplify expression", "like terms", "unlike terms", "evaluate expression",
                "substitution", "distributive property", "algebraic expression",
                "term", "simplify", "evaluate", "translate words to expression",
            ])
        # Prime/factors
        if "prime" in topic_lower or "factor" in topic_lower:
            out.extend(["prime", "factor", "factorization", "composite", "hcf", "lcm"])
        # Sets
        if "set" in topic_lower:
            out.extend(["set", "element", "subset", "union", "intersection"])
        # Minimal Urdu/roman (common in PK curricula)
        if "algebra" in topic_lower or "expression" in topic_lower:
            out.extend(["jabar", "ibarat"])  # algebra, expression in Urdu roman
        return list(dict.fromkeys(w for w in out if len(w) > 1))[:25]

    def _extract_topic_keywords(self, topic_text: str) -> List[str]:
        """Extract keywords from topic for relevance and validation. Generic, no hardcoded topics."""
        normalized = self._normalize_topic_for_keywords(topic_text or "")
        words = re.findall(r"[a-zA-Z0-9]+", normalized)
        keywords = [w.lower() for w in words if len(w) >= 2 and w.lower() not in ("the", "and", "for", "from", "with", "this", "that")]
        topic_lower = (topic_text or "").lower() + " " + normalized
        if "algebra" in topic_lower or "expression" in topic_lower:
            keywords.extend(["algebraic", "expression", "term", "coefficient", "variable", "constant", "simplify", "evaluate", "like", "unlike", "translate"])
        if "prime" in topic_lower or "factor" in topic_lower:
            keywords.extend(["prime", "factor", "factorization", "composite", "hcf", "lcm"])
        if "set" in topic_lower:
            keywords.extend(["set", "element", "subset", "union", "intersection"])
        return list(dict.fromkeys(keywords))

    def _log_validation_fail_debug(
        self,
        normalized_topic_text: str,
        expanded_query_terms: List[str],
        top5_ranges: List[Tuple[Tuple[int, int], float]],
        final_page_range: Tuple[int, int],
        hits: List[VectorHit],
    ) -> None:
        """Log debug dump when topic validation fails (server logs)."""
        logger.warning(
            "[VALIDATION_FAIL DEBUG] normalized_topic_text=%s | expanded_query_terms=%s",
            normalized_topic_text, expanded_query_terms[:15],
        )
        logger.warning(
            "[VALIDATION_FAIL DEBUG] top 5 chapter candidate ranges (score): %s",
            [(r, round(s, 4)) for r, s in top5_ranges],
        )
        logger.warning(
            "[VALIDATION_FAIL DEBUG] final selected page_range(s): %s-%s",
            final_page_range[0], final_page_range[1],
        )
        for i, h in enumerate(hits[:15]):
            meta = h.metadata or {}
            start = meta.get("page_start_pdf")
            end = meta.get("page_end_pdf")
            pr = f"{start}-{end}" if start is not None and end is not None else str(start or end or "")
            sim = getattr(h, "similarity_score", None)
            text_preview = (h.text or "")[:200]
            logger.warning(
                "[VALIDATION_FAIL DEBUG] chunk[%s] chunk_id=%s page=%s similarity=%s text_preview=%s",
                i, h.chunk_id, pr, sim, text_preview,
            )

    def _raise_topic_not_found(
        self,
        top5_ranges: List[Tuple[Tuple[int, int], float]],
        chosen_ranges: List[Tuple[int, int]],
        hits_after_front: List[VectorHit],
        topic_text: str,
        relevance_hits: Optional[List[VectorHit]] = None,
        avg_sim: float = 0.0,
        keyword_hits: int = 0,
    ) -> None:
        """Raise 422 with TOPIC_NOT_FOUND_IN_PACK and top 3 closest ranges + why insufficient."""
        keywords = self._extract_topic_keywords(topic_text)
        top3 = top5_ranges[:3]
        parts = []
        for (lo, hi), score in top3:
            range_hits = [h for h in hits_after_front if (h.metadata or {}).get("page_start_pdf") is not None and lo <= (h.metadata or {}).get("page_start_pdf", 0) <= hi]
            r_sim, r_kw = self._relevance_score(range_hits, topic_text) if range_hits else (0.0, 0)
            parts.append(f"pages {lo}-{hi}: score={score:.3f}, avg_sim={r_sim:.3f}, keyword_hits={r_kw} (need avg_sim>=0.32, keyword_hits>=2)")
        msg = "TOPIC_NOT_FOUND_IN_PACK: No chapter with sufficient relevance. Closest ranges: " + "; ".join(parts)
        if relevance_hits is not None:
            msg += f" Best attempt had avg_sim={avg_sim:.3f}, keyword_hits={keyword_hits}."
        rag_log("error", step="TOPIC_NOT_FOUND_IN_PACK", topic_text=topic_text, top3_ranges=parts, best_avg_sim=avg_sim, best_keyword_hits=keyword_hits)
        raise ValueError(msg)

    def _relevance_score(self, hits: List[VectorHit], topic_text: str) -> Tuple[float, int]:
        """Return (avg_similarity, keyword_hit_count) for topic relevance gate."""
        if not hits:
            return 0.0, 0
        keywords = self._extract_topic_keywords(topic_text)
        avg_sim = sum(getattr(h, "similarity_score", 0) for h in hits) / len(hits)
        context_text = " ".join(h.text for h in hits).lower()
        hit_count = sum(1 for kw in keywords if kw in context_text)
        return avg_sim, hit_count

    def _build_allowed_forbidden(self, context_text: str, topic_text: str) -> Tuple[List[str], List[str]]:
        """Build allowed concepts (from context) and forbidden concepts (unless in topic)."""
        # Extract top terms from context (words with 4+ chars, not stopwords)
        words = re.findall(r"[a-zA-Z]+", context_text.lower())
        stop = {"the", "and", "for", "from", "with", "this", "that", "which", "when", "what", "have", "has", "been", "were", "will", "your", "that", "they", "them"}
        freq = defaultdict(int)
        for w in words:
            if len(w) >= 4 and w not in stop:
                freq[w] += 1
        allowed = [w for w, _ in sorted(freq.items(), key=lambda x: -x[1])[:15]]
        # Forbidden: generic math that causes drift unless topic mentions them
        topic_lower = (topic_text or "").lower()
        forbidden_default = ["hcf", "lcm", "highest common factor", "lowest common multiple", "prime factorization", "prime number", "composite number", "absolute value", "integers", "integer"]
        forbidden = [f for f in forbidden_default if f.replace(" ", "") not in topic_lower.replace(" ", "")]
        return allowed, forbidden

    def _validate_questions_topic(self, questions: List[Dict[str, Any]], topic_text: str) -> Tuple[bool, str]:
        """Validate that questions match topic. Return (passed, report)."""
        if not questions:
            return False, "No questions to validate."
        keywords = self._extract_topic_keywords(topic_text)
        topic_lower = (topic_text or "").lower()
        normalized = self._normalize_topic_for_keywords(topic_text or "")
        # Forbidden drift terms (unless in topic)
        drift_terms = ["hcf", "lcm", "prime number", "composite", "factorization", "absolute value", "integer"]
        if "prime" in topic_lower or "factor" in topic_lower:
            drift_terms = [t for t in drift_terms if t not in ("prime number", "composite", "factorization", "hcf", "lcm")]
        match_count = 0
        drift_violations = []
        algebraic_ok = True
        for i, q in enumerate(questions):
            qtext = (q.get("question") or q.get("question_text") or "").lower()
            if any(kw in qtext for kw in keywords):
                match_count += 1
            for term in drift_terms:
                if term in qtext and term not in topic_lower:
                    drift_violations.append(f"Q{i+1}: contains '{term}'")
            # Algebraic expression: must have variable/expression vocab or symbols
            if "algebra" in normalized or "expression" in topic_lower:
                has_var = any(x in qtext for x in ["x", "y", "variable", "coefficient", "term", "simplify", "evaluate", "expression", "2x", "3y", "like terms"])
                if not has_var and len(qtext) > 20:
                    algebraic_ok = False
        need_match = max(7, int(len(questions) * 0.7))
        passed = match_count >= need_match and not drift_violations and (algebraic_ok or "algebra" not in normalized)
        report = f"Topic match: {match_count}/{len(questions)} (need {need_match})."
        if drift_violations:
            report += " Drift: " + "; ".join(drift_violations[:5])
        if not algebraic_ok and ("algebra" in normalized or "expression" in topic_lower):
            report += " Algebraic questions should use variables/expressions."
        return passed, report

    def get_worksheet(self, worksheet_id: UUID) -> Optional[WorksheetCache]:
        """Get cached worksheet by ID."""
        return self.db.query(WorksheetCache).filter(
            WorksheetCache.id == worksheet_id
        ).first()
