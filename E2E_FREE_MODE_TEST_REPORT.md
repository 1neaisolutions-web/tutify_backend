# End-to-End FREE MODE Ingestion Test Report

**Date:** 2026-01-28  
**Environment:** FREE MODE (fake embeddings, tesseract OCR)  
**Test Files:**
1. `math_ocr_test_pack.pdf` (Hybrid PDF - selectable text + equation images)
2. `math_ocr_test_pack_scanned.pdf` (Fully scanned PDF - image-only)

---

## Test Configuration

```
EMBEDDING_PROVIDER=fake
FAKE_EMBEDDING_DIM=384
VECTOR_STORE=pgvector
OCR_PROVIDER=tesseract
```

---

## PHASE 1: Hybrid PDF Test (`math_ocr_test_pack.pdf`)

### ✅ RESULT: PASSED

**Document ID:** `0fa9ec28-5fe6-4af5-88c2-57ff6e00876a`

### Processing Status
- **Final Status:** `PUBLISHED`
- **OCR Triggered:** No (digital PDF, text extraction sufficient)
- **Processing Time:** ~12 seconds

### Database Evidence

#### Page Texts
```sql
SELECT COUNT(*) AS pages,
       SUM(CASE WHEN char_count > 0 THEN 1 ELSE 0 END) AS non_empty_pages
FROM page_texts
WHERE document_id = '0fa9ec28-5fe6-4af5-88c2-57ff6e00876a';
```
**Results:**
- Total pages: **4**
- Non-empty pages: **4** (100%)

#### Chunks
```sql
SELECT COUNT(*) AS chunks
FROM chunks
WHERE document_id = '0fa9ec28-5fe6-4af5-88c2-57ff6e00876a';
```
**Results:**
- Total chunks: **2**

#### Embedding Persistence (NEW column: `embedding_v`)
```sql
SELECT COUNT(*) AS chunks_with_vectors
FROM chunks
WHERE document_id = '0fa9ec28-5fe6-4af5-88c2-57ff6e00876a'
  AND embedding_v IS NOT NULL
  AND embedding_model = 'fake';
```
**Results:**
- Chunks with `embedding_v`: **2** (100% of chunks)

#### Model/Dimension/Provider Evidence
```sql
SELECT embedding_model, embedding_dim, embedding_provider, COUNT(*)
FROM chunks
WHERE document_id = '0fa9ec28-5fe6-4af5-88c2-57ff6e00876a'
GROUP BY embedding_model, embedding_dim, embedding_provider;
```
**Results:**
- `embedding_model`: `fake`
- `embedding_dim`: `384`
- `embedding_provider`: `fake`
- Count: **2**

#### Math Layer Evidence
```sql
-- Math blocks count
SELECT COUNT(*) AS math_blocks 
FROM math_blocks 
WHERE document_id = '0fa9ec28-5fe6-4af5-88c2-57ff6e00876a';

-- Chunks with math markers
SELECT COUNT(*) AS chunks_with_math
FROM chunks
WHERE document_id = '0fa9ec28-5fe6-4af5-88c2-57ff6e00876a' 
  AND text LIKE '%[[MATH]]%';
```
**Results:**
- Math blocks: **7**
- Chunks with math markers: **2**

### Retrieval Test Evidence

**Query:** "solve linear equation"

**Top 5 Results:**
```sql
SELECT 
    chunk_id, 
    page_start_pdf, 
    page_end_pdf,
    (embedding_v <=> '[query_vector]'::vector) AS distance,
    LEFT(text, 120) AS snippet
FROM chunks
WHERE document_id = '0fa9ec28-5fe6-4af5-88c2-57ff6e00876a'
  AND embedding_v IS NOT NULL
  AND embedding_model = 'fake'
ORDER BY embedding_v <=> '[query_vector]'::vector
LIMIT 5;
```

**Results:** Retrieval returned results (exact distances and snippets available in test log)

---

## PHASE 2: Scanned PDF Test (`math_ocr_test_pack_scanned.pdf`)

### ❌ RESULT: FAILED (System Dependency Missing)

**Document ID:** `45dc1512-de2f-42cc-a5e8-bc5b5165dac6`

### Processing Status
- **Final Status:** `FAILED`
- **Error Code:** `OCR_ERROR`
- **Error Message:** `OCR required for document ... but OCR provider is not available`
- **OCR Triggered:** Yes (force_ocr=True), but Tesseract binary not found

### Root Cause
**Tesseract OCR binary is not installed on the system.**

The Python package `pytesseract` is installed, but the actual Tesseract OCR binary executable is missing from PATH.

### Fix Applied
Fixed checkpoint logic in `ingestion_service.py` to respect `force_ocr=True` flag:
- Previously: Checkpoint failed before OCR could run
- Now: Checkpoint skipped when `force_ocr=True`, allowing OCR to attempt

### Required Action
**Install Tesseract OCR binary:**

**Windows:**
1. Download from: https://github.com/UB-Mannheim/tesseract/wiki
2. Install the executable
3. Add Tesseract to PATH (or set `TESSDATA_PREFIX` environment variable)

**Linux:**
```bash
sudo apt-get install tesseract-ocr poppler-utils
```

**Verification:**
```bash
tesseract --version
```

After installation, re-run the test for the scanned PDF.

---

## Summary

### ✅ Hybrid PDF (Digital)
- **Status:** PUBLISHED
- **Pages:** 4 (all non-empty)
- **Chunks:** 2
- **Embeddings:** 2 chunks with `embedding_v` (384-dim, fake provider)
- **Math:** 7 math blocks detected, 2 chunks with math markers
- **Retrieval:** Working (similarity search returns results)

### ❌ Scanned PDF (Image-only)
- **Status:** FAILED
- **Reason:** Tesseract OCR binary not installed
- **Fix Applied:** Checkpoint logic now respects `force_ocr=True`
- **Next Step:** Install Tesseract OCR binary and re-run test

---

## Code Changes Made

1. **Fixed `force_ocr` checkpoint logic** (`app/domains/content_ingestion/services/ingestion_service.py`):
   - Modified checkpoint to skip when `force_ocr=True`
   - Allows OCR to run even if initial text extraction returns 0 characters

---

## Test Script

Created `test_e2e_free_mode.py`:
- Runs end-to-end ingestion for both PDFs
- Queries database for evidence
- Tests vector retrieval
- Provides comprehensive evidence report

**Usage:**
```powershell
$env:EMBEDDING_PROVIDER='fake'
$env:FAKE_EMBEDDING_DIM='384'
$env:VECTOR_STORE='pgvector'
$env:OCR_PROVIDER='tesseract'
python test_e2e_free_mode.py
```

---

## Evidence Files

- `test_output_fixed.log` - Full test execution log with SQL queries
- `test_e2e_free_mode.py` - Test script

---

## Next Steps

1. ✅ Hybrid PDF test: **COMPLETE** - All checks pass
2. ⏳ Scanned PDF test: **PENDING** - Install Tesseract OCR binary
3. After Tesseract installation, re-run test to verify:
   - OCR extracts text from scanned PDF
   - Page texts become non-empty after OCR
   - Chunks and embeddings are created
   - Retrieval works with OCR-extracted text
