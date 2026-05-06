"""
Delete all content packs and their dependent ingestion data.

Usage:
  python scripts/purge_content_packs.py --yes
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import func


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal  # noqa: E402
from app.domains.content_ingestion.models import ContentPack, Document  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Purge all content pack data.")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Required confirmation flag to run destructive delete.",
    )
    args = parser.parse_args()

    if not args.yes:
        print("Refusing to run without --yes")
        return 1

    db = SessionLocal()
    try:
        total_packs = db.query(func.count(ContentPack.id)).scalar() or 0
        total_docs = db.query(func.count(Document.id)).scalar() or 0

        deleted_packs = db.query(ContentPack).delete(synchronize_session=False)
        db.commit()

        print(f"Deleted content packs: {deleted_packs}")
        print(f"Before delete -> packs: {total_packs}, documents: {total_docs}")
        return 0
    except Exception as exc:
        db.rollback()
        print(f"Failed: {exc}")
        return 2
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
