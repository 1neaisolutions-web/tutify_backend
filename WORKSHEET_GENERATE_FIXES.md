# Worksheet Generation: Timeout and Cache Fixes

## What Caused the Timeouts

1. **Short request timeout**: `WORKSHEET_GENERATION_TIMEOUT_SECONDS` was 30s. A single LLM call for 10+ questions often exceeds 30s, so the route’s `asyncio.wait_for(..., 30)` raised `asyncio.TimeoutError` and returned "Generation timed out. Reduce questions or try again."

2. **Per-batch timeout**: Chunked generation (when `num_questions` > 10) used a 12s timeout per batch (`WORKSHEET_LLM_PER_BATCH_TIMEOUT_SEC`). Each batch was wrapped in `asyncio.wait_for(..., 12)`, so any batch taking longer than 12s triggered the same user-facing timeout message.

3. **Cache always on**: Cache lookup and write always ran, so the endpoint depended on `worksheet_cache` DB. For a “no DB storage” phase we needed a way to disable cache entirely.

## What’s Fixed

### A) DB dependency removed when cache disabled

- **Config**: `WORKSHEET_CACHE_ENABLED` (default `false`) in `app/core/config.py`.
- When `WORKSHEET_CACHE_ENABLED=false`:
  - Cache lookup is skipped (no `worksheet_cache` read).
  - Cache write is skipped (no `worksheet_cache` insert).
- Route defaults `skip_cache_write=True` when cache is disabled so the frontend doesn’t need to send it.
- The endpoint returns the worksheet from LLM generation only; no DB writes for the worksheet.

### B) Request timeout raised and made configurable

- **Config**: `WORKSHEET_GENERATION_TIMEOUT_SECONDS` default changed from `30` to `180` (env: `WORKSHEET_GENERATION_TIMEOUT_SECONDS=180`).
- The route uses this value for `asyncio.wait_for(service.generate_worksheet(...), timeout=...)`.
- No artificial short cap; only this single, configurable hard cap.

### C) LLM timeouts and provider timeout handling

- **LLM config** (`app/llm/config.py`): `OPENAI_READ_TIMEOUT` raised from 60s to 150s; `OPENAI_CONNECT_TIMEOUT` remains 10s.
- **Per-batch timeout removed**: Chunked generation no longer uses a 12s per-batch timeout. Only the route’s total timeout and the LLM client’s read timeout apply.
- **Provider timeout → 504**: If the LLM client times out (e.g. httpx timeout), the service raises `LLMProviderTimeoutError`. The route catches it and returns **504** with:
  - `detail.message`: `"LLM provider timeout. Please try again."`
  - `detail.request_id`: request id.
- Retries: still max 1 retry, only for JSON/schema validation failures; no retry on timeout.

### D) Output and prompts

- Strict JSON and normalization (options without letter prefixes, types, etc.) were already in place; no change.
- `max_tokens` remains 4000 to avoid truncation.

### E) Timing instrumentation

- `worksheet_summary` log now includes `cache_enabled=true|false` for both cache-hit and cache-miss paths.
- Logs remain safe (no sensitive prompt/content).

### F) Verification

- **Test script**: `tools/worksheet_performance_test.py` — same payload shape as frontend (pack_id, topic_text, grade, subject, num_questions, question_types, difficulty). Client timeout default 200s so it doesn’t cut off before the backend’s 180s.
- **Cache hit**: In 200 responses, `X-Worksheet-Cache: hit` is used when cache is enabled; with cache disabled all responses are “miss” and no DB writes occur.

## New / Updated Env and Config

| Variable | Default | Description |
|----------|---------|-------------|
| `WORKSHEET_CACHE_ENABLED` | `false` | If false, skip cache lookup and cache write. |
| `WORKSHEET_GENERATION_TIMEOUT_SECONDS` | `180` | Hard cap for the whole generate request (seconds). |
| `OPENAI_CONNECT_TIMEOUT` | `10` | LLM client connect timeout (seconds). |
| `OPENAI_READ_TIMEOUT` | `150` | LLM client read timeout per request (seconds). |

## Proof: Test Run

1. Set in `.env` (or leave defaults):
   - `WORKSHEET_CACHE_ENABLED=false`
   - `WORKSHEET_GENERATION_TIMEOUT_SECONDS=180`
2. Start backend: `uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`
3. Run: `python tools/worksheet_performance_test.py`
4. In server logs you should see:
   - `worksheet_summary ... cache_enabled=false ...` (no cache hit when cache disabled).
   - `total_ms=... llm_ms=...` for successful runs.
   - No "Generation timed out" for normal 10-question runs within 180s.
5. With cache disabled, no rows are written to `worksheet_cache` for these requests.

## Before vs After (typical 10-question run)

- **Before**: 30s request timeout and/or 12s per-batch timeout often triggered "Generation timed out" before the LLM finished.
- **After**: Request can run up to 180s; LLM read timeout 150s per call; no per-batch cap. Worksheet returns successfully when the provider responds in time; only real provider or total request timeout returns 504 with a clear message and `request_id`.
