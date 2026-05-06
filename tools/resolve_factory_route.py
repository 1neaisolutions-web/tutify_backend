from sqlalchemy import text

from app.db.session import SessionLocal
from app.domains.learning_hub.route_resolver import resolve_learning_hub_route


def main() -> None:
    db = SessionLocal()
    try:
        row = db.execute(
            text(
                "select content_id, content_type, category, source_type, json_blob "
                "from content_registry "
                "where source_type='content_factory' "
                "order by created_at desc "
                "limit 1"
            )
        ).fetchone()
        if not row:
            print("No content_factory content_registry rows found.")
            return

        class Obj:
            pass

        o = Obj()
        o.content_id = row[0]
        o.content_type = row[1]
        o.category = row[2]
        o.source_type = row[3]
        o.json_blob = row[4]
        o.tags = {}

        print(
            "latest_factory_item:",
            {
                "content_id": o.content_id,
                "content_type": o.content_type,
                "category": o.category,
                "source_type": o.source_type,
            },
        )
        print("resolved_route:", resolve_learning_hub_route(o))
    finally:
        db.close()


if __name__ == "__main__":
    main()

