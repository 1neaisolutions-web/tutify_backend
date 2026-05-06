# OCR Binary Discovery & Preflight Implementation

**Date:** 2026-01-28  
**Status:** ✅ Implementation Complete - Ready for OCR Binary Installation

---

## Summary

Implemented robust OCR binary discovery and preflight checks for Tesseract OCR and Poppler (pdf2image). The system now:

1. ✅ Discovers OCR binaries via environment variables or PATH
2. ✅ Provides actionable error messages when binaries are missing
3. ✅ Stores preflight results in document metadata
4. ✅ Fails early with clear instructions if OCR is required but binaries are missing

---

## Changes Made

### 1. New Module: `app/domains/content_ingestion/providers/ocr_preflight.py`

**Purpose:** Centralized OCR binary discovery and validation

**Features:**
- Discovers Tesseract via:
  - `TESSERACT_CMD` environment variable (explicit path)
  - PATH search (`shutil.which("tesseract")`)
  - Windows default locations:
    - `C:\Program Files\Tesseract-OCR\tesseract.exe`
    - `C:\Program Files (x86)\Tesseract-OCR\tesseract.exe`
- Discovers Poppler via:
  - `POPPLER_PATH` environment variable (directory containing pdftoppm)
  - PATH search (`shutil.which("pdftoppm")`)
- Validates binaries by running `--version` / `-h` commands
- Provides OS-specific installation instructions in error messages

**Key Methods:**
- `OcrPreflight.check()` - Returns discovery results without raising
- `OcrPreflight.check_and_raise()` - Raises `OcrPreflightError` if binaries missing

### 2. Updated: `app/domains/content_ingestion/providers/ocr_providers.py`

**TesseractOCRProvider Changes:**
- `__init__()` now calls `_setup_tesseract_binary()` for discovery
- `_setup_tesseract_binary()` - Sets `pytesseract.pytesseract.tesseract_cmd` based on discovery
- `_find_poppler_path()` - Discovers Poppler directory
- `validate_config()` - Uses preflight checks for robust validation
- `run_ocr()` - Passes `poppler_path` to `convert_from_path()` when available

### 3. Updated: `app/domains/content_ingestion/services/ingestion_service.py`

**Changes:**
- Imports `OcrPreflight` and `OcrPreflightError`
- Runs preflight checks before OCR when `needs_ocr=True` or `force_ocr=True`
- Stores preflight results in `document.processing_metadata["ocr_preflight"]`
- Raises `OcrPreflightError` with actionable instructions if binaries missing
- Error handling catches `OcrPreflightError` and uses its message as remediation hint

### 4. Updated: `test_e2e_free_mode.py`

**Changes:**
- Imports `OcrPreflight` and `OcrPreflightError`
- Runs preflight check at start and displays results
- Shows actionable errors if binaries are missing

---

## Environment Variables

### `TESSERACT_CMD` (Optional)
Full path to Tesseract executable.

**Example (Windows):**
```powershell
$env:TESSERACT_CMD="C:\Program Files\Tesseract-OCR\tesseract.exe"
```

**Example (Linux):**
```bash
export TESSERACT_CMD="/usr/bin/tesseract"
```

### `POPPLER_PATH` (Optional)
Directory containing Poppler binaries (pdftoppm, pdfinfo).

**Example (Windows):**
```powershell
$env:POPPLER_PATH="C:\poppler\Library\bin"
```

**Example (Linux):**
```bash
export POPPLER_PATH="/usr/bin"
```

**Note:** If not set, the system searches PATH automatically.

---

## Installation Instructions

### Windows

#### Tesseract OCR
1. Download from: https://github.com/UB-Mannheim/tesseract/wiki
2. Install the executable
3. **Option A:** Add to PATH (recommended)
   - Add `C:\Program Files\Tesseract-OCR` to system PATH
4. **Option B:** Set environment variable
   ```powershell
   $env:TESSERACT_CMD="C:\Program Files\Tesseract-OCR\tesseract.exe"
   ```

#### Poppler
1. Download from: https://github.com/oschwartz10612/poppler-windows/releases
2. Extract to a directory (e.g., `C:\poppler`)
3. Set environment variable:
   ```powershell
   $env:POPPLER_PATH="C:\poppler\Library\bin"
   ```

