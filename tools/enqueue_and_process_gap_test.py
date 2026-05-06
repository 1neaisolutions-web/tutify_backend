import asyncio

from sqlalchemy import text

from app.db.session import SessionLocal
from app.domains.content_factory.services.gap_generation_service import GapGenerationService
from app.domains.content_factory.services.gap_generation_worker import GapGenerationWorker
from app.domains.content_registry.enums import ContentStatus


def main() -> None:
    db = SessionLocal()
    try:
        # Pick a subject from existing starter-seed registry rows.
        # This avoids fake subjects and ensures the job is meaningful.
        subject_row = db.execute(
            text(
                "select category "
                "from content_registry "
                "where source_type='starter_seed' and status=:st "
                "and category is not null "
                "order by created_at desc "
                "limit 1"
            ),
            {"st": ContentStatus.PUBLISHED.value},
        ).fetchone()
        subject = subject_row
        if not subject:
            print("No starter subject found in content_registry; abort.")
            return
        subj = subject[0]
        print("Enqueuing gap job for subject:", subj)

        gap = GapGenerationService(db)
        gap.enqueue_gap_jobs(
            locale="en",
            subjects=[subj],
            grade_band=None,
            mode="personalized",
            prefer_non_starter=True,
        )

        worker = GapGenerationWorker(db)
        print("Processing pending gap job (worker.process_once)...")
        result = asyncio.run(worker.process_once())
        if not result:
            print("No pending gap job found after enqueue. It was likely skipped by _has_enough_content.")
            return
        print(
            "Gap job completed:",
            result.id,
            "status:",
            result.status,
            "result_content_id:",
            result.result_content_id,
            "error_message:",
            result.error_message,
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()

