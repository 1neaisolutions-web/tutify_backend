# OCR Zero Characters Fix

## Problem

Frontend uploads were failing with:
```
"total chars 0 < MIN_CHARS_EXTRACT ... pdf_type=digital, OCR attempted=no"
```

**Root Cause**: When text extraction yielded 0 characters, the `MIN_CHARS_EXTRACT` checkpoint ran BEFORE OCR was attempted, causing the pipeline to fail even though OCR could have extracted text from the PDF.

## Solution

Fixed the OCR logic to ensure OCR is attempted when extraction yields 0 characters, regardless of PDF type heuristic.

### Changes Made

#### 1. Fixed `_needs_ocr()` Logic (`app/domains/content_ingestion/services/ingestion_service.py`)

**Before:**
- Only checked average chars per page against threshold
- Did not explicitly handle `total_chars == 0` case

**After:**
- **Priority 1**: If `total_chars == 0` → return `True` (OCR required)
- **Priority 2**: If `avg_chars < SCANNED_THRESHOLD_CHARS` → return `True` (OCR required)
- PDF type heuristic cannot block OCR when extracted text is empty

```python
def _needs_ocr(self, pages: List, source_type: str) -> bool:
    """Determine if OCR is needed based on text density."""
    if source_type != "pdf":
        return False
    
    if not pages:
        return True
    
    # Check total chars first - if 0, OCR is required regardless of pdf_type heuristic
    total_chars = sum(p.char_count for p in pages)
    if total_chars == 0:
        return True
    
    # Check average chars per page - if below threshold, needs OCR
    avg_chars = total_chars / len(pages) if pages else 0
    if avg_chars < settings.SCANNED_THRESHOLD_CHARS:
        return True
    
    return False
```

#### 2. Moved `MIN_CHARS_EXTRACT` Checkpoint to Run AFTER OCR

**Before:**
- Checkpoint ran immediately after text extraction
- Failed if `total_chars < MIN_CHARS_EXTRACT` even if OCR could extract text

**After:**
- Checkpoint runs AFTER OCR attempt
- OCR has opportunity to extract text before checkpoint validation
- Error message includes `OCR attempted=yes/no` for debugging

```python
# MIN_CHARS_EXTRACT checkpoint: Run AFTER OCR attempt
# This ensures OCR has a chance to extract text before we fail
total_chars = sum(p.char_count for p in pages)
min_chars = getattr(settings, "MIN_CHARS_EXTRACT", 1)
if total_chars < min_chars:
    meta = dict(document.processing_metadata or {})
    pdf_type = meta.get("pdf_type", "unknown")
    raise ValueError(
        f"Extraction checkpoint failed: total chars {total_chars} < MIN_CHARS_EXTRACT ({min_chars}). "
        f"extractor used, pdf_type={pdf_type}, OCR attempted={'yes' if ocr_attempted else 'no'}"
    )
```

#### 3. Enhanced Status Tracking

- Status now shows `OCR_RUNNING` when OCR is triggered
- `ocr_attempted` flag tracks whether OCR was attempted
- Used in error messages and logging

#### 4. Added QA Logging

**When `total_chars == 0` triggers OCR:**
- Logs `ocr_triggered_zero_chars` event with:
  - `total_chars`: 0
  - `needs_ocr`: boolean
  - `force_ocr`: boolean
  - `pdf_type`: digital/scanned/unknown
  - `preflight_result`: OCR binary availability

**After OCR completes:**
- Logs `ocr_complete` event with:
  - `total_chars_before_ocr`: chars before OCR
  - `total_chars_after_ocr`: chars after OCR
  - `preflight_result`: OCR preflight check results
  - `ocr_attempted`: True

#### 5. Verified `force_ocr` Support

Both upload routes already support `force_ocr`:
- `POST /api/v1/admin/documents` - Form field: `force_ocr: bool = Form(False)`
- `POST /api/v1/admin/documents/upload-stream` - Form field: `force_ocr: bool = Form(False)`

When `force_ocr=True`:
- Stored in `document.processing_metadata = {"force_ocr": True}`
- OCR runs regardless of text extraction results
- Useful for forcing OCR on digital PDFs

## Processing Flow (After Fix)

1. **Text Extraction**
   - Extract text from PDF using pdfplumber
   - Store initial page texts
   - Calculate `total_chars`

2. **OCR Decision**
   - Check `_needs_ocr()`:
     - If `total_chars == 0` → OCR required
     - If `avg_chars < threshold` → OCR required
     - If `force_ocr=True` → OCR required
   - Run OCR preflight checks
   - Store preflight results in metadata

3. **OCR Execution** (if needed)
   - Update status to `OCR_RUNNING`
   - Run OCR using Tesseract
   - Update page texts with OCR results
   - Recalculate `total_chars` after OCR

4. **MIN_CHARS_EXTRACT Checkpoint** (AFTER OCR)
   - Check if `total_chars >= MIN_CHARS_EXTRACT`
   - If not, fail with error including `OCR attempted=yes/no`

5. **Continue Pipeline**
   - Normalize text
   - Chunk text
   - Generate embeddings
   - Index vectors
   - QA validation
   - Publish

## Testing

To verify the fix:

1. **Upload a PDF with 0 extracted characters** (e.g., fully scanned PDF)
2. **Expected behavior:**
   - Text extraction yields 0 chars
   - OCR is triggered automatically
   - Status shows `OCR_RUNNING`
   - OCR extracts text from scanned pages
   - `page_texts` become non-empty
   - Chunks are created
   - Embeddings are persisted
   - Status reaches `PUBLISHED`

3. **Check logs for:**
   - `ocr_triggered_zero_chars` event when chars=0
   - `ocr_complete` event with before/after char counts
   - Preflight results in metadata

4. **Verify database:**
   ```sql
   SELECT 
       COUNT(*) AS pages,
       SUM(CASE WHEN char_count > 0 THEN 1 ELSE 0 END) AS non_empty_pages
   FROM page_texts
   WHERE document_id = '<document_id>';
   ```
   - Should show non-empty pages after OCR

## Error Messages

**Before Fix:**
```
Extraction checkpoint failed: total chars 0 < MIN_CHARS_EXTRACT (1). 
extractor used, pdf_type=digital, OCR attempted=no
```

**After Fix:**
- If OCR succeeds: No error, pipeline continues
- If OCR fails: Error includes `OCR attempted=yes`:
```
Extraction checkpoint failed: total chars 0 < MIN_CHARS_EXTRACT (1). 
extractor used, pdf_type=digital, OCR attempted=yes
```

## Files Modified

- `app/domains/content_ingestion/services/ingestion_service.py`
  - `_needs_ocr()`: Added `total_chars == 0` check
  - Moved `MIN_CHARS_EXTRACT` checkpoint after OCR
  - Added QA logging for OCR attempts
  - Enhanced error messages with OCR attempt status

## No API Changes

- All changes are internal to `IngestionService`
- No changes to request/response schemas
- No changes to endpoint signatures
- `force_ocr` parameter already supported

## Summary

✅ OCR now triggers when `total_chars == 0`  
✅ `MIN_CHARS_EXTRACT` checkpoint runs AFTER OCR  
✅ Status shows `OCR_RUNNING` when OCR is triggered  
✅ QA logging includes OCR attempt evidence  
✅ `force_ocr` already supported in upload routes  
✅ No API changes required
