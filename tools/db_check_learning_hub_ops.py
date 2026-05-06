from app.core.config import settings
from sqlalchemy import create_engine, text


def main() -> None:
    engine = create_engine(settings.DATABASE_URL)
    conn = engine.connect()
    try:
        starter_counts = conn.execute(
            text(
                "select source_type, count(id)::int as cnt "
                "from content_registry "
                "where source_type in ('starter_seed','content_factory') "
                "group by source_type"
            )
        ).fetchall()
        print("starter_counts_by_source_type", starter_counts)

        starter_samples = conn.execute(
            text(
                "select content_id, content_type, locale, status, category, difficulty, source_ref, tags "
                "from content_registry "
                "where source_type='starter_seed' "
                "order by created_at desc nulls last limit 10"
            )
        ).fetchall()
        print("starter_samples", starter_samples)

        jobs_gap = conn.execute(
            text(
                "select status, count(id)::int as cnt "
                "from content_generation_jobs "
                "where source = 'gap_detection' "
                "group by status "
                "order by cnt desc"
            )
        ).fetchall()
        print("gap_detection_jobs_by_status", jobs_gap)

        rows = conn.execute(
            text(
                "select status, count(id)::int as cnt "
                "from content_generation_jobs "
                "group by status "
                "order by cnt desc"
            )
        ).fetchall()
        print("jobs_by_status", rows)

        latest = conn.execute(
            text(
                "select id, status, job_type, content_type, locale, source, "
                "created_at, updated_at, priority "
                "from content_generation_jobs "
                "order by created_at desc limit 5"
            )
        ).fetchall()
        print("latest_jobs", latest)

        reg = conn.execute(
            text(
                "select content_id, content_type, locale, status, source_type, "
                "published_at, created_at "
                "from content_registry "
                "where source_type = :st and status = :s "
                "order by published_at desc nulls last limit 5"
            ),
            {"st": "content_factory", "s": "published"},
        ).fetchall()
        print("latest_published_factory", reg)
    finally:
        conn.close()


if __name__ == "__main__":
    main()

