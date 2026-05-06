## Free Mode Quickstart (No API keys / No network)

### 1) Install Python deps

```bash
pip install -r requirements.txt
```

### 2) Install system deps (OCR)

**Windows**
- Tesseract: https://github.com/UB-Mannheim/tesseract/wiki
- Poppler (for `pdf2image`): install Poppler for Windows and ensure `pdftoppm` is on PATH

**Ubuntu/Debian**
```bash
sudo apt-get update
sudo apt-get install -y tesseract-ocr poppler-utils
```

### 3) Set env vars (free mode)

```bash
set OCR_ENGINE=tesseract
set EMBEDDING_PROVIDER=fake
set FAKE_EMBEDDING_DIM=384
set VECTOR_STORE=pgvector
```

Optional (local AI embeddings, still free):
```bash
set EMBEDDING_PROVIDER=local
set LOCAL_EMBEDDING_MODEL_NAME=sentence-transformers/all-MiniLM-L6-v2
```

### 4) Run backend and ingest a sample PDF

Upload using existing endpoints (no API changes):
- `POST /api/v1/admin/documents`
- `POST /api/v1/admin/documents/upload-stream`

### 5) Verify success (DB checks)

**Embeddings persisted (non-null)**
```sql
SELECT COUNT(*) AS embedded_chunks
FROM chunks
WHERE document_id = '<DOCUMENT_UUID>'
  AND embedding_v IS NOT NULL
  AND embedding_model IN ('fake','local');
```

**Embedding dims recorded**
```sql
SELECT embedding_model, embedding_dim, COUNT(*)
FROM chunks
WHERE document_id = '<DOCUMENT_UUID>'
GROUP BY 1,2;
```

**Math blocks (if math detected)**
```sql
SELECT COUNT(*) AS math_blocks
FROM math_blocks
WHERE document_id = '<DOCUMENT_UUID>';
```

### Expected status lifecycle

`uploaded → text_extracting → ocr_running (conditional) → normalizing → chunking → embedding → indexing → qa_validation → published`

