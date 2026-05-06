# Worksheet Generator Performance Changes

## Summary

- **Instrumentation**: Precise phase timings: `signature_hash_ms`, `content_fetch_ms`, `cache_lookup_ms`, `cache_fetch_ms`, `llm_call_ms`, `parse_normalize_ms`, `cache_write_ms`, `total_ms`; roll-up line `worksheet_summary request_id=... total_ms=... cache_hit=... llm_ms=... db_ms=...`.
- **Response headers**: `X-Worksheet-Cache: hit|miss`, `X-Request-Id: <request_id>` (no breaking change).
- **Chunked generation**: When `num_questions` > 10, split into batches of ≤10; per-batch timeout 12s; merge results; fail gracefully on batch timeout (no partial).
- **Timeouts**: LLM connect/read timeouts; 30s hard cap per request; 504 with `request_id` on timeout.
- **Retry**: Max 1 retry for parse (JSON) errors only.
- **Frontend**: Timeout/error panel with message + request_id; Retry / Reduce to 10 questions / Close; Cancel button; no raw stack traces.

## Before vs After (Target)

| Metric | Before | After (target) |
|--------|--------|-----------------|
| Cache hit (server) | Unmeasured | < 300 ms |
| Cache hit (e2e) | Unmeasured | < 1 s |
| Cache miss (10 q) | Unbounded / no timeout | 5–15 s typical; cap 30 s |
| Cache miss (20 q) | Unbounded | ≤ 25 s; cap 30 s |
| Hang risk | Possible | None (fail fast, 504) |
| Retries | 2 for any error | 1 for parse only |

## Files Changed

| File | Change |
|------|--------|
| `app/core/config.py` | `WORKSHEET_GENERATION_TIMEOUT_SECONDS = 30.0` |
| `app/domains/content_ingestion/services/worksheet_service.py` | Phase timings (`*_ms`), `worksheet_summary` roll-up; chunked generation (batches ≤10, 12s/batch); `from_cache` on cache object; `cache_lookup_ms`/`content_fetch_ms`; retry only for parse |
| `app/domains/content_ingestion/routes.py` | `asyncio.wait_for`, 504 with `request_id`; `Response` headers `X-Request-Id`, `X-Worksheet-Cache` |
| `app/llm/config.py` | `OPENAI_CONNECT_TIMEOUT`, `OPENAI_READ_TIMEOUT` |
| `app/llm/providers/openai_provider.py` | `httpx.Timeout(connect, read)` on `AsyncOpenAI` |
| `tools/worksheet_performance_test.py` | Prints `request_id`, `status_code`, `total_ms` every run; 35s client timeout; env RUNS/SCENARIOS |
| `1ne-frontend/src/pages/features/WorksheetGenerator.tsx` | Error panel (timeout/error), request_id, Retry / Reduce to 10 / Close; 504 detail parsing |

## How to Run the Test

```bash
# Terminal 1: start backend
cd 1ne_backend
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Terminal 2: run test (never hangs; 35s timeout per request)
python tools/worksheet_performance_test.py
```

Optional env: `BASE_URL`, `WORKSHEET_TEST_TIMEOUT` (default 35).

## Diagnosis (from server logs)

Grep for `worksheet_timing` and `worksheet_summary`:

```
worksheet_timing request_id=... phase=signature_hash_ms ms=...
worksheet_timing request_id=... phase=cache_lookup_ms ms=...
worksheet_timing request_id=... phase=content_fetch_ms ms=... chunks=...
worksheet_timing request_id=... phase=llm_call_ms ms=... batches=...
worksheet_timing request_id=... phase=parse_normalize_ms ms=...
worksheet_timing request_id=... phase=cache_write_ms ms=...
worksheet_timing request_id=... phase=total_ms ms=...
worksheet_summary request_id=... total_ms=... cache_hit=... llm_ms=... db_ms=...
```

- **llm_call_ms** dominating → chunked generation (batches) reduces single-call variance; ensure cache is used on repeat.
- **content_fetch_ms** high → retrieval/embedding slow (DB or vector store).
- **cache_lookup_ms** high → ensure index on `worksheet_cache.signature_hash` (unique already indexes).
- **parse_normalize_ms** high → large output or heavy logic (should stay low).

## Before vs After (target)

| Scenario | Before | After (target) |
|----------|--------|----------------|
| Cache hit | Unmeasured | &lt; 300 ms server, &lt; 1 s e2e |
| 10 questions (miss) | Often timed out | 5–15 s typical; chunked if needed |
| 20 questions (miss) | Often timed out | Batches of 10, 12s each; &lt; 30 s total or 504 |
| On timeout | Hang or generic error | 504 + request_id; UI panel + Retry / Reduce / Close |
| Logs | Minimal | worksheet_timing + worksheet_summary with ms |

## Example timing logs (after fix)

```
worksheet_timing request_id=8f7b3544-1408-46f4-bbb8-246632deee86 phase=signature_hash_ms ms=1 num_questions=10 ...
worksheet_timing request_id=8f7b3544-1408-46f4-bbb8-246632deee86 phase=cache_lookup_ms ms=12 ...
worksheet_timing request_id=8f7b3544-1408-46f4-bbb8-246632deee86 phase=content_fetch_ms ms=1200 chunks=8 ...
worksheet_timing request_id=8f7b3544-1408-46f4-bbb8-246632deee86 phase=llm_call_ms ms=8500 batches=1 ...
worksheet_timing request_id=8f7b3544-1408-46f4-bbb8-246632deee86 phase=parse_normalize_ms ms=15 ...
worksheet_timing request_id=8f7b3544-1408-46f4-bbb8-246632deee86 phase=cache_write_ms ms=45 ...
worksheet_summary request_id=8f7b3544-1408-46f4-bbb8-246632deee86 total_ms=9764 cache_hit=false llm_ms=8500 db_ms=57
```

## List of Changes (Why Each Reduces Latency / Risk)

1. **Precise phase timings** – Identifies bottleneck (llm_call_ms vs content_fetch_ms vs db).
2. **Chunked generation (num_questions > 10)** – Batches of ≤10 with 12s/batch; avoids one 20-question call exceeding 30s.
3. **Response headers X-Worksheet-Cache, X-Request-Id** – Client can show cache status and support reference without changing body.
4. **LLM connect/read timeouts** – No hang on network/API.
5. **30s request cap + 504** – No stuck requests; clear message + request_id.
6. **Max 1 retry, parse only** – Fewer duplicate LLM calls.
7. **max_tokens 4000** – Bounded output; less truncation risk than 5000.
8. **Frontend error panel** – Timeout shows actionable message, request_id, Retry / Reduce to 10 / Close; no raw stack.
