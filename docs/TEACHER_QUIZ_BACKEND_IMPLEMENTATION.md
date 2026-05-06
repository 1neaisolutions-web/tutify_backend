# Teacher Quiz Backend — Implementation Appendix (Plan Completion)

This document **completes the technical plan** with file-level specs, table layouts, API list, and `DemoQuiz` mapping so engineering can implement without guesswork.

**Applying code in Cursor:** non-markdown file edits require **Agent mode** (Plan mode only allows markdown). Ask the agent to implement from this document, or apply migrations and modules manually.

This file lives at `1ne_backend/docs/TEACHER_QUIZ_BACKEND_IMPLEMENTATION.md`.

---

## 1. Alembic migration

- **Revision:** new file `alembic/versions/t5u6v7w8x9y0_create_teacher_quiz_tables.py`
- **`down_revision`:** `r4s5t6u7v8w9` (current personalization head; verify with `python -m alembic heads` in your venv).
- **Tables:** `teacher_quizzes`, `teacher_quiz_questions`, `teacher_quiz_generation_runs` (see model columns below).
- Use **PostgreSQL** types: `UUID`, `JSONB`, `TIMESTAMP WITH TIME ZONE`.

---

## 2. SQLAlchemy models (`app/domains/teacher_quiz/models.py`)

**`teacher_quizzes`**

| Column | Type | Notes |
|--------|------|--------|
| id | UUID PK | |
| tenant_id | UUID FK tenants | index |
| owner_user_id | UUID FK users | |
| title, subject, grade | string | |
| student_instructions, teacher_notes | text nullable | |
| time_limit_minutes | int default 30 | |
| status | string | draft, published, scheduled, archived |
| assigned_at, due_at | timestamptz nullable | |
| source_pack_ids | JSONB | list of UUID strings |
| scope_topics | JSONB | list of strings |
| scope_refinement | text nullable | |
| generate_without_sources | bool | |
| shuffle_questions, shuffle_answers, negative_marking | bool | |
| difficulty | string nullable | foundation / standard / challenge |
| handout_layout | JSONB nullable | mirrors UI |
| class_keys | JSONB | UI `classes` |
| questions_count | int | denormalized |
| total_marks | float | denormalized |
| submission_count | int | placeholder for analytics |
| avg_score | float nullable | placeholder |
| content_version | int | optimistic concurrency |
| created_at, updated_at | timestamptz | |

**`teacher_quiz_questions`:** id, quiz_id FK CASCADE, sort_order, type (mcq|tf|short), prompt, points, options JSONB nullable, response_lines int nullable, extra JSONB nullable.

**`teacher_quiz_generation_runs`:** id, quiz_id FK CASCADE, status, error_code, error_message, input_hash, idempotency_key nullable indexed, retrieval_warnings, retrieval_metadata, llm_model, created_at.

**Index:** `(tenant_id, status, updated_at)` on `teacher_quizzes`.

---

## 3. Register models

In [`app/db/base.py`](app/db/base.py), import `TeacherQuiz`, `TeacherQuizQuestion`, `TeacherQuizGenerationRun` so Alembic autogenerate sees them (optional if you hand-write migration).

---

## 4. Pydantic schemas (`schemas.py`)

- **QuizCreateRequest**, **QuizPatchRequest** — fields optional on patch; align names with [`DemoQuiz`](1ne-frontend/src/pages/features/teacher-tools/demo/teacherToolsDemoData.ts).
- **QuizQuestionApi** — id, type, prompt, points, options?, response_lines?, extra?
- **QuizResponse** — full quiz + `questions: List[QuizQuestionApi]`.
- **QuizListResponse** — `items`, `total`, `page`, `page_size`.
- **QuizGenerateRequest** — question_count, mix (balanced/custom), counts per type, include_mcq/tf/short, teacher_notes, optional idempotency handled at HTTP layer.
- **QuizGenerateResponse** — quiz snapshot + `warnings: list[str]`, `generation_run_id`.

Include **`demo_compat`** optional nested object mirroring `DemoQuiz` for zero-friction frontend wiring later.

---

## 5. Repository (`repository.py`)

Tenant-scoped CRUD:

- `list_quizzes(tenant_id, filters, skip, limit)`
- `get_quiz(tenant_id, quiz_id)` with `joinedload(questions)`
- `create_quiz`, `update_quiz`, `delete_quiz`
- `replace_questions(quiz_id, questions)` in one transaction
- `duplicate_quiz` — copy row + questions, new UUID, title suffix `" (copy)"`

---

## 6. Retrieval facade (`retrieval.py`)

**No OCR imports.** Only:

