# Content Ingestion + Worksheet Generation Upgrade — Deliverables

**Date:** 2026-02-13  
**Scope:** Silicon-level, international-grade, scalable across boards; minimal architectural changes; backward compatible.

---

## A) Exact File Modification List

| File | Change |
|------|--------|
| `app/core/config.py` | Added `OCR_MODE`, `OCR_ENGINE_DEFAULT`, `OCR_FALLBACK_ENGINE`. |
| `app/domains/content_ingestion/providers/base.py` | Added `OCRPageResult`, `OCRResult` dataclasses. |
| `app/domains/content_ingestion/ocr/__init__.py` | **New.** OCR decision module exports. |
| `app/domains/content_ingestion/ocr/decision.py` | **New.** Central OCR decision: `decide_ocr_required`, `resolve_ocr_engine`, `get_ocr_provider_for_engine`, `page_text_list_to_ocr_result`. |
| `app/domains/content_ingestion/providers/ocr_providers.py` | Added `GoogleDocumentAIOCRProvider` stub. |
| `app/domains/content_ingestion/models.py` | `ContentPack`: added `ocr_policy` (String, default `"auto"`). `Document`: added `structure_map` (JSONB, optional). |
| `app/domains/content_ingestion/services/ingestion_service.py` | Use central OCR decision; store `ocr_used`, `ocr_engine_used`, `ocr_mode`, `ocr_decision_reason`, `ocr_warnings` in `processing_metadata`; call `assign_chunk_roles(chunks, document.structure_map)` after chunking. |
| `app/domains/content_ingestion/services/role_tagger.py` | **New.** Role taxonomy, auto-tag heuristics, `structure_map` override; `assign_chunk_roles()`. |
| `app/domains/content_ingestion/providers/vector_stores.py` | Query: support `pack_ids` (multi-pack), `filters["roles"]` (role filter); include `documents.pack_id` in SELECT for citations. |
| `app/domains/content_ingestion/schemas.py` | `WorksheetGenerateRequest`: added `pack_ids`, `teacher_prompt`, `teacher_reference_images` (placeholder). |
| `alembic/versions/add_ocr_policy_and_structure_map.py` | **New.** Migration: add `content_packs.ocr_policy`, `documents.structure_map`. |

**Planned (not all implemented in this pass):**  
- Worksheet service: `pack_ids` / multi-pack retrieval, `teacher_prompt` in prompt, role-aware two-context retrieval (concept + assessment), shallow-topic broadening, timing logs (signature_hash_ms, retrieval_ms, llm_call_ms, validation_ms), early-accept with difficulty warning.  
- These can be added in a follow-up pass using the same abstractions (role in chunk metadata, vector_store `roles`/`pack_ids` support, schemas already extended).

---

## B) DB Migration Plan

- **Prefer JSON/columns over new tables:** No new tables.
- **New columns:**
  - `content_packs.ocr_policy` — `VARCHAR(50)`, nullable, server default `'auto'`. Values: `math` | `non_math` | `auto`.
  - `documents.structure_map` — `JSONB`, nullable. Format: `[{"page_start": 10, "page_end": 15, "role": "worked_example"}, ...]`.
- **Existing:** `Document.processing_metadata` stores OCR decision metadata (`ocr_used`, `ocr_engine_used`, `ocr_mode`, `ocr_decision_reason`, `ocr_warnings`).  
- **Chunk role:** Stored in existing `chunks.metadata_json->>'role'` (no new column).
- **Migration file:** `alembic/versions/add_ocr_policy_and_structure_map.py` (revises `da71b2113835`).

---

## C) Updated Pydantic Schemas

- **WorksheetGenerateRequest:**  
  - `pack_id: UUID` (unchanged; used when `pack_ids` not provided).  
  - `pack_ids: Optional[List[UUID]] = None` — if set, overrides single-pack retrieval.  
  - `teacher_prompt: Optional[str] = None` — appended as STYLE/CONSTRAINT layer.  
  - `teacher_reference_images: Optional[List[str]] = None` — placeholder only.
- **Content pack:** Expose `ocr_policy` in create/response if desired (optional; DB column added).

---

## D) OCR Provider Abstraction Design

- **Unified result:** `OCRResult(pages: List[OCRPageResult], meta: Dict)` with `OCRPageResult(page_no, text, optional latex_text)` and `meta: {provider, duration_ms, warnings}`.
- **Existing providers** continue to return `List[PageText]`; adapter `page_text_list_to_ocr_result()` builds `OCRResult` for metadata/logging.
- **Base:** `OCRProvider` interface unchanged; optional `run_ocr_return_result()` could return `OCRResult` in future.
- **Implementations:**  
  - `LocalTesseractOCRProvider` (existing `TesseractOCRProvider`).  
  - `EasyOCRProvider` (existing).  
  - `MathpixOCRProvider` (stub).  
  - `GoogleDocumentAIOCRProvider` (stub; checks env keys, no crash if missing).
- **Resolution:** Single function returns provider instance by engine name; falls back to `OCR_FALLBACK_ENGINE` if unknown or misconfigured.

---

## E) Central OCR Decision Pseudocode

