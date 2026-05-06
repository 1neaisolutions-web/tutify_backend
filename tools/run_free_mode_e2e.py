"""
Pure-Python runner for FREE MODE end-to-end tests.
Avoids PowerShell Env: provider issues by setting env vars directly in Python.

Usage:
    python tools/run_free_mode_e2e.py

This script sets environment variables in Python (not PowerShell) and runs
the end-to-end test, avoiding the "Get-ChildItem Env:" crash.
"""
import os
import sys
from pathlib import Path

# Set FREE MODE environment variables FIRST (before any imports)
# This ensures they're available when test_e2e_free_mode.py loads
os.environ["EMBEDDING_PROVIDER"] = "fake"
os.environ["FAKE_EMBEDDING_DIM"] = "384"
os.environ["VECTOR_STORE"] = "pgvector"
os.environ["OCR_PROVIDER"] = "tesseract"

# Set OCR binary paths (use provided paths, can be overridden by system env)
# These paths are set here to avoid PowerShell Env: enumeration issues
tesseract_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# Check for Poppler in cleaner path first, then fall back to Downloads
poppler_paths = [
    r"C:\poppler\poppler-25.12.0\Library\bin",  # Clean path (preferred)
    r"C:\Users\rttsg\Downloads\Release-25.12.0-0 (1)\poppler-25.12.0\Library\bin",  # Downloads fallback
]
poppler_path = None
for path in poppler_paths:
    if os.path.exists(path):
        poppler_path = path
        break

if "TESSERACT_CMD" not in os.environ:
    if os.path.exists(tesseract_path):
        os.environ["TESSERACT_CMD"] = tesseract_path
    else:
        print(f"[WARN] Tesseract not found at default path: {tesseract_path}")

if "POPPLER_PATH" not in os.environ:
    if poppler_path:
        os.environ["POPPLER_PATH"] = poppler_path
        # Prepend Poppler bin to PATH for DLL resolution (Windows)
        if sys.platform == "win32":
            current_path = os.environ.get("PATH", "")
            if poppler_path not in current_path:
                os.environ["PATH"] = f"{poppler_path};{current_path}"
                print(f"[INFO] Prepend Poppler to PATH: {poppler_path}")
    else:
        print(f"[WARN] Poppler not found at any default path. Checked: {poppler_paths}")

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Print configuration (only what we care about, no full env enumeration)
print("=" * 80)
print("FREE MODE E2E TEST RUNNER")
print("=" * 80)
print(f"EMBEDDING_PROVIDER: {os.environ.get('EMBEDDING_PROVIDER', 'NOT SET')}")
print(f"FAKE_EMBEDDING_DIM: {os.environ.get('FAKE_EMBEDDING_DIM', 'NOT SET')}")
print(f"VECTOR_STORE: {os.environ.get('VECTOR_STORE', 'NOT SET')}")
print(f"OCR_PROVIDER: {os.environ.get('OCR_PROVIDER', 'NOT SET')}")
print(f"TESSERACT_CMD: {os.environ.get('TESSERACT_CMD', 'NOT SET')}")
print(f"POPPLER_PATH: {os.environ.get('POPPLER_PATH', 'NOT SET')}")
print("=" * 80)

# Run OCR preflight check
print("\n[PHASE 0] OCR Preflight Check")
print("-" * 80)
try:
    from app.domains.content_ingestion.providers.ocr_preflight import OcrPreflight
    preflight_result = OcrPreflight.check()
    
    print(f"Tesseract found: {preflight_result['tesseract_found']}")
    if preflight_result['tesseract_path']:
        print(f"Tesseract path: {preflight_result['tesseract_path']}")
        if preflight_result.get('tesseract_version'):
            print(f"Tesseract version: {preflight_result['tesseract_version']}")
    
    print(f"Poppler found: {preflight_result['poppler_found']}")
    if preflight_result['poppler_path']:
        print(f"Poppler path: {preflight_result['poppler_path']}")
    
    if preflight_result['errors']:
        print("\n[WARN] OCR preflight errors:")
        for error in preflight_result['errors']:
            print(f"  {error}")
        print("\n[WARN] Scanned PDF test may fail. Continuing anyway...")
    else:
        print("\n[PASS] OCR preflight check passed")
except Exception as e:
    print(f"[ERROR] Preflight check failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Run the actual test script
print("\n" + "=" * 80)
print("[PHASE 1-5] Running end-to-end test")
print("=" * 80)

# Import and run the test script's main function
try:
    # Change to repo root directory
    os.chdir(ROOT)
    
    # Import the test script module directly
    sys.path.insert(0, str(ROOT))
    from test_e2e_free_mode import main as test_main
    
    # Run the async main function
    import asyncio
    asyncio.run(test_main())
        
except Exception as e:
    print(f"\n[ERROR] Test execution failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 80)
print("TEST RUNNER COMPLETE")
print("=" * 80)
