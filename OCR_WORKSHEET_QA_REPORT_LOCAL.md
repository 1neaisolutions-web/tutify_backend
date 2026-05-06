## OCR + Worksheet QA Report

- **Generated**: `2026-03-02T20:31:53.554133+00:00`
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
    "id": "da463257-0f65-45fa-8eb7-81ab0d5f0a53",
    "name": "QA Pack A 1772483385",
    "ocr_policy": "non_math"
  },
  "B": {
    "id": "a3425c71-59b9-4960-91a0-40de3949835a",
    "name": "QA Pack B 1772483385",
    "ocr_policy": "non_math"
  }
}
```
### Ingestion Results
```json
{
  "upload_like_create": {
    "doc_a_id": "5d7e619f-7aae-4228-b659-3e200bacb681",
    "doc_b_id": "2e2e6102-6e2d-44e6-8b9c-7e305e539bb3",
    "elapsed_s": 0.7069530999287963
  },
  "ingest_elapsed_s": 121.24863639986143,
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
      "extraction_strategy": "ocr",
      "ocr_decision_reason": "extracted_text_empty",
      "detected_source_type": "pdf"
    },
    "processing_run": {
      "status": "published",
      "current_step": "published",
      "completed_steps": null,
      "pages_processed": 10,
      "chunks_created": 9,
      "vectors_stored": 9
    },
    "chunks_total": 9,
    "chunks_with_embeddings": 9
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
      "extraction_strategy": "ocr",
      "ocr_decision_reason": "extracted_text_empty",
      "detected_source_type": "pdf"
    },
    "processing_run": {
      "status": "published",
      "current_step": "published",
      "completed_steps": null,
      "pages_processed": 10,
      "chunks_created": 9,
      "vectors_stored": 9
    },
    "chunks_total": 9,
    "chunks_with_embeddings": 9
  }
}
```
### Worksheet Results
```json
{
  "single_easy": {
    "elapsed_s": 0.743989699985832,
    "worksheet_id": "c20662d2-c4f2-4253-9278-3ab78cddfcdc",
    "from_cache_first": false,
    "from_cache_second": true,
    "citations_count": 2,
    "citations_pack_ids": [
      "da463257-0f65-45fa-8eb7-81ab0d5f0a53"
    ],
    "chapter_page_range": "9-12",
    "relevance_avg_sim": 0.7857142857142857,
    "relevance_keyword_hits": 3,
    "retrieval_context_breakdown": {
      "concept_context": {
        "roles": [
          "concept"
        ],
        "chunks": 2
      },
      "assessment_context": {
        "roles": [
          "exercise_prompt",
          "worked_example",
          "exam_question"
        ],
        "chunks": 2
      }
    }
  },
  "single_medium": {
    "elapsed_s": 0.7266822000965476,
    "worksheet_id": "330a7662-005e-4b59-8e67-654c435bccd3",
    "from_cache_first": false,
    "from_cache_second": true,
    "citations_count": 2,
    "citations_pack_ids": [
      "da463257-0f65-45fa-8eb7-81ab0d5f0a53"
    ],
    "chapter_page_range": "9-12",
    "relevance_avg_sim": 0.7857142857142857,
    "relevance_keyword_hits": 3,
    "retrieval_context_breakdown": {
      "concept_context": {
        "roles": [
          "concept"
        ],
        "chunks": 2
      },
      "assessment_context": {
        "roles": [
          "exercise_prompt",
          "worked_example",
          "exam_question"
        ],
        "chunks": 2
      }
    }
  },
  "single_hard": {
    "elapsed_s": 0.6582893000449985,
    "worksheet_id": "31603e5b-5f1b-4372-8de7-ae48c3e96820",
    "from_cache_first": false,
    "from_cache_second": true,
    "citations_count": 2,
    "citations_pack_ids": [
      "da463257-0f65-45fa-8eb7-81ab0d5f0a53"
    ],
    "chapter_page_range": "9-12",
    "relevance_avg_sim": 0.7857142857142857,
    "relevance_keyword_hits": 3,
    "retrieval_context_breakdown": {
      "concept_context": {
        "roles": [
          "concept"
        ],
        "chunks": 2
      },
      "assessment_context": {
        "roles": [
          "exercise_prompt",
          "worked_example",
          "exam_question"
        ],
        "chunks": 2
      }
    }
  },
  "multi_pack_medium": {
    "elapsed_s": 0.6764062999282032,
    "worksheet_id": "cf869344-73c4-4f18-a8e4-ffdc63772598",
    "from_cache": false,
    "citations_count": 4,
    "citations_pack_ids": [
      "a3425c71-59b9-4960-91a0-40de3949835a",
      "da463257-0f65-45fa-8eb7-81ab0d5f0a53"
    ],
    "citations_duplicates": 0,
    "retrieval_context_breakdown": {
      "concept_context": {
        "roles": [
          "concept"
        ],
        "chunks": 4
      },
      "assessment_context": {
        "roles": [
          "exercise_prompt",
          "worked_example",
          "exam_question"
        ],
        "chunks": 4
      }
    }
  },
  "teacher_prompt_medium": {
    "elapsed_s": 0.715224500047043,
    "worksheet_id": "f1fb07e1-a3c4-4395-90a2-b36656bdf501",
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
