from app.db.session import SessionLocal
from app.domains.recommendation_engine.services.recommendation_ranking_service import (
    RecommendationRankingService,
)
from sqlalchemy import text


def main() -> None:
    db = SessionLocal()
    try:
        teacher_id_row = db.execute(
            text(
                "select user_id from teacher_profile_context order by updated_at desc limit 1"
            )
        ).fetchone()
        if not teacher_id_row:
            print("No teacher_profile_context rows found.")
            return
        teacher_id = teacher_id_row[0]

        ranking = RecommendationRankingService(db)
        resp = ranking.get_learning_hub_recommendations(teacher_id=teacher_id, locale="en", limit=6, mode="personalized")
        primary = [c.content_id for c in resp.primary_recommendations]
        secondary = [c.content_id for c in resp.secondary_recommendations]
        print("teacher_id:", teacher_id)
        print("primary_content_ids:", primary)
        print("secondary_content_ids:", secondary)
    finally:
        db.close()


if __name__ == "__main__":
    main()

