"""
QA E2E: ingestion (scanned PDF OCR) + worksheet generation.

Designed to run locally without HTTP (service-level E2E) to avoid
framework/client dependency mismatches while still exercising:
- DB models + processing state machine
- OCR decision + OCR execution
- chunking + embeddings + indexing
- worksheet retrieval + generation + caching

Run examples (PowerShell):
  $env:PYTHONPATH="."; $env:OCR_MODE="local"; python ./tools/qa_test_non_math_ocr_pdf_flow.py --pdf "./ocr_test_non_math_scanned_10_pages.pdf"
  $env:PYTHONPATH="."; $env:OCR_MODE="api";   python ./tools/qa_test_non_math_ocr_pdf_flow.py --pdf "./ocr_test_non_math_scanned_10_pages.pdf" --api-fallback-check
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import settings
from app.db.session import SessionLocal
from app.domains.auth.models import (
    Tenant,
    TenantType,
    User,
    UserStatus,
    Role,
    RoleName,
    RoleScope,
    UserRole,
)
from app.domains.content_ingestion.models import (
    Document,
    Chunk,
    WorksheetCache,
    DocumentProcessingRun,
)
from app.domains.content_ingestion.schemas import ContentPackCreate
from app.domains.content_ingestion.services.content_pack_service import ContentPackService
from app.domains.content_ingestion.services.document_service import DocumentService
from app.domains.content_ingestion.services.ingestion_service import IngestionService
from app.domains.content_ingestion.services.worksheet_service import WorksheetService


@dataclass
class PackInfo:
    name: str
    pack_id: UUID


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_qa_user_and_role(db) -> User:
    tenant = db.query(Tenant).order_by(Tenant.created_at.asc()).first()
    if not tenant:
        tenant = Tenant(
            name="QA Tenant",
            slug=f"qa-tenant-{int(time.time())}",
            type=TenantType.ORGANIZATION,
            parent_tenant_id=None,
            hierarchy_path="/qa/",
            settings={},
            is_active=True,
        )
        db.add(tenant)
        db.commit()
        db.refresh(tenant)

    user = db.query(User).filter(User.email == "qa.bot@local.test").first()
    if not user:
        user = User(
            tenant_id=tenant.id,
            email="qa.bot@local.test",
            username="qa_bot",
            password_hash="not-a-real-hash",
            first_name="QA",
            last_name="Bot",
            full_name="QA Bot",
            status=UserStatus.ACTIVE,
            email_verified=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    role = db.query(Role).filter(Role.name == RoleName.ORG_ADMIN).first()
    if not role:
        role = Role(
            name=RoleName.ORG_ADMIN,
            description="QA role for local testing",
            scope=RoleScope.ORGANIZATION,
            is_system_role=True,
            is_active=True,
        )
        db.add(role)
        db.commit()
        db.refresh(role)

    user_role = db.query(UserRole).filter(
        UserRole.user_id == user.id,
        UserRole.tenant_id == user.tenant_id,
        UserRole.role_id == role.id,
    ).first()
    if not user_role:
        user_role = UserRole(user_id=user.id, tenant_id=user.tenant_id, role_id=role.id)
        db.add(user_role)
        db.commit()

    return user


def _create_pack(db, *, tenant_id, created_by, name: str, ocr_policy: str) -> PackInfo:
    svc = ContentPackService(db)
    pack = svc.create_pack(
        data=ContentPackCreate(
            name=name,
            description="QA pack for OCR/worksheet E2E",
            subject="Computer Science",
            grade="10",
            curriculum="Generic",
            ocr_policy=ocr_policy,
            metadata={"qa_created_at": _now_iso()},
        ),
        tenant_id=tenant_id,
        created_by=created_by,
    )
    return PackInfo(name=name, pack_id=pack.id)


def _create_document_like_upload(db, *, tenant_id, uploaded_by, pack_id: UUID, pdf_path: Path) -> UUID:
    # Copy PDF into DOCUMENTS_DIR so ingestion uses the same file layout as the API.
    documents_dir = Path(settings.DOCUMENTS_DIR)
    documents_dir.mkdir(parents=True, exist_ok=True)
    target = documents_dir / f"qa_upload_{pack_id}_{int(time.time())}_{pdf_path.name}"
    target.write_bytes(pdf_path.read_bytes())

    doc_service = DocumentService(db)
    doc = doc_service.create_document(
        pack_id=pack_id,
        filename=pdf_path.name,
        file_path=str(target),
        file_size=target.stat().st_size,
        mime_type="application/pdf",
        source_type="pdf",
        tenant_id=tenant_id,
        uploaded_by=uploaded_by,
        title=f"QA Upload {pdf_path.name}",
        author="QA",
        chapter_map=None,
        document_hash=None,
    )
    return doc.id


def _db_assertions_for_ingestion(db, *, document_id: UUID) -> Dict[str, Any]:
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise RuntimeError("Document not found in DB after upload")

    meta = dict(doc.processing_metadata or {})

    run = (
        db.query(DocumentProcessingRun)
        .filter(DocumentProcessingRun.document_id == doc.id)
        .order_by(DocumentProcessingRun.started_at.desc())
        .first()
    )

    chunks_total = db.query(Chunk).filter(Chunk.document_id == doc.id).count()
    chunks_with_embeddings = db.query(Chunk).filter(Chunk.document_id == doc.id, Chunk.embedding_v.isnot(None)).count()

    return {
        "document_status": doc.status,
        "processing_metadata": meta,
        "processing_run": {
            "status": getattr(run, "status", None),
            "current_step": getattr(run, "current_step", None),
            "completed_steps": getattr(run, "completed_steps", None),
            "pages_processed": getattr(run, "pages_processed", None),
            "chunks_created": getattr(run, "chunks_created", None),
            "vectors_stored": getattr(run, "vectors_stored", None),
        },
        "chunks_total": chunks_total,
        "chunks_with_embeddings": chunks_with_embeddings,
    }


def _db_get_worksheet_retrieval(db, *, worksheet_id: str) -> Dict[str, Any]:
    ws_id = UUID(str(worksheet_id))
    ws = db.query(WorksheetCache).filter(WorksheetCache.id == ws_id).first()
    if not ws:
        raise RuntimeError("WorksheetCache not found in DB")
    retrieval = ws.retrieval_metadata or {}
    return retrieval if isinstance(retrieval, dict) else {}


def _create_document_with_engine_override_and_ingest(
    db,
    *,
    tenant_id,
    uploaded_by,
    pack_id: UUID,
    pdf_path: Path,
    ocr_engine_override: str,
) -> str:
    # Copy PDF into DOCUMENTS_DIR so ingestion uses the same behavior as API upload.
    documents_dir = Path(settings.DOCUMENTS_DIR)
    documents_dir.mkdir(parents=True, exist_ok=True)
    target = documents_dir / f"qa_override_{int(time.time())}_{pdf_path.name}"
    target.write_bytes(pdf_path.read_bytes())

    doc_service = DocumentService(db)
    doc = doc_service.create_document(
        pack_id=pack_id,
        filename=pdf_path.name,
        file_path=str(target),
        file_size=target.stat().st_size,
        mime_type="application/pdf",
        source_type="pdf",
        tenant_id=tenant_id,
        uploaded_by=uploaded_by,
        title="QA Override OCR Engine",
        author="QA",
        chapter_map=None,
        document_hash=None,
    )
    doc.processing_metadata = {"force_ocr": True, "ocr_engine_override": ocr_engine_override}
    db.commit()

    # Run ingestion synchronously in-process so override is definitely applied.
    ing = IngestionService(db)
    asyncio.run(ing.ingest_document(doc.id))
    return str(doc.id)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", required=True, help="Path to scanned 10-page non-math PDF")
    parser.add_argument("--api-fallback-check", action="store_true", help="Also run an OCR engine override to verify API-mode fallback with missing keys")
    parser.add_argument("--report", default="OCR_WORKSHEET_QA_REPORT.md", help="Output report markdown filename (written to repo root)")
    args = parser.parse_args()

    pdf_path = Path(args.pdf).resolve()
    if not pdf_path.exists():
        raise FileNotFoundError(str(pdf_path))

    db = SessionLocal()
    try:
        user = _ensure_qa_user_and_role(db)
        tenant_id = user.tenant_id
        user_id = user.id

        report: Dict[str, Any] = {
            "started_at": _now_iso(),
            "settings": {
                "OCR_MODE": getattr(settings, "OCR_MODE", None),
                "OCR_ENGINE_DEFAULT": getattr(settings, "OCR_ENGINE_DEFAULT", None),
                "OCR_FALLBACK_ENGINE": getattr(settings, "OCR_FALLBACK_ENGINE", None),
                "SCANNED_THRESHOLD_CHARS": getattr(settings, "SCANNED_THRESHOLD_CHARS", None),
                "DOCUMENTS_DIR": str(getattr(settings, "DOCUMENTS_DIR", "")),
            },
            "packs": {},
            "ingestion": {},
            "worksheets": {},
            "failures": [],
        }

        # Phase 1: Create packs A/B
        t0 = time.perf_counter()
        pack_a = _create_pack(db, tenant_id=tenant_id, created_by=user_id, name=f"QA Pack A {int(time.time())}", ocr_policy="non_math")
        pack_b = _create_pack(db, tenant_id=tenant_id, created_by=user_id, name=f"QA Pack B {int(time.time())}", ocr_policy="non_math")
        report["packs"]["A"] = {"id": str(pack_a.pack_id), "name": pack_a.name, "ocr_policy": "non_math"}
        report["packs"]["B"] = {"id": str(pack_b.pack_id), "name": pack_b.name, "ocr_policy": "non_math"}
        report["packs_create_s"] = time.perf_counter() - t0

        # Phase 1: Upload-like document creation (file copied into DOCUMENTS_DIR)
        upload_t0 = time.perf_counter()
        doc_a_id = _create_document_like_upload(db, tenant_id=tenant_id, uploaded_by=user_id, pack_id=pack_a.pack_id, pdf_path=pdf_path)
        doc_b_id = _create_document_like_upload(db, tenant_id=tenant_id, uploaded_by=user_id, pack_id=pack_b.pack_id, pdf_path=pdf_path)
        report["ingestion"]["upload_like_create"] = {"doc_a_id": str(doc_a_id), "doc_b_id": str(doc_b_id), "elapsed_s": time.perf_counter() - upload_t0}

        # Run ingestion for both (full pipeline)
        ing = IngestionService(db)
        ingest_t0 = time.perf_counter()
        asyncio.run(ing.ingest_document(doc_a_id))
        asyncio.run(ing.ingest_document(doc_b_id))
        report["ingestion"]["ingest_elapsed_s"] = time.perf_counter() - ingest_t0

        # DB assertions (metadata + chunks + embeddings)
        report["ingestion"]["doc_a_db"] = _db_assertions_for_ingestion(db, document_id=doc_a_id)
        report["ingestion"]["doc_b_db"] = _db_assertions_for_ingestion(db, document_id=doc_b_id)

        # Phase 2: OCR_MODE api without keys fallback check (forced override)
        if args.api_fallback_check:
            override_engine = "google_document_ai"
            t_override = time.perf_counter()
            doc_override_id = _create_document_with_engine_override_and_ingest(
                db,
                tenant_id=tenant_id,
                uploaded_by=user_id,
                pack_id=pack_b.pack_id,
                pdf_path=pdf_path,
                ocr_engine_override=override_engine,
            )
            report["ingestion"]["api_fallback_check"] = {
                "document_id": doc_override_id,
                "override_engine": override_engine,
                "elapsed_s": time.perf_counter() - t_override,
                "db": _db_assertions_for_ingestion(db, document_id=doc_override_id),
            }

        # Phase 3: Worksheet generation (single pack)
        topic = "Optical Character Recognition"
        ws = WorksheetService(db)
        for diff in ("easy", "medium", "hard"):
            t_ws = time.perf_counter()
            mix = {diff: 1.0}
            w1 = asyncio.run(ws.generate_worksheet(pack_id=pack_a.pack_id, topic_text=topic, difficulty_mix=mix, num_questions=10, question_types=["mcq", "short_answer"]))
            from_cache_1 = bool(getattr(w1, "from_cache", False))
            w2 = asyncio.run(ws.generate_worksheet(pack_id=pack_a.pack_id, topic_text=topic, difficulty_mix=mix, num_questions=10, question_types=["mcq", "short_answer"]))
            from_cache_2 = bool(getattr(w2, "from_cache", False))
            retrieval = _db_get_worksheet_retrieval(db, worksheet_id=str(w1.id))
            citations = (retrieval.get("citations") or []) if isinstance(retrieval.get("citations"), list) else []
            report["worksheets"][f"single_{diff}"] = {
                "elapsed_s": time.perf_counter() - t_ws,
                "worksheet_id": str(w1.id),
                "from_cache_first": from_cache_1,
                "from_cache_second": from_cache_2,
                "citations_count": len(citations),
                "citations_pack_ids": sorted({c.get("pack_id") for c in citations if isinstance(c, dict)}),
                "chapter_page_range": retrieval.get("chapter_page_range"),
                "relevance_avg_sim": retrieval.get("relevance_avg_sim"),
                "relevance_keyword_hits": retrieval.get("relevance_keyword_hits"),
                "retrieval_context_breakdown": {
                    "concept_context": retrieval.get("concept_context"),
                    "assessment_context": retrieval.get("assessment_context"),
                },
            }

        # Phase 4: Multi-pack retrieval
        t_multi = time.perf_counter()
        w_multi = asyncio.run(
            ws.generate_worksheet(
                pack_id=pack_a.pack_id,
                pack_ids=[pack_a.pack_id, pack_b.pack_id],
                topic_text=topic,
                difficulty_mix={"medium": 1.0},
                num_questions=10,
                question_types=["mcq", "short_answer"],
            )
        )
        retrieval_m = _db_get_worksheet_retrieval(db, worksheet_id=str(w_multi.id))
        citations_m = (retrieval_m.get("citations") or []) if isinstance(retrieval_m.get("citations"), list) else []
        citation_keys = set()
        dup_count = 0
        for c in citations_m:
            if not isinstance(c, dict):
                continue
            k = (c.get("document_id"), c.get("chunk_id"))
            if k in citation_keys:
                dup_count += 1
            citation_keys.add(k)
        report["worksheets"]["multi_pack_medium"] = {
            "elapsed_s": time.perf_counter() - t_multi,
            "worksheet_id": str(w_multi.id),
            "from_cache": bool(getattr(w_multi, "from_cache", False)),
            "citations_count": len(citations_m),
            "citations_pack_ids": sorted({c.get("pack_id") for c in citations_m if isinstance(c, dict)}),
            "citations_duplicates": dup_count,
            "retrieval_context_breakdown": {
                "concept_context": retrieval_m.get("concept_context"),
                "assessment_context": retrieval_m.get("assessment_context"),
            },
        }

        # Phase 5: Teacher prompt influence
        t_teacher = time.perf_counter()
        teacher_prompt = "Focus on analytical and application-based questions."
        w_tp = asyncio.run(
            ws.generate_worksheet(
                pack_id=pack_a.pack_id,
                topic_text=topic,
                difficulty_mix={"medium": 1.0},
                num_questions=10,
                question_types=["mcq", "short_answer"],
                force_regenerate=True,
                teacher_prompt=teacher_prompt,
            )
        )
        q_text = " ".join((q.get("question") or "") for q in ((w_tp.worksheet_json or {}).get("questions") or []) if isinstance(q, dict)).lower()
        report["worksheets"]["teacher_prompt_medium"] = {
            "elapsed_s": time.perf_counter() - t_teacher,
            "worksheet_id": str(w_tp.id),
            "teacher_prompt": teacher_prompt,
            "heuristics": {
                "mentions_analy": ("analy" in q_text),
                "mentions_apply": ("apply" in q_text or "application" in q_text),
                "mentions_ocr": ("ocr" in q_text or "optical character recognition" in q_text),
            },
        }

        # Write markdown report
        out_path = (Path(__file__).resolve().parent.parent / args.report).resolve()
        md = []
        md.append(f"## OCR + Worksheet QA Report\n\n- **Generated**: `{_now_iso()}`\n- **PDF**: `{pdf_path}`\n")
        md.append("### Settings\n")
        md.append("```json\n" + json.dumps(report["settings"], indent=2) + "\n```\n")
        md.append("### Packs\n")
        md.append("```json\n" + json.dumps(report["packs"], indent=2) + "\n```\n")
        md.append("### Ingestion Results\n")
        md.append("```json\n" + json.dumps(report["ingestion"], indent=2) + "\n```\n")
        md.append("### Worksheet Results\n")
        md.append("```json\n" + json.dumps(report["worksheets"], indent=2) + "\n```\n")
        md.append("### Notes\n\n")
        md.append("- This run validates cache behavior via `WorksheetCache.from_cache` (the API header `X-Worksheet-Cache` is derived from the same flag).\n")
        if report["failures"]:
            md.append("### Failures\n")
            md.append("```json\n" + json.dumps(report["failures"], indent=2) + "\n```\n")
        out_path.write_text("".join(md), encoding="utf-8")

        print(f"[OK] Wrote report: {out_path}")
        return 0

    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

