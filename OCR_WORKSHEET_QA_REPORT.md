## OCR + Worksheet QA Report

- **Generated**: `2026-03-02T21:30:46.358035+00:00`
- **PDF**: `C:\Users\rttsg\OneDrive\Desktop\1ne\1ne_backend\ocr_test_non_math_scanned_10_pages.pdf`
### Settings
```json
{
  "OCR_MODE": "local",
  "OCR_ENGINE_DEFAULT": "tesseract",
  "OCR_FALLBACK_ENGINE": "tesseract",
  "SCANNED_THRESHOLD_CHARS": 50,
  "DOCUMENTS_DIR": "uploads/documents"
}
```
### Packs
```json
{
  "A": {
    "id": "d3072885-4536-49c4-9fc7-363373d4fedf",
    "name": "QA Pack A 1772486830",
    "ocr_policy": "non_math"
  },
  "B": {
    "id": "8e7e1cdf-2566-4d0e-8d8c-291b1b3bc578",
    "name": "QA Pack B 1772486830",
    "ocr_policy": "non_math"
  }
}
```
### Ingestion Results
```json
{
  "upload_like_create": {
    "doc_a_id": "d36c9693-bc9b-4989-9861-1a14c24357e5",
    "doc_b_id": "504f951f-8fb2-42c3-9e8f-22432233bfc3",
    "elapsed_s": 0.6764152999967337
  },
  "ingest_elapsed_s": 206.62985979998484,
  "doc_a_db": {
    "document_status": "published",
    "processing_metadata": {
      "ocr_mode": "local",
      "ocr_used": true,
      "pdf_type": "scanned",
      "math_density": 0.0,
      "detected_mime": "application/pdf",
      "ocr_preflight": {
        "poppler_path": "C:\\Users\\rttsg\\Downloads\\Release-25.12.0-0 (1)\\poppler-25.12.0\\Library\\bin",
        "poppler_found": true,
        "tesseract_path": "C:\\Program Files\\Tesseract-OCR\\tesseract.exe",
        "tesseract_found": true
      },
      "ocr_engine_used": "tesseract",
      "content_type_hint": null,
      "role_distribution": {
        "concept": 10,
        "unknown": 0,
        "solution": 0,
        "exam_question": 0,
        "marking_scheme": 0,
        "worked_example": 0,
        "exercise_prompt": 0
      },
      "extraction_strategy": "ocr",
      "ocr_decision_reason": "extracted_text_empty",
      "detected_source_type": "pdf",
      "role_tagging_metrics": {
        "total_chunks": 10,
        "concept_ratio": 1.0,
        "exercise_ratio": 0.0,
        "known_role_ratio": 1.0
      }
    },
    "processing_run": {
      "status": "published",
      "current_step": "published",
      "completed_steps": null,
      "pages_processed": 10,
      "chunks_created": 10,
      "vectors_stored": 10
    },
    "chunks_total": 10,
    "chunks_with_embeddings": 10
  },
  "doc_b_db": {
    "document_status": "published",
    "processing_metadata": {
      "ocr_mode": "local",
      "ocr_used": true,
      "pdf_type": "scanned",
      "math_density": 0.0,
      "detected_mime": "application/pdf",
      "ocr_preflight": {
        "poppler_path": "C:\\Users\\rttsg\\Downloads\\Release-25.12.0-0 (1)\\poppler-25.12.0\\Library\\bin",
        "poppler_found": true,
        "tesseract_path": "C:\\Program Files\\Tesseract-OCR\\tesseract.exe",
        "tesseract_found": true
      },
      "ocr_engine_used": "tesseract",
      "content_type_hint": null,
      "role_distribution": {
        "concept": 10,
        "unknown": 0,
        "solution": 0,
        "exam_question": 0,
        "marking_scheme": 0,
        "worked_example": 0,
        "exercise_prompt": 0
      },
      "extraction_strategy": "ocr",
      "ocr_decision_reason": "extracted_text_empty",
      "detected_source_type": "pdf",
      "role_tagging_metrics": {
        "total_chunks": 10,
        "concept_ratio": 1.0,
        "exercise_ratio": 0.0,
        "known_role_ratio": 1.0
      }
    },
    "processing_run": {
      "status": "published",
      "current_step": "published",
      "completed_steps": null,
      "pages_processed": 10,
      "chunks_created": 10,
      "vectors_stored": 10
    },
    "chunks_total": 10,
    "chunks_with_embeddings": 10
  }
}
```
### Worksheet Results
```json
{
  "single_easy": {
    "elapsed_s": 1.53011679998599,
    "worksheet_id": "2ece0d5d-8b0f-44f8-a758-060e3c1af56a",
    "from_cache_first": false,
    "from_cache_second": true,
    "citations_count": 2,
    "citations_pack_ids": [
      "d3072885-4536-49c4-9fc7-363373d4fedf"
    ],
    "chapter_page_range": "9-12",
    "relevance_avg_sim": 0.7857142857142857,
    "relevance_keyword_hits": 3,
    "retrieval_context_breakdown": {
      "concept_context": {
        "roles": [
          "concept",
          "worked_example"
        ],
        "chunks": 2,
        "backfill": 0,
        "preferred_count": 2
      },
      "assessment_context": {
        "roles": [
          "exercise_prompt",
          "exam_question"
        ],
        "chunks": 2,
        "backfill": 2,
        "preferred_count": 0
      }
    }
  },
  "single_medium": {
    "elapsed_s": 0.8157865998800844,
    "worksheet_id": "8c112234-5ae5-472d-9b08-394347b416ce",
    "from_cache_first": false,
    "from_cache_second": true,
    "citations_count": 2,
    "citations_pack_ids": [
      "d3072885-4536-49c4-9fc7-363373d4fedf"
    ],
    "chapter_page_range": "9-12",
    "relevance_avg_sim": 0.7857142857142857,
    "relevance_keyword_hits": 3,
    "retrieval_context_breakdown": {
      "concept_context": {
        "roles": [
          "concept",
          "worked_example"
        ],
        "chunks": 2,
        "backfill": 0,
        "preferred_count": 2
      },
      "assessment_context": {
        "roles": [
          "exercise_prompt",
          "exam_question"
        ],
        "chunks": 2,
        "backfill": 2,
        "preferred_count": 0
      }
    }
  },
  "single_hard": {
    "elapsed_s": 0.7966813000384718,
    "worksheet_id": "e187be27-4826-4d3f-a6f7-b61ee18df9bf",
    "from_cache_first": false,
    "from_cache_second": true,
    "citations_count": 2,
    "citations_pack_ids": [
      "d3072885-4536-49c4-9fc7-363373d4fedf"
    ],
    "chapter_page_range": "9-12",
    "relevance_avg_sim": 0.7857142857142857,
    "relevance_keyword_hits": 3,
    "retrieval_context_breakdown": {
      "concept_context": {
        "roles": [
          "concept",
          "worked_example"
        ],
        "chunks": 2,
        "backfill": 0,
        "preferred_count": 2
      },
      "assessment_context": {
        "roles": [
          "exercise_prompt",
          "exam_question"
        ],
        "chunks": 2,
        "backfill": 2,
        "preferred_count": 0
      }
    }
  },
  "multi_pack_medium": {
    "elapsed_s": 0.8770230000372976,
    "worksheet_id": "eb1548a3-9ef5-4486-b62c-4a55f9223a4f",
    "from_cache": false,
    "citations_count": 4,
    "citations_pack_ids": [
      "8e7e1cdf-2566-4d0e-8d8c-291b1b3bc578",
      "d3072885-4536-49c4-9fc7-363373d4fedf"
    ],
    "citations_duplicates": 0,
    "retrieval_context_breakdown": {
      "concept_context": {
        "roles": [
          "concept",
          "worked_example"
        ],
        "chunks": 4,
        "backfill": 0,
        "preferred_count": 4
      },
      "assessment_context": {
        "roles": [
          "exercise_prompt",
          "exam_question"
        ],
        "chunks": 4,
        "backfill": 4,
        "preferred_count": 0
      }
    }
  },
  "teacher_prompt_medium": {
    "elapsed_s": 0.8712504000868648,
    "worksheet_id": "c18166cd-e646-45d2-ad1b-02767282dd9a",
    "teacher_prompt": "Focus on analytical and application-based questions.",
    "heuristics": {
      "mentions_analy": true,
      "mentions_apply": true,
      "mentions_ocr": true
    }
  }
}
```
### Notes

- This run validates cache behavior via `WorksheetCache.from_cache` (the API header `X-Worksheet-Cache` is derived from the same flag).