- Validate packs belong to tenant (reuse [`QuizCatalogService`](1ne_backend/app/domains/content_ingestion/quiz_catalog_service.py) patterns).
- Query `Chunk` + `Document` for `Document.status == published`, `Document.tenant_id`, `pack_id in (...)`.
- Apply topic filter using the same helpers as catalog: import `QUIZ_CATALOG_FULL_TEXT_STRAND`, `_chunks_match_topic_strings_clause`, `_topic_strings_apply_chunk_filter` from `quiz_catalog_service.py` (or duplicate minimal ORM filter to avoid tight coupling — prefer one shared internal module in a follow-up refactor).

**Fallback order:**

1. Filtered by selected topic strands.
2. If chunk count &lt; minimum: drop topic filter (full pack text strand behavior).
3. If still empty and `generate_without_sources`: return empty context + flag for LLM topic-only mode.

Return: concatenated context text, list of citation dicts `{chunk_id, document_id, page_range}`, `warnings[]`.

---

## 7. Generation (`generation.py`)

- **`QuizGenerationService`** with `async def generate(...)`:
  - Build system + user prompt JSON schema for MCQ/TF/short.
  - Call [`ModelRouter.generate`](1ne_backend/app/llm/router.py) (same as worksheets).
  - Parse JSON; repair strip markdown fences.
  - Validate counts and types; clamp MCQ options.
- Map difficulty profile `foundation|standard|challenge` to prompt tone (reuse worksheet difficulty language style where applicable).

**Config:** add `QUIZ_GENERATION_TIMEOUT_SECONDS` in [`app/core/config.py`](1ne_backend/app/core/config.py) (default `180.0`).

---

## 8. Application service (`service.py`)

- Orchestrates repository + generation + retrieval.
- **`generate_for_quiz`:** load quiz → merge request params → call retrieval → call generation → `replace_questions` → update denormalized counts/marks → insert `TeacherQuizGenerationRun` → increment `content_version`.
- **Errors:** raise domain exceptions mapped in routes to HTTP `detail={"code":"...", "message":"..."}`.

---

## 9. HTTP routes (`routes.py`)

- `APIRouter(prefix="/api/v1/teacher-tools", tags=["teacher-quiz"])`
- `GET /quizzes` — list + filters (`q`, `subject`, `grade`, `status`, `date_from`, `date_to`, `class_key`).
- `POST /quizzes` — create.
- `GET /quizzes/{id}` — detail.
- `PATCH /quizzes/{id}` — partial update.
- `DELETE /quizzes/{id}`.
- `POST /quizzes/{id}/duplicate`.
- `POST /quizzes/{id}/generate` — `asyncio.wait_for` with `QUIZ_GENERATION_TIMEOUT_SECONDS`; set `X-Request-Id`; honor `Idempotency-Key` header (store on last run / dedupe).

**Auth:** `Depends(require_any_role("teacher", "school_admin", "super_admin", "org_admin"))` — mirror [`quiz_catalog_routes.py`](1ne_backend/app/domains/content_ingestion/quiz_catalog_routes.py).

---

## 10. Register router

In [`app/api/v1/__init__.py`](1ne_backend/app/api/v1/__init__.py):

```python
from app.domains.teacher_quiz import routes as teacher_quiz_routes
router.include_router(teacher_quiz_routes.router)
```

Export `router` from `app/domains/teacher_quiz/routes.py`.

---

## 11. Tests (`tests/test_teacher_quiz_api.py`)

- Schema roundtrip tests (no DB).
- `_parse_llm_json` / question normalization unit tests.
- Optional: `TestClient` + `dependency_overrides` for `get_current_user` and `get_db` (see worksheet tests).

---

## 12. Contract mapping (`DemoQuiz`)

| DemoQuiz field | API / DB |
|----------------|----------|
| id | `id` (UUID string in JSON) |
| title, subject, grade | same |
| classes | `class_keys` |
| questions | `questions_count` |
| totalMarks | `total_marks` |
| timeLimitMinutes | `time_limit_minutes` |
| status | `status` |
| submissionCount / avgScore | `submission_count` / `avg_score` |
| topic | derive string from `scope_topics` + `scope_refinement` or store redundant `topic_summary` column (optional optimization) |
| sourceBookIds | `source_pack_ids` |
| scopeTopics / scopeRefinement | same |
| sourceSummary | compute client-side or add optional `source_summary` text column |
| questionStubs | `questions` array |
| studentInstructions / difficulty / shuffle* / negativeMarking / handoutLayout | same column names |

---

## 13. OCR teammate boundary

- Quiz domain **never** imports `ocr_providers` or `IngestionService`.
- Failed OCR → document never reaches **published** → retrieval returns empty → generation uses documented fallbacks + warnings.

---

**Next step:** Enable **Agent mode** and ask to “implement Teacher Quiz per `docs/TEACHER_QUIZ_BACKEND_IMPLEMENTATION.md`” for file creation and migration.
