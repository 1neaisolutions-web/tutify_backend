"""
OCR preflight checks for binary discovery and validation.
Provides actionable errors when OCR binaries are missing.
"""
import os
import shutil
import subprocess
import platform
from typing import Dict, Optional, Tuple
from pathlib import Path

from app.core.logging import get_logger
from app.core.config import settings

logger = get_logger(__name__)


class OcrPreflightError(Exception):
    """Raised when OCR preflight checks fail."""
    pass


class OcrPreflight:
    """Preflight checks for OCR binaries (Tesseract and Poppler)."""
    
    @staticmethod
    def _find_tesseract() -> Optional[str]:
        """Find Tesseract executable path."""
        # Check explicit env var first
        tesseract_cmd = os.getenv("TESSERACT_CMD")
        if tesseract_cmd and os.path.exists(tesseract_cmd):
            return tesseract_cmd
        
        # Check PATH
        tesseract_path = shutil.which("tesseract")
        if tesseract_path:
            return tesseract_path
        
        # Windows-specific default locations
        if platform.system() == "Windows":
            default_paths = [
                r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            ]
            for path in default_paths:
                if os.path.exists(path):
                    return path
        
        return None
    
    @staticmethod
    def _find_poppler() -> Optional[str]:
        """Find Poppler directory (contains pdftoppm/pdfinfo)."""
        # Check explicit env var first
        poppler_path = os.getenv("POPPLER_PATH")
        if poppler_path:
            poppler_dir = Path(poppler_path)
            if poppler_dir.is_dir():
                # Check if pdftoppm exists in this directory
                pdftoppm = poppler_dir / ("pdftoppm.exe" if platform.system() == "Windows" else "pdftoppm")
                if pdftoppm.exists():
                    return str(poppler_dir)
        
        # Check PATH for pdftoppm
        pdftoppm_path = shutil.which("pdftoppm")
        if pdftoppm_path:
            # Return parent directory
            return str(Path(pdftoppm_path).parent)
        
        # Windows-specific default locations (auto-discovery)
        if platform.system() == "Windows":
            # Try to get user home directory dynamically
            user_home = os.path.expanduser("~")
            default_paths = [
                r"C:\poppler\poppler-25.12.0\Library\bin",  # Clean path (preferred)
                r"C:\poppler\Library\bin",  # Alternative clean path
                os.path.join(user_home, r"Downloads\Release-25.12.0-0 (1)\poppler-25.12.0\Library\bin"),  # Downloads fallback
                r"C:\Program Files\poppler\bin",  # Program Files location
            ]
            for path_str in default_paths:
                poppler_dir = Path(path_str)
                if poppler_dir.is_dir():
                    pdftoppm = poppler_dir / "pdftoppm.exe"
                    if pdftoppm.exists():
                        logger.info(f"Auto-discovered Poppler at: {path_str}")
                        # Set POPPLER_PATH in environment for this process
                        if not os.getenv("POPPLER_PATH"):
                            os.environ["POPPLER_PATH"] = str(poppler_dir)
                            # Also prepend to PATH for DLL resolution
                            current_path = os.environ.get("PATH", "")
                            if str(poppler_dir) not in current_path:
                                os.environ["PATH"] = f"{poppler_dir};{current_path}"
                        return str(poppler_dir)
        
        return None
    
    @staticmethod
    def _test_tesseract(tesseract_path: str) -> Tuple[bool, Optional[str]]:
        """Test if Tesseract executable works."""
        try:
            result = subprocess.run(
                [tesseract_path, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                version_line = result.stdout.split("\n")[0] if result.stdout else "unknown"
                return True, version_line
            return False, result.stderr
        except FileNotFoundError:
            return False, "Executable not found"
        except subprocess.TimeoutExpired:
            return False, "Timeout"
        except Exception as e:
            return False, str(e)
    
    @staticmethod
    def _test_poppler(poppler_path: Optional[str]) -> Tuple[bool, Optional[str]]:
        """Test if Poppler tools work, specifically pdfinfo (used by pdf2image)."""
        try:
            env = os.environ.copy()
            if poppler_path:
                # Test pdfinfo (used by pdf2image) first, then pdftoppm
                pdfinfo_exe = Path(poppler_path) / ("pdfinfo.exe" if platform.system() == "Windows" else "pdfinfo")
                if not pdfinfo_exe.exists():
                    return False, f"pdfinfo.exe not found at {pdfinfo_exe}"
                cmd = [str(pdfinfo_exe), "-v"]
                # Prepend Poppler bin directory to PATH for DLL resolution on Windows
                if platform.system() == "Windows":
                    current_path = env.get("PATH", "")
                    if poppler_path not in current_path:
                        # Prepend (not append) for better DLL resolution
                        env["PATH"] = f"{poppler_path};{current_path}"
            else:
                cmd = ["pdfinfo", "-v"]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=5,
                env=env,  # Pass modified env with PATH
            )
            # Exit code 3221225781 (0xC0000135) = STATUS_DLL_NOT_FOUND - missing runtime dependency
            # This typically means Microsoft VC++ Redistributable is missing
            if result.returncode == 0:
                return True, "Poppler tools available"
            elif result.returncode == 1:
                # Help/version output often returns 1
                return True, "Poppler tools available"
            elif result.returncode == 3221225781:  # 0xC0000135
                error_msg = (
                    "Poppler binary found but missing runtime dependency (exit code 0xC0000135). "
                    "Install Microsoft Visual C++ Redistributable 2015-2022 (x64) from: "
                    "https://aka.ms/vs/17/release/vc_redist.x64.exe"
                )
                return False, error_msg
            elif "DLL" in (result.stderr or "").upper():
                error_msg = (
                    f"Poppler DLL dependency issue (exit {result.returncode}). "
                    "Install Microsoft Visual C++ Redistributable 2015-2022 (x64) from: "
                    "https://aka.ms/vs/17/release/vc_redist.x64.exe"
                )
                return False, error_msg
            else:
                # Other error
                return False, f"Exit code {result.returncode}: {result.stderr[:200] if result.stderr else 'No error message'}"
        except FileNotFoundError:
            return False, "pdfinfo not found"
        except subprocess.TimeoutExpired:
            return False, "Timeout"
        except Exception as e:
            return False, str(e)
    
    @staticmethod
    def check() -> Dict[str, any]:
        """
        Run preflight checks for OCR binaries.
        
        Returns:
            Dict with:
            - tesseract_found: bool
            - tesseract_path: str | None
            - tesseract_version: str | None
            - poppler_found: bool
            - poppler_path: str | None
            - errors: List[str] (actionable error messages)
        
        Raises:
            OcrPreflightError: If critical binaries are missing with actionable instructions
        """
        errors = []
        result = {
            "tesseract_found": False,
            "tesseract_path": None,
            "tesseract_version": None,
            "poppler_found": False,
            "poppler_path": None,
            "errors": [],
        }
        
        # Check Tesseract
        tesseract_path = OcrPreflight._find_tesseract()
        if tesseract_path:
            works, version_or_error = OcrPreflight._test_tesseract(tesseract_path)
            if works:
                result["tesseract_found"] = True
                result["tesseract_path"] = tesseract_path
                result["tesseract_version"] = version_or_error
                logger.info(f"Tesseract found: {tesseract_path} ({version_or_error})")
            else:
                errors.append(f"Tesseract found at {tesseract_path} but not working: {version_or_error}")
        else:
            # Generate OS-specific error message
            if platform.system() == "Windows":
                error_msg = (
                    "Tesseract OCR binary not found. "
                    "Install from: https://github.com/UB-Mannheim/tesseract/wiki\n"
                    "Then either:\n"
                    "  1. Add Tesseract to PATH, OR\n"
                    "  2. Set TESSERACT_CMD environment variable to full path (e.g., C:\\Program Files\\Tesseract-OCR\\tesseract.exe)"
                )
            else:
                error_msg = (
                    "Tesseract OCR binary not found. "
                    "Install with: sudo apt-get install tesseract-ocr\n"
                    "Or set TESSERACT_CMD environment variable to full path."
                )
            errors.append(error_msg)
        
        # Check Poppler
        poppler_path = OcrPreflight._find_poppler()
        if poppler_path:
            # Check if executable exists
            pdftoppm = Path(poppler_path) / ("pdftoppm.exe" if platform.system() == "Windows" else "pdftoppm")
            if pdftoppm.exists():
                works, msg = OcrPreflight._test_poppler(poppler_path)
                if works:
                    result["poppler_found"] = True
                    result["poppler_path"] = poppler_path
                    logger.info(f"Poppler found: {poppler_path}")
                else:
                    # Check if it's a DLL dependency error (0xC0000135)
                    if "0xC0000135" in msg or "VC++ Redistributable" in msg:
                        # This is a critical runtime dependency issue - fail preflight
                        errors.append(f"Poppler found at {poppler_path} but {msg}")
                        result["poppler_found"] = False
                        result["poppler_path"] = poppler_path
                    else:
                        # Other issues - mark as found but warn
                        result["poppler_found"] = True
                        result["poppler_path"] = poppler_path
                        logger.warning(f"Poppler found at {poppler_path} but test had issues: {msg}. Will attempt OCR anyway.")
            else:
                errors.append(f"Poppler directory found but pdftoppm.exe not found at {pdftoppm}")
        else:
            # Generate OS-specific error message
            if platform.system() == "Windows":
                error_msg = (
                    "Poppler (pdfinfo/pdftoppm) not found or DLL dependencies missing. "
                    "Install Poppler for Windows and set POPPLER_PATH environment variable.\n"
                    "Download from: https://github.com/oschwartz10612/poppler-windows/releases\n"
                    "Example: POPPLER_PATH=C:\\poppler\\poppler-25.12.0\\Library\\bin\n"
                    "If pdfinfo.exe exits with 0xC0000135, install Microsoft VC++ Redistributable 2015-2022 (x64): "
                    "https://aka.ms/vs/17/release/vc_redist.x64.exe"
                )
            else:
                error_msg = (
                    "Poppler (pdftoppm) not found. "
                    "Install with: sudo apt-get install poppler-utils\n"
                    "Or set POPPLER_PATH environment variable to Poppler bin directory."
                )
            errors.append(error_msg)
        
        result["errors"] = errors
        return result
    
    @staticmethod
    def check_and_raise():
        """
        Run preflight checks and raise OcrPreflightError if binaries are missing.
        
        Raises:
            OcrPreflightError: With actionable error messages
        """
        result = OcrPreflight.check()
        
        if result["errors"]:
            error_text = "\n".join(result["errors"])
            raise OcrPreflightError(error_text)
        
        return result
