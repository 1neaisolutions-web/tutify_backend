# Poppler Backend Auto-Discovery Fix

## Problem

Backend process was failing with:
```
Poppler (pdfinfo/pdftoppm) not found or DLL dependencies missing. 
Install Poppler for Windows and set POPPLER_PATH environment variable.
```

**Root Cause**: When the backend starts via `uvicorn`, it doesn't inherit environment variables set in test scripts or PowerShell sessions. The `POPPLER_PATH` environment variable wasn't set in the backend process environment.

## Solution

Added automatic Poppler path discovery that runs:
1. **On backend startup** - Startup event handler discovers and sets Poppler path
2. **During preflight checks** - Preflight check auto-discovers Poppler if not found

### Changes Made

#### 1. Enhanced `_find_poppler()` in `ocr_preflight.py`

**Added Windows-specific path auto-discovery:**
- Checks common Windows locations:
  - `C:\poppler\poppler-25.12.0\Library\bin` (clean path, preferred)
  - `C:\poppler\Library\bin` (alternative clean path)
  - `%USERPROFILE%\Downloads\Release-25.12.0-0 (1)\poppler-25.12.0\Library\bin` (Downloads fallback)
  - `C:\Program Files\poppler\bin` (Program Files location)
- When Poppler is found, automatically sets `POPPLER_PATH` in environment
- Prepends Poppler directory to `PATH` for DLL resolution

```python
# Windows-specific default locations (auto-discovery)
if platform.system() == "Windows":
    user_home = os.path.expanduser("~")
    default_paths = [
        r"C:\poppler\poppler-25.12.0\Library\bin",
        r"C:\poppler\Library\bin",
        os.path.join(user_home, r"Downloads\Release-25.12.0-0 (1)\poppler-25.12.0\Library\bin"),
        r"C:\Program Files\poppler\bin",
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
```

#### 2. Added Startup Event Handler in `app/main.py`

**Auto-discovers Poppler and Tesseract on backend startup:**
- Runs when FastAPI app starts
- Checks common Windows paths
- Sets environment variables for the backend process
- Logs discovery results

```python
@app.on_event("startup")
async def startup_event():
    """Initialize backend on startup."""
    import os
    import platform
    from pathlib import Path
    
    # Auto-discover Poppler path if not set
    if not os.getenv("POPPLER_PATH") and platform.system() == "Windows":
        user_home = os.path.expanduser("~")
        poppler_paths = [
            r"C:\poppler\poppler-25.12.0\Library\bin",
            r"C:\poppler\Library\bin",
            os.path.join(user_home, r"Downloads\Release-25.12.0-0 (1)\poppler-25.12.0\Library\bin"),
            r"C:\Program Files\poppler\bin",
        ]
        
        for path_str in poppler_paths:
            poppler_dir = Path(path_str)
            if poppler_dir.is_dir():
                pdftoppm = poppler_dir / "pdftoppm.exe"
                if pdftoppm.exists():
                    os.environ["POPPLER_PATH"] = str(poppler_dir)
                    # Prepend to PATH for DLL resolution
                    current_path = os.environ.get("PATH", "")
                    if str(poppler_dir) not in current_path:
                        os.environ["PATH"] = f"{poppler_dir};{current_path}"
                    logger.info(f"Auto-discovered Poppler at startup: {poppler_dir}")
                    break
    
    # Auto-discover Tesseract if not set
    if not os.getenv("TESSERACT_CMD") and platform.system() == "Windows":
        tesseract_paths = [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        ]
        for path_str in tesseract_paths:
            if Path(path_str).exists():
                os.environ["TESSERACT_CMD"] = path_str
                logger.info(f"Auto-discovered Tesseract at startup: {path_str}")
                break
    
    logger.info("Backend startup initialization complete")
```

## How It Works

### Discovery Priority

1. **Environment Variable** (`POPPLER_PATH`)
   - If set, uses that path (highest priority)

2. **System PATH**
   - Checks if `pdftoppm` is in system PATH

3. **Auto-Discovery** (Windows only)
   - Checks common Windows installation paths
   - Sets `POPPLER_PATH` automatically if found
   - Prepends to `PATH` for DLL resolution

### DLL Resolution

When Poppler is auto-discovered:
- `POPPLER_PATH` is set in the process environment
- Poppler bin directory is prepended to `PATH`
- This ensures `pdfinfo.exe` and `pdftoppm.exe` can find their DLL dependencies

## Testing

### Verify Auto-Discovery

1. **Start backend without POPPLER_PATH set:**
   ```powershell
   # Don't set POPPLER_PATH
   python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
   ```

2. **Check backend logs:**
   ```
   Auto-discovered Poppler at startup: C:\poppler\poppler-25.12.0\Library\bin
   Backend startup initialization complete
   ```

3. **Upload a PDF that requires OCR:**
   - Should now work without manual POPPLER_PATH configuration

### Manual Override

If you want to override auto-discovery:
```powershell
# Set POPPLER_PATH before starting backend
$env:POPPLER_PATH="C:\custom\poppler\path\bin"
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## Benefits

✅ **No manual configuration required** - Backend finds Poppler automatically  
✅ **Works across different environments** - Checks multiple common paths  
✅ **Backward compatible** - Still respects `POPPLER_PATH` if set  
✅ **DLL resolution** - Automatically prepends to PATH for Windows DLL dependencies  
✅ **Also discovers Tesseract** - Same auto-discovery for Tesseract OCR

## Files Modified

- `app/main.py` - Added startup event handler for auto-discovery
- `app/domains/content_ingestion/providers/ocr_preflight.py` - Enhanced `_find_poppler()` with auto-discovery

## Next Steps

1. **Restart backend server** to apply changes
2. **Upload a PDF** that requires OCR
3. **Verify** that OCR runs successfully without manual POPPLER_PATH configuration

The backend will now automatically find Poppler even if `POPPLER_PATH` isn't set in the environment!
