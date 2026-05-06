# Role Tagging PR – Deliverables

## A) File Modification List

| File | Changes |
|------|---------|
| `app/domains/content_ingestion/services/role_tagger.py` | Rewritten: taxonomy, confidence-based heuristics, `get_role_from_structure_map`, `compute_role_distribution` |
| `app/domains/content_ingestion/services/ingestion_service.py` | Role distribution logging; `apply_structure_map_to_chunks` utility |
| `app/domains/content_ingestion/services/worksheet_service.py` | Logging: `concept_preferred_count`, `assessment_preferred_count`, `backfill_count` |
| `app/domains/content_ingestion/schemas.py` | Optional `structure_map` on `DocumentResponse` |
| `app/domains/content_ingestion/README.md` | Role tagging env notes, QA instructions |
| `app/domains/content_ingestion/models.py` | No change (structure_map already exists) |
| `app/core/config.py` | No new knobs (role taxonomy fixed) |

## B) Role Tagging Heuristic List

| Role | Patterns (regex) | Confidence |
|------|------------------|------------|
| exercise_prompt | `exercise\s+\d+`, `review\s+exercise`, `questions?\s+for\s+practice` | 0.85–0.9 |
| exercise_prompt | `^\d+[\.\)]\s+`, `^\(\s*[a-zA-Z]\s*\)\s+`, `^[ivxlcdm]+[\.\)]\s+` | 0.65–0.7 |
| exercise_prompt | `\b(Solve|Find|Prove|Show|Calculate|Evaluate|Simplify)\b` | 0.6 |
| worked_example | `example\s+\d+`, `^Example\s*[:\.]` | 0.85–0.9 |
| worked_example | Step-like numbering | 0.6 |
| solution | `\bsolution\s*[:\.]?\s*$`, `\bsolution\b` | 0.75–0.9 |
| solution | `\banswer(s)?\s*[:\.]?\s*$`, `\banswer(s)?\b` | 0.7–0.85 |
| marking_scheme | `marking\s+scheme`, `marking\s+criteria` | 0.85–0.9 |
| exam_question | `exam(ination)?\s+[Qq]uestion`, `past\s+paper` | 0.7–0.9 |
| concept | `\bis\s+defined\s+as\b`, `\brefers\s+to\b`, `\bmeans\s+that\b`, `\bdefinition\s*[:\.]` | 0.75–0.85 |
| concept | `\[\[MATH\]\]` (math block) | 0.5 |
| unknown | Default when no pattern matches | 0.0 |

## C) Sample chunk.metadata_json

**Before (legacy, no role):**
```json
{}
```

**After auto-tagging:**
```json
{
  "auto_role": "exercise_prompt",
  "auto_confidence": 0.9,
  "role": "exercise_prompt",
  "role_source": "auto"
}
```

**After structure_map override:**
```json
{
  "auto_role": "exercise_prompt",
  "auto_confidence": 0.9,
  "role": "worked_example",
  "role_source": "manual"
}
```

## D) Example role_distribution Log Output

```
role_distribution document_id=abc-123 distribution={'concept': 12, 'worked_example': 8, 'exercise_prompt': 15, 'exam_question': 2, 'solution': 5, 'marking_scheme': 1, 'unknown': 7}
```

Stored in `document.processing_metadata["role_distribution"]`.

## E) QA Instructions

1. **Upload math book** – Ingest a math textbook. Inspect `processing_metadata.role_distribution`:
   - Expect more `exercise_prompt`, `worked_example`, `solution` than a non-math doc.

2. **Upload non-math book** – Ingest a prose/history book. Inspect role_distribution:
   - Expect more `concept`, `unknown`; fewer exercise/solution.

3. **Generate worksheet (medium/hard)** – Inspect `retrieval_metadata`:
   - `concept_context.preferred_count` and `assessment_context.preferred_count` should be > 0 when content has matching roles.
   - `assessment_context` should not be purely backfilled when the doc has exercise/exam content.

4. **Manual override** – Set `document.structure_map` with page ranges and roles, then call:
   ```python
   IngestionService(db).apply_structure_map_to_chunks(document_id)
   ```
   Reapply without re-running OCR or chunking.
