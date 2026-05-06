"""
QA Role Tagging Report: human review of role distribution by document.

Usage:
  $env:PYTHONPATH="."; python ./tools/qa_role_tagging_report.py <document_id>

Output:
  - role_distribution
  - role_tagging_metrics (known_role_ratio, exercise_ratio, concept_ratio)
  - First 3 chunks per role: chunk_id, pages, short preview
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from uuid import UUID

from app.db.session import SessionLocal
from app.domains.content_ingestion.models import Document, Chunk


def _preview(text: str, max_len: int = 120) -> str:
    if not text:
        return ""
    t = (text or "").strip().replace("\n", " ")
    if len(t) <= max_len:
        return t
    return t[: max_len - 3] + "..."


def main() -> int:
    parser = argparse.ArgumentParser(description="Role tagging QA report for a document")
    parser.add_argument("document_id", help="Document UUID")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    try:
        doc_id = UUID(args.document_id)
    except ValueError:
        print(f"Invalid document_id: {args.document_id}", file=sys.stderr)
        return 1

    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if not doc:
            print(f"Document {doc_id} not found", file=sys.stderr)
            return 1

        chunks = (
            db.query(Chunk)
            .filter(Chunk.document_id == doc_id)
            .order_by(Chunk.page_start_pdf.asc(), Chunk.chunk_id.asc())
            .all()
        )

        meta = doc.processing_metadata or {}
        role_dist = meta.get("role_distribution")
        role_metrics = meta.get("role_tagging_metrics")
        if not role_dist and chunks:
            from app.domains.content_ingestion.services.role_tagger import (
                compute_role_distribution,
                compute_role_tagging_metrics,
            )
            fake_chunks = [type("_", (), {"metadata": ch.metadata_json})() for ch in chunks]
            role_dist = compute_role_distribution(fake_chunks)
            role_metrics = compute_role_tagging_metrics(role_dist, len(chunks))
        elif role_dist and not role_metrics:
            from app.domains.content_ingestion.services.role_tagger import compute_role_tagging_metrics
            role_metrics = compute_role_tagging_metrics(role_dist, len(chunks))
        role_dist = role_dist or {}
        role_metrics = role_metrics or {}

        # Build chunks by role
        by_role: dict[str, list[dict]] = defaultdict(list)
        for ch in chunks:
            m = ch.metadata_json or {}
            role = m.get("role") or "unknown"
            by_role[role].append({
                "chunk_id": ch.chunk_id,
                "page_start": ch.page_start_pdf,
                "page_end": ch.page_end_pdf,
                "preview": _preview(ch.text),
            })

        # First 3 per role
        samples = {}
        for r in sorted(by_role.keys()):
            samples[r] = by_role[r][:3]

        report = {
            "document_id": str(doc_id),
            "filename": doc.filename,
            "total_chunks": len(chunks),
            "role_distribution": role_dist,
            "role_tagging_metrics": role_metrics,
            "chunks_by_role_sample": samples,
        }

        if args.json:
            print(json.dumps(report, indent=2))
            return 0

        # Human-readable
        print("=" * 60)
        print(f"Role Tagging Report: {doc.filename}")
        print(f"Document ID: {doc_id}")
        print(f"Total chunks: {len(chunks)}")
        print("=" * 60)
        print("\nRole distribution:")
        for k, v in sorted(role_dist.items()):
            print(f"  {k}: {v}")
        print("\nRole tagging metrics:")
        for k, v in role_metrics.items():
            print(f"  {k}: {v}")
        print("\nFirst 3 chunks per role:")
        for role in sorted(samples.keys()):
            print(f"\n  [{role}]")
            for i, s in enumerate(samples[role], 1):
                pages = f"{s['page_start']}-{s['page_end']}" if s.get("page_start") and s.get("page_end") else str(s.get("page_start", "?"))
                prev = s["preview"]
                if len(prev) > 80:
                    prev = prev[:77] + "..."
                print(f"    {i}. {s['chunk_id']} (p.{pages}): {prev}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
