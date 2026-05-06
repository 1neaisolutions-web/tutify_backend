## OCR + Worksheet QA Report

- **Generated**: `2026-03-02T20:35:20.529412+00:00`
- **PDF**: `C:\Users\rttsg\OneDrive\Desktop\1ne\1ne_backend\ocr_test_non_math_scanned_10_pages.pdf`
### Settings
```json
{
  "OCR_MODE": "api",
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
    "id": "97177070-b9a5-49e2-b913-f65c3d5092d0",
    "name": "QA Pack A 1772483531",
    "ocr_policy": "non_math"
  },
  "B": {
    "id": "29b72db1-656a-4355-81b3-af89dc106e5a",
    "name": "QA Pack B 1772483531",
    "ocr_policy": "non_math"
  }
}
```
### Ingestion Results
```json
{
  "upload_like_create": {
    "doc_a_id": "9c325e42-48bc-4712-a104-ab4f675e9527",
    "doc_b_id": "5787c316-3dcf-4382-84f2-85422f453a2f",
    "elapsed_s": 0.6506668000947684
  },
  "ingest_elapsed_s": 121.12136529991403,
  "doc_a_db": {
    "document_status": "published",
    "processing_metadata": {
      "ocr_mode": "api",
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
      "ocr_mode": "api",
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
  "api_fallback_check": {
    "document_id": "8f680b84-1182-4a5a-8496-fe842c46435a",
    "override_engine": "google_document_ai",
    "elapsed_s": 60.93426170013845,
    "db": {
      "document_status": "published",
      "processing_metadata": {
        "ocr_mode": "api",
        "ocr_used": true,
        "pdf_type": "scanned",
        "force_ocr": true,
        "math_density": 0.0,
        "ocr_warnings": [
          "API keys missing for selected engine; using fallback"
        ],
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
        "ocr_decision_reason": "force_ocr=True",
        "ocr_engine_override": "google_document_ai",
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
}
```
### Worksheet Results
```json
{
  "single_easy": {
    "elapsed_s": 0.8562755000311881,
    "worksheet_id": "5c4ee0d8-8f3f-4664-9642-d2653a94284f",
    "from_cache_first": false,
    "from_cache_second": true,
    "citations_count": 2,
    "citations_pack_ids": [
      "97177070-b9a5-49e2-b913-f65c3d5092d0"
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
    "elapsed_s": 0.6608023999724537,
    "worksheet_id": "ea474158-47ba-410b-88bd-606bf2dda2f6",
    "from_cache_first": false,
    "from_cache_second": true,
    "citations_count": 2,
    "citations_pack_ids": [
      "97177070-b9a5-49e2-b913-f65c3d5092d0"
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
    "elapsed_s": 0.6623951999936253,
    "worksheet_id": "73bef65d-1da7-4527-a058-08c2f9126c39",
    "from_cache_first": false,
    "from_cache_second": true,
    "citations_count": 2,
    "citations_pack_ids": [
      "97177070-b9a5-49e2-b913-f65c3d5092d0"
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
    "elapsed_s": 0.6754566999152303,
    "worksheet_id": "e69ea870-f911-4dc4-aba9-da4f09625d92",
    "from_cache": false,
    "citations_count": 6,
    "citations_pack_ids": [
      "29b72db1-656a-4355-81b3-af89dc106e5a",
      "97177070-b9a5-49e2-b913-f65c3d5092d0"
    ],
    "citations_duplicates": 0,
    "retrieval_context_breakdown": {
      "concept_context": {
        "roles": [
          "concept"
        ],
        "chunks": 6
      },
      "assessment_context": {
        "roles": [
          "exercise_prompt",
          "worked_example",
          "exam_question"
        ],
        "chunks": 6
      }
    }
  },
  "teacher_prompt_medium": {
    "elapsed_s": 0.7222221998963505,
    "worksheet_id": "542f7c27-73ec-42a7-846b-6f8adb74a77c",
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
