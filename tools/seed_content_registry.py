"""
Seed the content registry with sample items (one MICRO_COURSE, one AI_GUIDED_TUTORIAL,
one LEARNING_PATH). Idempotent: skips existing content_id. Run from project root:

    python tools/seed_content_registry.py
"""
from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.db.session import SessionLocal
from app.domains.content_registry.services import ContentRegistryService


def main() -> None:
    db = SessionLocal()
    try:
        service = ContentRegistryService(db)
        created = service.seed_sample_content()
        print(f"Content registry seed: {len(created)} item(s) created.")
        for item in created:
            print(f"  - {item.content_id} ({item.content_type}): {item.title}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
