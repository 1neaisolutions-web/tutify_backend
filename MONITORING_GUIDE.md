# Document Processing Monitoring Guide

## Real-Time Monitoring System

The system now includes real-time monitoring that shows:
- **Current Status** (uploaded, ocr_running, embedding, etc.)
- **Progress Percentage** (0-100%)
- **Current Step** (what's happening right now)
- **Chunks Count** (how many chunks created)
- **Vectors Stored** (how many embeddings saved)
- **Elapsed Time** (how long processing has taken)

## Monitoring Scripts

### 1. `monitor_live.py` - Live Dashboard (RECOMMENDED)
**Best for: Real-time monitoring with visual dashboard**

```powershell
python monitor_live.py [document_id]
```

**Features:**
- Updates every 3 seconds
- Shows progress bar
- Shows all processing steps
- Highlights current step
- Auto-stops when document is ready or failed
- Shows error messages if processing fails

**Example:**
```powershell
python monitor_live.py 4eb16c21-4470-4ac4-bb6e-f5f1b247e860
```

### 2. `watch_status.py` - Simple Status Monitor
**Best for: Quick status checks**

```powershell
python watch_status.py [document_id]
```

**Features:**
- One-line status updates
- Shows: Status | Progress | Pages | Chunks | Vectors
- Updates every 3 seconds
- Press Ctrl+C to stop

### 3. `monitor_document_processing.py` - Full Monitor
**Best for: Complete monitoring with verification**

```powershell
python monitor_document_processing.py [document_id]
```

**Features:**
- Uses SSE stream for real-time updates
- Falls back to polling if stream unavailable
- Verifies document is ready before stopping
- Shows detailed error messages

### 4. `complete_upload_with_monitoring.py` - Upload + Monitor
**Best for: Upload new document and monitor**

```powershell
python complete_upload_with_monitoring.py
```

**Features:**
- Finds PDF file automatically
- Uploads document via API
- Monitors processing automatically
- Verifies everything works
- Stops only when document is ready

## Processing Status Flow

The system monitors these statuses:

1. **uploaded** → Document uploaded, waiting to process
2. **text_extracting** → Extracting text from PDF
3. **ocr_running** → Running OCR (takes 15-30 min for 193 pages)
4. **normalizing** → Cleaning and normalizing text
5. **chunking** → Creating chunks (500 tokens each)
6. **embedding** → Generating embeddings (OpenAI)
7. **indexing** → Storing in vector database
8. **qa_validation** → Running quality checks
9. **published** → ✓ Ready for use
10. **failed** → ✗ Processing failed (check error message)

## Verification

The system **automatically verifies**:
- ✓ Chunks are created (> 0)
- ✓ Embeddings are stored (> 0)
- ✓ Document status is 'published'
- ✗ If any check fails → Status set to 'FAILED'

**The document will NOT be marked as published if:**
- No chunks are created
- No embeddings are stored
- Processing errors occur

## Current Document Status

To check current status:
```powershell
python check_status.py
```

To monitor live:
```powershell
python monitor_live.py
```

## Troubleshooting

**If document shows "published" but has 0 chunks:**
- This should not happen (system prevents it)
- If it does, run: `python force_ocr_reprocess.py`

**If processing is stuck:**
- Check backend logs
- Verify OCR engine is configured: `OCR_ENGINE=easyocr`
- Verify OpenAI API key is set: `OPENAI_API_KEY=sk-...`

**If OCR is slow:**
- Normal for large PDFs (193 pages = 15-30 minutes)
- EasyOCR downloads models on first use (~500MB)
- Processing is CPU-intensive

## Quick Commands

```powershell
# Monitor current document
python monitor_live.py

# Upload and monitor new document
python complete_upload_with_monitoring.py

# Check status quickly
python check_status.py

# Reprocess failed document
python force_ocr_reprocess.py
```
