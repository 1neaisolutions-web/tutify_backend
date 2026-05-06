# Content Ingestion + RAG Worksheet Generation

## Overview

This module implements an end-to-end system for ingesting international curriculum content and generating worksheets using RAG (Retrieval-Augmented Generation).

## Architecture

### Domain Structure
```
app/domains/content_ingestion/
├── models.py              # Database models
├── enums.py               # Status enums
├── schemas.py             # Pydantic schemas
├── routes.py              # API endpoints
├── jobs.py                # Background jobs
├── providers/             # Provider interfaces & implementations
│   ├── base.py           # Abstract base classes
│   ├── ocr_providers.py  # Tesseract, Mathpix (stub)
│   ├── text_extractors.py # PDF, DOCX extractors
│   ├── chunkers.py       # Text chunking
│   ├── embedding_providers.py # OpenAI embeddings
│   └── vector_stores.py   # pgvector implementation
└── services/             # Business logic
    ├── content_pack_service.py
    ├── document_service.py
    ├── ingestion_service.py
    ├── qa_service.py
    └── worksheet_service.py
```

## Database Models

- **ContentPack**: Organizes curriculum documents
- **Document**: Document metadata and processing status
- **PageText**: Per-page extracted text
- **Chunk**: Text chunks with embeddings (pgvector)
- **DocumentProcessingRun**: Processing history
- **QAValidation**: Quality assurance results
- **WorksheetCache**: Cached worksheet generation results

## State Machine

```
UPLOADED → TEXT_EXTRACTING → OCR_RUNNING (conditional)
→ NORMALIZING → CHUNKING → EMBEDDING → INDEXING
→ QA_VALIDATION → PUBLISHED
FAILED (from any step)
```

## Environment Variables

```bash
# OCR Configuration
OCR_ENGINE=tesseract  # tesseract | mathpix

# Embedding Configuration
EMBEDDING_PROVIDER=openai  # openai | cohere | sentence-transformers

# Vector Store Configuration
VECTOR_STORE=pgvector  # pgvector | qdrant | pinecone

# Processing Configuration
# Global defaults (backwards-compat)
CHUNK_SIZE_TOKENS=500
CHUNK_OVERLAP_TOKENS=50
MIN_CHARS_PER_PAGE=100
SCANNED_THRESHOLD_CHARS=50

# Adaptive chunking profiles
# Digital documents (standard PDFs with text layer)
CHUNK_SIZE_TOKENS_DIGITAL=500
CHUNK_OVERLAP_TOKENS_DIGITAL=50
# OCR / scanned documents (smaller chunks, more coverage; target 200–250)
CHUNK_SIZE_TOKENS_OCR=220
CHUNK_OVERLAP_TOKENS_OCR=50
# Minimum number of chunks required for OCR docs before triggering rechunk
OCR_MIN_CHUNKS_THRESHOLD=20
# For small OCR docs (pages < OCR_MIN_PAGES_FOR_THRESHOLD): use lower threshold
OCR_MIN_PAGES_FOR_THRESHOLD=30
OCR_MIN_CHUNKS_THRESHOLD_SMALL=10
# Deterministic rechunk size when below threshold
OCR_RECHUNK_SIZE_TOKENS=200

# Role-bucket retrieval: minimum chunks per bucket before backfill from remaining relevant chunks
BUCKET_MIN_TARGET=4

# Role Tagging (board-agnostic)
# Roles: concept, worked_example, exercise_prompt, exam_question, solution, marking_scheme, unknown
# Auto-tagging during ingestion; manual override via document.structure_map
# Chunk metadata_json: {auto_role, auto_confidence, role, role_source}
# processing_metadata.role_distribution: {concept: N, ...}
# processing_metadata.role_tagging_metrics: {known_role_ratio, exercise_ratio, concept_ratio}
# ROLE_MIN_CHARS_FOR_QUESTION_BLOCK=200 (anti false-positive for exercise/exam)
# QA: python tools/qa_role_tagging_report.py <document_id>

# File Storage
DOCUMENTS_DIR=uploads/documents
MAX_FILE_SIZE_MB=50

# PDF text extraction (large textbooks)
# Abort if pdfplumber + page loop exceeds this (seconds). Raise as EXTRACTION_TIMEOUT.
EXTRACTION_TIMEOUT_SECONDS=3600
# How often to commit DB progress during extraction (pages per batch).
EXTRACTION_PROGRESS_BATCH_SIZE=10
# Files >= this size (MB) use EXTRACTION_PROGRESS_BATCH_SIZE_LARGE for fresher progress on textbooks.
EXTRACTION_LARGE_FILE_MB=12
EXTRACTION_PROGRESS_BATCH_SIZE_LARGE=3

# SSE: document status stream sends comment heartbeats if no data events (avoids proxy idle disconnect).
SSE_STATUS_HEARTBEAT_SECONDS=15
```

## API Endpoints

### Admin Endpoints (require_role("institution_admin"))

- `POST /api/v1/admin/content-packs` - Create content pack
- `GET /api/v1/admin/content-packs` - List packs
- `GET /api/v1/admin/content-packs/{id}` - Get pack details
- `POST /api/v1/admin/documents` - Upload document (multipart/form-data)
- `GET /api/v1/admin/documents` - List documents
- `GET /api/v1/admin/documents/{id}` - Get document details
- `GET /api/v1/admin/documents/{id}/status/stream` - **SSE stream for real-time status**
- `POST /api/v1/admin/documents/{id}/retry` - Retry failed processing
- `POST /api/v1/admin/documents/{id}/qa/run` - Run QA validation
- `POST /api/v1/admin/documents/{id}/publish` - Publish document

