"""
Check if backend can discover Poppler paths.
Run this to verify Poppler discovery before starting the backend.
"""
import os
import sys
import io
import platform
from pathlib import Path

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

print("=" * 80)
print("BACKEND POPPLER DISCOVERY CHECK")
print("=" * 80)
print()

# Check current environment
print("[1] Current Environment:")
print(f"   POPPLER_PATH: {os.getenv('POPPLER_PATH', 'NOT SET')}")
print(f"   TESSERACT_CMD: {os.getenv('TESSERACT_CMD', 'NOT SET')}")
print()

# Simulate startup discovery
print("[2] Simulating Backend Startup Discovery:")
if platform.system() == "Windows":
    user_home = os.path.expanduser("~")
    poppler_paths = [
        r"C:\poppler\poppler-25.12.0\Library\bin",
        r"C:\poppler\Library\bin",
        os.path.join(user_home, r"Downloads\Release-25.12.0-0 (1)\poppler-25.12.0\Library\bin"),
        r"C:\Program Files\poppler\bin",
    ]
    
    print("   Checking paths:")
    found = False
    for path_str in poppler_paths:
        poppler_dir = Path(path_str)
        exists = poppler_dir.is_dir()
        pdftoppm = poppler_dir / "pdftoppm.exe"
        pdftoppm_exists = pdftoppm.exists()
        
        status = "[FOUND]" if (exists and pdftoppm_exists) else "[NOT FOUND]"
        print(f"   {status} {path_str}")
        if exists:
            print(f"      Directory exists: Yes")
            print(f"      pdftoppm.exe exists: {pdftoppm_exists}")
            if pdftoppm_exists:
                found = True
                print(f"   [PASS] Poppler would be auto-discovered at: {poppler_dir}")
                break
        else:
            print(f"      Directory exists: No")
    
    if not found:
        print()
        print("   [FAIL] Poppler not found in any checked path")
        print()
        print("   [SOLUTION]")
        print("   Option 1: Set POPPLER_PATH environment variable:")
        print("      $env:POPPLER_PATH=\"C:\\path\\to\\poppler\\bin\"")
        print()
        print("   Option 2: Move Poppler to one of these locations:")
        for path_str in poppler_paths[:2]:  # Show first 2 preferred paths
            print(f"      {path_str}")
else:
    print("   Non-Windows system - checking PATH...")
    import shutil
    pdftoppm_path = shutil.which("pdftoppm")
    if pdftoppm_path:
        print(f"   [PASS] Found pdftoppm in PATH: {pdftoppm_path}")
    else:
        print("   [FAIL] pdftoppm not found in PATH")

print()
print("[3] Testing Preflight Check:")
try:
    from app.domains.content_ingestion.providers.ocr_preflight import OcrPreflight
    result = OcrPreflight.check()
    
    print(f"   Tesseract found: {result['tesseract_found']}")
    if result['tesseract_path']:
        print(f"   Tesseract path: {result['tesseract_path']}")
    
    print(f"   Poppler found: {result['poppler_found']}")
    if result['poppler_path']:
        print(f"   Poppler path: {result['poppler_path']}")
    
    if result['errors']:
        print()
        print("   Errors:")
        for error in result['errors']:
            print(f"      - {error}")
    
    if result['poppler_found'] and result['tesseract_found']:
        print()
        print("   [PASS] All OCR binaries found - backend should work!")
    else:
        print()
        print("   [WARN] Some OCR binaries missing - check errors above")
except Exception as e:
    print(f"   [FAIL] Error running preflight check: {e}")
    import traceback
    traceback.print_exc()

print()
print("=" * 80)