```
FUNCTION decide_ocr_required(force_ocr, skip_ocr, pages, source_type):
  IF force_ocr THEN RETURN (True, "force_ocr=True")
  IF skip_ocr THEN RETURN (False, "skip_ocr=True")
  IF source_type != "pdf" THEN RETURN (False, "source_type is not pdf")
  IF pages is empty THEN RETURN (True, "no_pages_extracted")
  total_chars = sum(page.char_count for page in pages)
  IF total_chars == 0 THEN RETURN (True, "extracted_text_empty")
  avg_chars = total_chars / len(pages)
  IF avg_chars < SCANNED_THRESHOLD_CHARS THEN RETURN (True, "avg_chars_below_threshold")
  RETURN (False, "text_sufficient_no_ocr")

FUNCTION resolve_ocr_engine(ocr_engine_override, pack_ocr_policy):
  ocr_mode = config.OCR_MODE  # "local" | "api"
  default_engine = config.OCR_ENGINE_DEFAULT
  fallback_engine = config.OCR_FALLBACK_ENGINE
  candidate = ocr_engine_override OR pack_ocr_policy OR default_engine

  IF pack_ocr_policy == "math" AND NOT override:
    IF ocr_mode == "api" AND (mathpix OR google_document_ai) has keys:
      RETURN that engine
    ELSE use fallback_engine, WARNING "API keys missing or OCR_MODE=local"
  IF pack_ocr_policy == "non_math" AND candidate in (mathpix, google_document_ai):
    candidate = fallback_engine
  IF ocr_mode == "local" AND candidate in (mathpix, google_document_ai):
    candidate = fallback_engine, WARNING "OCR_MODE=local"
  IF ocr_mode == "api" AND candidate is API AND keys missing:
    candidate = fallback_engine, WARNING "API keys missing"
  RETURN engine_resolved = candidate, ocr_mode, warnings
```

---

## F) Updated WorksheetService Prompt Skeleton (Role-Aware)

- **Two contexts (when role tagging present):**  
  - **CONCEPT CONTEXT** (roles: `concept`, `worked_example`): up to 6–8 chunks.  
  - **ASSESSMENT CONTEXT** (roles: `exercise_prompt`, `exam_question`): up to 6–8 chunks.  
- **Build prompt:**  
  - "Use CONCEPT CONTEXT for definitions and worked examples; use ASSESSMENT CONTEXT for question style and difficulty."  
  - If `teacher_prompt` provided: append "TEACHER STYLE / CONSTRAINTS: {teacher_prompt}" (must not override topic or grade safety).  
- **Shallow topic:** If relevance low, do not return "Topic not found"; broaden retrieval within same chapter range and include assessment_context aggressively; only fail if no chunks at all.
- **Timing:** Log `signature_hash_ms`, `retrieval_ms`, `llm_call_ms`, `validation_ms`; early accept when MCQ valid + topic aligned, log warning if difficulty slightly below threshold.

---

## G) Tagging Heuristic List (Board-Agnostic)

| Pattern / source | Role |
|------------------|------|
| `Exercise \d+` | exercise_prompt |
| `Example \d+` | worked_example |
| `Review Exercise` | exercise_prompt |
| `(i)`, `(ii)`, `[1]` style | exercise_prompt |
| `1.` / `1)` numbered list | exercise_prompt |
| Verbs: Solve, Find, Prove, Show, Evaluate, Simplify | exercise_prompt |
| `Solution:` / `Answer:` | solution |
| `Marking scheme` / `Marking criteria` | marking_scheme |
| `Exam question` | exam_question |
| `[[MATH]]` block | concept (default for math-heavy) |
| No match | concept (default) |
| **structure_map** (page_start, page_end, role) | Override auto-tag for that page range |

---

## H) 5 Manual Test Cases + Expected Logs

1. **OCR decision — text sufficient**  
   - Upload a digital PDF with >50 chars/page.  
   - **Expected:** `ocr_used: false`, `ocr_decision_reason: "text_sufficient_no_ocr"` in `processing_metadata`; no OCR step.

2. **OCR decision — scanned, pack_ocr_policy=auto**  
   - Create pack with `ocr_policy=auto` (or null). Upload scanned PDF (or force_ocr=True).  
   - **Expected:** `ocr_used: true`, `ocr_engine_used: "tesseract"` (or configured default), `ocr_mode: "local"`; logs "engine_resolved", "step_complete" for ocr_running.

3. **OCR decision — OCR_MODE=local, pack_ocr_policy=math**  
   - Set `OCR_MODE=local`, pack `ocr_policy=math`. Trigger OCR.  
   - **Expected:** Fallback to tesseract; `ocr_warnings` or log: "OCR_MODE=local; API engine not allowed, using fallback".

4. **Role tagging**  
   - Ingest a PDF that contains "Example 1" and "Exercise 2" in text.  
   - **Expected:** Chunks with those phrases have `metadata_json.role` = `worked_example` and `exercise_prompt` respectively (or from structure_map if provided).

5. **Worksheet multi-pack (when implemented)**  
   - Call `POST /worksheets/generate` with `pack_ids: [uuid1, uuid2]` (and optional `teacher_prompt`).  
   - **Expected:** Retrieval runs over both packs; citations include `pack_id`; no crash; 200 and valid worksheet when content exists.

---

## Backward Compatibility Summary

- Existing `pack_id`-only calls work unchanged.  
- Existing OCR engines (tesseract, easyocr) unchanged; new decision layer only.  
- All new fields optional; no breaking schema changes.  
- Cache signature can be extended to include `pack_ids` and `teacher_prompt` when those are used in generation.