### Worksheet Endpoints (authenticated users)

- `POST /api/v1/worksheets/generate` - Generate worksheet
- `GET /api/v1/worksheets/{id}` - Get cached worksheet

## Setup

### 1. Database Migration

```bash
# Run migration to create tables and enable pgvector
alembic upgrade head
```

The migration will:
- Enable pgvector extension
- Create all content ingestion tables
- Create vector indexes

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

New dependencies:
- `pytesseract`, `ocrmypdf`, `pdf2image`, `Pillow` (OCR)
- `pdfplumber`, `python-docx` (Text extraction)
- `pgvector` (Vector database)
- `tiktoken` (Token counting)
- `numpy` (Vector operations)

### 3. System Dependencies (for OCR)

**Windows:**
- Install Tesseract OCR: https://github.com/UB-Mannheim/tesseract/wiki
- Add to PATH or set `TESSDATA_PREFIX` environment variable

**Linux (Ubuntu/Debian):**
```bash
sudo apt-get install tesseract-ocr
sudo apt-get install poppler-utils  # For pdf2image
```

**macOS:**
```bash
brew install tesseract
brew install poppler
```

### 4. Configure Environment

Add to `.env`:
```bash
OCR_ENGINE=tesseract
EMBEDDING_PROVIDER=openai
VECTOR_STORE=pgvector
OPENAI_API_KEY=your-key-here  # Required for embeddings
```

## Usage

### 1. Create Content Pack

```bash
POST /api/v1/admin/content-packs
{
  "name": "Grade 5 Mathematics",
  "subject": "Mathematics",
  "grade": "Grade 5",
  "curriculum": "Cambridge"
}
```

### 2. Upload Document

```bash
POST /api/v1/admin/documents
Content-Type: multipart/form-data

pack_id: <uuid>
file: <pdf/docx file>
title: "Math Textbook Chapter 1"
chapter_map: [{"id": "ch1", "title": "Fractions", "start_page_pdf": 1, "end_page_pdf": 25}]
```

### 3. Monitor Processing (SSE Stream)

Frontend connects to:
```
GET /api/v1/admin/documents/{id}/status/stream
```

Receives real-time updates:
```json
{
  "document_id": "...",
  "status": "embedding",
  "progress": {
    "step": "embedding",
    "completed": 250,
    "total": 300,
    "percentage": 83
  }
}
```

### 4. Generate Worksheet

```bash
POST /api/v1/worksheets/generate
{
  "pack_id": "...",
  "topic_text": "Fractions",
  "grade": "Grade 5",
  "subject": "Mathematics",
  "num_questions": 10,
  "difficulty_mix": {"easy": 0.3, "medium": 0.5, "hard": 0.2}
}
```

## Future-Proofing

### Adding Mathpix OCR

1. Implement `MathpixOCRProvider` in `providers/ocr_providers.py`
2. Set `OCR_ENGINE=mathpix` in environment
3. Add `MATHPIX_APP_ID` and `MATHPIX_APP_KEY` to environment

### Adding Different Embedding Provider

1. Implement provider in `providers/embedding_providers.py`
2. Set `EMBEDDING_PROVIDER=<provider>` in environment
3. Update `IngestionService._init_providers()` if needed

### Adding Different Vector Store

1. Implement `VectorStore` interface in `providers/vector_stores.py`
2. Set `VECTOR_STORE=<provider>` in environment
3. Update `IngestionService._init_providers()` if needed

## Testing

### Unit Tests

```bash
pytest tests/test_content_ingestion/
```

### End-to-End Test

1. Create content pack
2. Upload test PDF
3. Monitor status stream
4. Wait for PUBLISHED status
5. Generate worksheet
6. Verify worksheet JSON structure

## Troubleshooting

### pgvector Extension Not Found

```sql
-- Run in PostgreSQL
CREATE EXTENSION IF NOT EXISTS vector;
```

### Tesseract Not Found

- Verify Tesseract is installed: `tesseract --version`
- Check PATH or set `TESSDATA_PREFIX` environment variable

### Embedding Generation Fails

- Verify `OPENAI_API_KEY` is set
- Check API quota/limits
- Review logs for specific error messages

### Vector Query Returns No Results

- Ensure document status is `PUBLISHED`
- Verify chunks have embeddings (not NULL)
- Check pack_id filter matches

## Role Tagging QA

1. **Upload math book** – Ingest a math textbook. Check `processing_metadata.role_distribution`:
   - Expect more `exercise_prompt`, `worked_example`, `solution` than a non-math doc
2. **Upload non-math book** – Ingest a prose/history book. Check role_distribution:
   - Expect more `concept`, `unknown`; fewer exercise/solution
3. **Generate worksheet (medium/hard)** – Check retrieval_metadata:
   - `concept_context.preferred_count` and `assessment_context.preferred_count` should be > 0 when content has matching roles
   - `assessment_context` should not be purely backfilled when doc has exercise/exam content
4. **Manual override** – Set `document.structure_map` with page ranges and roles, then call `IngestionService.apply_structure_map_to_chunks(document_id)` to reapply without re-chunking

## Notes

- All providers are swappable via environment variables
- Processing metadata is stored for reproducibility
- QA validation must pass before publishing
- Worksheets are cached by signature hash
- Math content uses LaTeX format for frontend rendering
