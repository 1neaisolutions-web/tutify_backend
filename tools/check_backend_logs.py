"""
Check if backend is actually processing OCR or stuck.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

print("=" * 80)
print("BACKEND OCR STATUS CHECK")
print("=" * 80)
print()
print("[INFO] To check backend logs:")
print("  1. Look at the terminal/console where you started the backend")
print("  2. Look for log messages containing:")
print("     - 'Running Tesseract OCR on'")
print("     - 'Using Poppler path'")
print("     - 'OCR completed for page'")
print("     - 'Tesseract OCR failed'")
print()
print("[INFO] If backend logs show:")
print("  [OK] 'Running Tesseract OCR on' -> OCR started")
print("  [OK] 'Using Poppler path' -> Poppler found")
print("  [STUCK] No 'OCR completed for page' -> OCR is stuck in conversion/processing")
print("  [ERROR] 'Tesseract OCR failed' -> Error occurred")
print()
print("[DIAGNOSIS] Based on the code analysis:")
print("  The OCR provider converts ALL 193 pages to images at once:")
print("    images = convert_from_path(pdf_path, dpi=300)")
print()
print("  This can:")
print("  1. Take 2-5 minutes for conversion (if working)")
print("  2. Hang if memory is insufficient (~1.3GB needed)")
print("  3. Then process each page sequentially with Tesseract")
print()
print("[RECOMMENDATION]")
print("  Check backend terminal for:")
print("  - Any error messages")
print("  - CPU usage (should be high if OCR is processing)")
print("  - Memory usage (should increase during conversion)")
print()
print("  If backend shows no activity for 30+ minutes:")
print("  -> OCR is likely stuck/hanging")
print("  -> Consider implementing batch processing")
print("  -> Or reduce DPI for large documents")
print()
print("=" * 80)
