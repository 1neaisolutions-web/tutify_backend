# Role Tagging QA Report (Refined Anti-False-Positive)

**Generated**: After refined role tagging (instructional verb + question mark requirement)

## Changes Applied

- **exercise_prompt / exam_question**: Require >= 2 numbered lines AND (instructional verb OR question mark)
- **Numbered lines only**: Classify as `unknown`, not exercise
- **Summary indicators**: "Key Points", "Summary", "Review Notes" → `concept`

---

## 1) Non-Math OCR Test

**Document**: `ocr_test_non_math_scanned_10_pages.pdf`  
**Document ID**: `d36c9693-bc9b-4989-9861-1a14c24357e5`

### role_distribution
| Role | Count |
|------|-------|
| concept | 10 |
| exercise_prompt | 0 |
| exam_question | 0 |
| worked_example | 0 |
| solution | 0 |
| marking_scheme | 0 |
| unknown | 0 |

### role_tagging_metrics
| Metric | Value |
|--------|-------|
| known_role_ratio | 1.0 |
| exercise_ratio | 0.0 |
| concept_ratio | 1.0 |
| total_chunks | 10 |

### assessment_preferred_count vs backfill_count (medium worksheet)
| Metric | Value |
|--------|-------|
| assessment_context.preferred_count | 0 |
| assessment_context.backfill | 2 |

*Expected for non-math doc: no exercise/exam chunks, so assessment is fully backfilled.*

---

## 2) Punjab Math

**Status**: PDF not found in workspace.  
**Action**: Place Punjab math PDF in workspace and run:
```powershell
$env:PYTHONPATH="."; $env:OCR_MODE="local"; python ./tools/qa_test_non_math_ocr_pdf_flow.py --pdf "<path_to_punjab_math.pdf>"
$env:PYTHONPATH="."; python ./tools/qa_role_tagging_report.py <document_id>
```

---

## 3) SNC Math

**Status**: PDF not found in workspace.  
**Action**: Place SNC math PDF in workspace and run same commands as Punjab.

---

## Summary

- **Non-math OCR**: Previously all 10 chunks were `exercise_prompt` (false positive). After refinement: `concept` 10, `exercise_prompt` 0. Numbered checklists without instructional verbs are no longer misclassified as exercises.
- **Punjab/SNC math**: Requires user to provide PDFs and re-run ingestion + report.
