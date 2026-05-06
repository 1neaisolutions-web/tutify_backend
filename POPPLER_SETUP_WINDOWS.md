# Poppler Setup for Windows - DLL Dependency Fix

## Issue
Poppler binaries exit with code `0xC0000135` (STATUS_DLL_NOT_FOUND), indicating missing Microsoft Visual C++ Redistributable runtime.

## Solution Steps

### Step 1: Move Poppler to Clean Path (Recommended)
1. Create directory: `C:\poppler\poppler-25.12.0\Library\bin`
2. Copy all files from current Poppler location to the new location:
   ```
   Current: C:\Users\rttsg\Downloads\Release-25.12.0-0 (1)\poppler-25.12.0\Library\bin
   Target:  C:\poppler\poppler-25.12.0\Library\bin
   ```
3. Ensure all DLLs and executables are copied (should have ~26 DLLs + executables)

### Step 2: Install VC++ Redistributable
1. Download: https://aka.ms/vs/17/release/vc_redist.x64.exe
2. Run installer (may require admin privileges)
3. Restart terminal/IDE after installation

### Step 3: Verify Setup
Run the test script:
```powershell
python tools/test_poppler_dlls.py
```

Expected output:
```
[PASS] pdfinfo works correctly
```

### Step 4: Set Environment Variable
Set `POPPLER_PATH` to the clean path:
```powershell
$env:POPPLER_PATH="C:\poppler\poppler-25.12.0\Library\bin"
```

Or add to system environment variables permanently.

### Step 5: Run End-to-End Test
```powershell
python tools/run_free_mode_e2e.py
```

## Alternative: Use Current Path
If you prefer to keep Poppler in Downloads:
1. Install VC++ Redistributable (Step 2 above)
2. Set `POPPLER_PATH` to current location
3. The runner script will automatically prepend it to PATH

## Troubleshooting
- If `pdfinfo.exe` still fails after installing VC++ Redistributable:
  - Ensure you installed the **x64** version (not x86)
  - Restart terminal/IDE completely
  - Verify DLLs are in the same directory as `pdfinfo.exe`
  - Check Windows Event Viewer for specific DLL names if needed