### Linux

```bash
sudo apt-get update
sudo apt-get install tesseract-ocr poppler-utils
```

---

## Testing

### Preflight Check (Standalone)
```python
from app.domains.content_ingestion.providers.ocr_preflight import OcrPreflight

result = OcrPreflight.check()
print(f"Tesseract found: {result['tesseract_found']}")
print(f"Tesseract path: {result['tesseract_path']}")
print(f"Poppler found: {result['poppler_found']}")
print(f"Poppler path: {result['poppler_path']}")
if result['errors']:
    for error in result['errors']:
        print(f"Error: {error}")
```

### End-to-End Test
```powershell
$env:EMBEDDING_PROVIDER='fake'
$env:FAKE_EMBEDDING_DIM='384'
$env:VECTOR_STORE='pgvector'
$env:OCR_PROVIDER='tesseract'
# Optional: Set if binaries not in PATH
# $env:TESSERACT_CMD='C:\Program Files\Tesseract-OCR\tesseract.exe'
# $env:POPPLER_PATH='C:\poppler\Library\bin'
python test_e2e_free_mode.py
```

---

## Current Status

### ✅ Completed
- Binary discovery logic (env vars + PATH + Windows defaults)
- Preflight validation (tests binaries are runnable)
- Actionable error messages (OS-specific installation instructions)
- Preflight results stored in document metadata
- OCR provider uses discovered paths
- Error handling catches preflight errors

### ⏳ Pending User Action
**Install OCR binaries:**
- Tesseract OCR binary
- Poppler (pdftoppm)

**After installation, re-run:**
```powershell
python test_e2e_free_mode.py
```

Expected result:
- Hybrid PDF: ✅ PASSED (already working)
- Scanned PDF: ✅ Should reach PUBLISHED after OCR binaries installed

---

## Error Messages

### If Tesseract Missing (Windows)
```
Tesseract OCR binary not found. Install from: https://github.com/UB-Mannheim/tesseract/wiki
Then either:
  1. Add Tesseract to PATH, OR
  2. Set TESSERACT_CMD environment variable to full path (e.g., C:\Program Files\Tesseract-OCR\tesseract.exe)
```

### If Poppler Missing (Windows)
```
Poppler (pdftoppm) not found. Install Poppler for Windows and set POPPLER_PATH environment variable to Poppler bin directory.
Download from: https://github.com/oschwartz10612/poppler-windows/releases
Example: POPPLER_PATH=C:\poppler\Library\bin
```

### If Tesseract Missing (Linux)
```
Tesseract OCR binary not found. Install with: sudo apt-get install tesseract-ocr
Or set TESSERACT_CMD environment variable to full path.
```

### If Poppler Missing (Linux)
```
Poppler (pdftoppm) not found. Install with: sudo apt-get install poppler-utils
Or set POPPLER_PATH environment variable to Poppler bin directory.
```

---

## Next Steps

1. **Install Tesseract OCR binary** (Windows or Linux)
2. **Install Poppler** (Windows or Linux)
3. **Verify installation:**
   ```powershell
   # Test Tesseract
   tesseract --version
   
   # Test Poppler
   pdftoppm -h
   ```
4. **Re-run end-to-end test:**
   ```powershell
   python test_e2e_free_mode.py
   ```
5. **Expected:** Scanned PDF should process successfully and reach PUBLISHED status

---

## Files Modified

1. ✅ `app/domains/content_ingestion/providers/ocr_preflight.py` (NEW)
2. ✅ `app/domains/content_ingestion/providers/ocr_providers.py` (UPDATED)
3. ✅ `app/domains/content_ingestion/services/ingestion_service.py` (UPDATED)
4. ✅ `test_e2e_free_mode.py` (UPDATED)

---

## Notes

- **No API changes:** All changes are internal to ingestion pipeline
- **Backward compatible:** System works with binaries in PATH (no env vars required)
- **Future-proof:** Supports explicit paths via env vars for Docker/CI environments
- **Actionable errors:** Users get clear instructions on what to install and how
