"""
Test Poppler DLL dependencies and provide actionable fixes.
"""
import os
import sys
import subprocess
import platform
from pathlib import Path

def test_pdfinfo(poppler_path: str) -> tuple[bool, str]:
    """Test pdfinfo.exe with full error capture."""
    pdfinfo_exe = Path(poppler_path) / "pdfinfo.exe"
    if not pdfinfo_exe.exists():
        return False, f"pdfinfo.exe not found at {pdfinfo_exe}"
    
    env = os.environ.copy()
    # Prepend Poppler to PATH
    current_path = env.get("PATH", "")
    if poppler_path not in current_path:
        env["PATH"] = f"{poppler_path};{current_path}"
    
    try:
        result = subprocess.run(
            [str(pdfinfo_exe), "-v"],
            capture_output=True,
            text=True,
            timeout=5,
            env=env,
        )
        
        if result.returncode == 0:
            return True, "pdfinfo works correctly"
        elif result.returncode == 1:
            # Version output often returns 1
            return True, "pdfinfo works (exit code 1 is normal for -v)"
        elif result.returncode == 3221225781:  # 0xC0000135
            return False, (
                "ERROR: Missing runtime dependency (exit code 0xC0000135).\n"
                "SOLUTION: Install Microsoft Visual C++ Redistributable 2015-2022 (x64)\n"
                "Download: https://aka.ms/vs/17/release/vc_redist.x64.exe\n"
                "After installation, restart terminal and retest."
            )
        else:
            stderr = result.stderr[:500] if result.stderr else "No error message"
            return False, f"Exit code {result.returncode}: {stderr}"
    except Exception as e:
        return False, f"Exception: {str(e)}"

def main():
    """Test Poppler DLL dependencies."""
    print("=" * 80)
    print("POPPLER DLL DEPENDENCY TEST")
    print("=" * 80)
    
    # Check for Poppler in cleaner path first
    poppler_paths = [
        r"C:\poppler\poppler-25.12.0\Library\bin",
        r"C:\Users\rttsg\Downloads\Release-25.12.0-0 (1)\poppler-25.12.0\Library\bin",
    ]
    
    # Also check environment variable
    if "POPPLER_PATH" in os.environ:
        poppler_paths.insert(0, os.environ["POPPLER_PATH"])
    
    poppler_path = None
    for path in poppler_paths:
        if os.path.exists(path):
            pdfinfo_exe = Path(path) / "pdfinfo.exe"
            if pdfinfo_exe.exists():
                poppler_path = path
                print(f"[INFO] Found Poppler at: {poppler_path}")
                break
    
    if not poppler_path:
        print("[ERROR] Poppler not found. Checked paths:")
        for path in poppler_paths:
            print(f"  - {path}")
        print("\n[INSTRUCTIONS]")
        print("1. Download Poppler for Windows from:")
        print("   https://github.com/oschwartz10612/poppler-windows/releases")
        print("2. Extract to: C:\\poppler\\poppler-25.12.0\\Library\\bin")
        print("3. Set POPPLER_PATH environment variable to that path")
        sys.exit(1)
    
    print(f"\n[TEST] Testing pdfinfo.exe at: {poppler_path}")
    success, message = test_pdfinfo(poppler_path)
    
    if success:
        print(f"[PASS] {message}")
        print("\n[INFO] Poppler is ready for OCR operations.")
        sys.exit(0)
    else:
        print(f"[FAIL] {message}")
        print("\n[INSTRUCTIONS]")
        print("1. Install Microsoft Visual C++ Redistributable 2015-2022 (x64)")
        print("   Download: https://aka.ms/vs/17/release/vc_redist.x64.exe")
        print("2. Run installer (may require admin privileges)")
        print("3. Restart terminal/IDE")
        print("4. Rerun this test: python tools/test_poppler_dlls.py")
        sys.exit(1)

if __name__ == "__main__":
    main()
