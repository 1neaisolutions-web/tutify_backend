"""
Teacher Tools cross-domain stats endpoint.
Aggregate queries over quiz, assignment, worksheet, and exam tables (no new tables).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.db.session import get_db
from app.domains.auth.dependencies import require_any_role
from app.domains.auth.models import User
from app.domains.teacher_assignment.models import TeacherAssignment
from app.domains.teacher_exam.models import TeacherExam
from app.domains.teacher_quiz.models import TeacherQuiz
from app.domains.teacher_worksheet.models import TeacherWorksheet

router = APIRouter(prefix="/api/v1/teacher-tools", tags=["teacher-stats"])
_ALLOWED_ROLES = ("teacher", "school_admin", "super_admin", "org_admin")


class AnalyticsTrendPoint(BaseModel):
    date: str  # ISO date "YYYY-MM-DD"
    quiz: int = 0
    assignment: int = 0
    worksheet: int = 0
    exam: int = 0
    total: int = 0


class AnalyticsBreakdownItem(BaseModel):
    label: str
    count: int


class AnalyticsVelocity(BaseModel):
    this_period: int
    prev_period: int
    change_pct: float  # signed; positive = grew


class TeacherToolsAnalyticsResponse(BaseModel):
    period: str
    bucket_size: str  # "day" | "week"
    trend: list[AnalyticsTrendPoint]
    by_subject: list[AnalyticsBreakdownItem]
    by_grade: list[AnalyticsBreakdownItem]
    velocity: AnalyticsVelocity
    total_draft: int
    total_published: int
    total_archived: int
    active_class_keys: int  # distinct class identifiers across all tools
    avg_quiz_score: Optional[float]


def _owner_uuid(user: User) -> UUID:
    uid = user.id
    return uid if isinstance(uid, UUID) else UUID(str(uid))


def _count_by_status(db: Session, model, owner_uuid: UUID) -> dict[str, int]:
    rows = (
        db.query(model.status, func.count().label("n"))
        .filter(model.owner_user_id == owner_uuid)
        .group_by(model.status)
        .all()
    )
    return {str(r.status): int(r.n) for r in rows}


def _count_due_in_next_7_days(db: Session, model, date_col_name: str, owner_uuid: UUID) -> int:
    date_col = getattr(model, date_col_name, None)
    if date_col is None:
        return 0
    now = datetime.now(timezone.utc)
    end = now + timedelta(days=7)
    return (
        db.query(func.count())
        .filter(
            model.owner_user_id == owner_uuid,
            date_col.isnot(None),
            date_col >= now,
            date_col <= end,
        )
        .scalar()
        or 0
    )


def _count_updated_since(
    db: Session,
    model,
    owner_uuid: UUID,
    statuses: tuple[str, ...],
    since_days: int,
) -> int:
    since = datetime.now(timezone.utc) - timedelta(days=since_days)
    updated_col = getattr(model, "updated_at", None)
    if updated_col is None:
        return 0
    return (
        db.query(func.count())
        .filter(
            model.owner_user_id == owner_uuid,
            model.status.in_(list(statuses)),
            updated_col >= since,
        )
        .scalar()
        or 0
    )


def _analytics_data(db: Session, uid: UUID, period: str) -> TeacherToolsAnalyticsResponse:
    period_days = {"7d": 7, "30d": 30, "90d": 90, "365d": 365}
    days = period_days.get(period, 30)
    bucket = "day" if days <= 30 else "week"

    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    prev_since = since - timedelta(days=days)

    trend_sql = sa_text(
        """
        WITH combined AS (
            SELECT DATE_TRUNC(:bucket, created_at)::date AS b, 'quiz' AS tool
            FROM teacher_quizzes WHERE owner_user_id = :uid AND created_at >= :since
            UNION ALL
            SELECT DATE_TRUNC(:bucket, created_at)::date, 'assignment'
            FROM teacher_assignments WHERE owner_user_id = :uid AND created_at >= :since
            UNION ALL
            SELECT DATE_TRUNC(:bucket, created_at)::date, 'worksheet'
            FROM teacher_worksheets WHERE owner_user_id = :uid AND created_at >= :since
            UNION ALL
            SELECT DATE_TRUNC(:bucket, created_at)::date, 'exam'
            FROM teacher_exams WHERE owner_user_id = :uid AND created_at >= :since
        )
        SELECT
            b AS date,
            SUM(CASE WHEN tool='quiz'       THEN 1 ELSE 0 END)::int AS quiz,
            SUM(CASE WHEN tool='assignment' THEN 1 ELSE 0 END)::int AS assignment,
            SUM(CASE WHEN tool='worksheet'  THEN 1 ELSE 0 END)::int AS worksheet,
            SUM(CASE WHEN tool='exam'       THEN 1 ELSE 0 END)::int AS exam,
            COUNT(*)::int AS total
        FROM combined
        GROUP BY b
        ORDER BY b
        """
    )

    trend_rows = db.execute(trend_sql, {"uid": uid, "since": since, "bucket": bucket}).fetchall()
    trend = [
        AnalyticsTrendPoint(
            date=str(r.date),
            quiz=int(r.quiz),
            assignment=int(r.assignment),
            worksheet=int(r.worksheet),
            exam=int(r.exam),
            total=int(r.total),
        )
        for r in trend_rows
    ]

    subject_sql = sa_text(
        """
        SELECT subject AS label, COUNT(*)::int AS count FROM (
            SELECT subject FROM teacher_quizzes
            WHERE owner_user_id = :uid AND subject IS NOT NULL AND subject <> ''
            UNION ALL
            SELECT subject FROM teacher_assignments
            WHERE owner_user_id = :uid AND subject IS NOT NULL AND subject <> ''
            UNION ALL
            SELECT subject FROM teacher_worksheets
            WHERE owner_user_id = :uid AND subject IS NOT NULL AND subject <> ''
            UNION ALL
            SELECT subject FROM teacher_exams
            WHERE owner_user_id = :uid AND subject IS NOT NULL AND subject <> ''
        ) s GROUP BY subject ORDER BY count DESC LIMIT 10
        """
    )
    by_subject = [
        AnalyticsBreakdownItem(label=str(r.label), count=int(r.count))
        for r in db.execute(subject_sql, {"uid": uid}).fetchall()
    ]

    grade_sql = sa_text(
        """
        SELECT grade AS label, COUNT(*)::int AS count FROM (
            SELECT grade FROM teacher_quizzes    WHERE owner_user_id = :uid AND grade IS NOT NULL AND grade <> ''
            UNION ALL
            SELECT grade FROM teacher_assignments WHERE owner_user_id = :uid AND grade IS NOT NULL AND grade <> ''
            UNION ALL
            SELECT grade FROM teacher_worksheets  WHERE owner_user_id = :uid AND grade IS NOT NULL AND grade <> ''
            UNION ALL
            SELECT grade FROM teacher_exams       WHERE owner_user_id = :uid AND grade IS NOT NULL AND grade <> ''
        ) g GROUP BY grade ORDER BY count DESC LIMIT 10
        """
    )
    by_grade = [
        AnalyticsBreakdownItem(label=str(r.label), count=int(r.count))
        for r in db.execute(grade_sql, {"uid": uid}).fetchall()
    ]

    def _count_in_window(start: datetime, end: datetime) -> int:
        total = 0
        for model in (TeacherQuiz, TeacherAssignment, TeacherWorksheet, TeacherExam):
            total += (
                db.query(func.count())
                .filter(model.owner_user_id == uid, model.created_at >= start, model.created_at < end)
                .scalar()
                or 0
            )
        return int(total)

    this_period = _count_in_window(since, now)
    prev_period = _count_in_window(prev_since, since)
    change_pct = round((this_period - prev_period) / max(prev_period, 1) * 100, 1)

    quiz_c = _count_by_status(db, TeacherQuiz, uid)
    asgn_c = _count_by_status(db, TeacherAssignment, uid)
    ws_c = _count_by_status(db, TeacherWorksheet, uid)
    exam_c = _count_by_status(db, TeacherExam, uid)

    all_counts = [quiz_c, asgn_c, ws_c, exam_c]
    total_draft = sum(c.get("draft", 0) for c in all_counts)
    total_archived = sum(c.get("archived", 0) for c in all_counts)
    total_published = sum(
        c.get("published", 0)
        + c.get("scheduled", 0)
        + c.get("active", 0)
        + c.get("pending_review", 0)
        + c.get("graded", 0)
        + c.get("completed", 0)
        for c in all_counts
    )

    class_sql = sa_text(
        """
        SELECT COUNT(DISTINCT ck)::int AS n FROM (
            SELECT jsonb_array_elements_text(class_keys) AS ck
            FROM teacher_quizzes WHERE owner_user_id = :uid AND class_keys IS NOT NULL AND jsonb_array_length(class_keys) > 0
            UNION ALL
            SELECT jsonb_array_elements_text(class_keys)
            FROM teacher_assignments WHERE owner_user_id = :uid AND class_keys IS NOT NULL AND jsonb_array_length(class_keys) > 0
            UNION ALL
            SELECT jsonb_array_elements_text(class_keys)
            FROM teacher_worksheets WHERE owner_user_id = :uid AND class_keys IS NOT NULL AND jsonb_array_length(class_keys) > 0
            UNION ALL
            SELECT jsonb_array_elements_text(class_keys)
            FROM teacher_exams WHERE owner_user_id = :uid AND class_keys IS NOT NULL AND jsonb_array_length(class_keys) > 0
        ) ck
        """
    )
    active_class_keys = int(db.execute(class_sql, {"uid": uid}).scalar() or 0)

    avg_score_row = (
        db.query(func.avg(TeacherQuiz.avg_score))
        .filter(
            TeacherQuiz.owner_user_id == uid,
            TeacherQuiz.avg_score.isnot(None),
            TeacherQuiz.avg_score > 0,
        )
        .scalar()
    )
    avg_quiz_score = round(float(avg_score_row), 1) if avg_score_row else None

    return TeacherToolsAnalyticsResponse(
        period=period,
        bucket_size=bucket,
        trend=trend,
        by_subject=by_subject,
        by_grade=by_grade,
        velocity=AnalyticsVelocity(
            this_period=this_period,
            prev_period=prev_period,
            change_pct=change_pct,
        ),
        total_draft=int(total_draft),
        total_published=int(total_published),
        total_archived=int(total_archived),
        active_class_keys=int(active_class_keys),
        avg_quiz_score=avg_quiz_score,
    )


def _total_active(counts: dict[str, int]) -> int:
    return sum(v for k, v in counts.items() if k != "archived")


@router.get("/stats")
def get_teacher_tools_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_role(*_ALLOWED_ROLES)),
):
    uid = _owner_uuid(current_user)

    quiz_counts = _count_by_status(db, TeacherQuiz, uid)
    asgn_counts = _count_by_status(db, TeacherAssignment, uid)
    ws_counts = _count_by_status(db, TeacherWorksheet, uid)
    exam_counts = _count_by_status(db, TeacherExam, uid)

    asgn_live = (
        asgn_counts.get("active", 0)
        + asgn_counts.get("pending_review", 0)
        + asgn_counts.get("graded", 0)
    )
    exam_live = exam_counts.get("scheduled", 0) + exam_counts.get("completed", 0)

    quiz_due = _count_due_in_next_7_days(db, TeacherQuiz, "due_at", uid)
    asgn_due = _count_due_in_next_7_days(db, TeacherAssignment, "due_at", uid)
    ws_due = _count_due_in_next_7_days(db, TeacherWorksheet, "due_at", uid)
    exam_due = _count_due_in_next_7_days(db, TeacherExam, "schedule_start", uid)

    quiz_pub_30d = _count_updated_since(db, TeacherQuiz, uid, ("published", "scheduled"), 30)
    asgn_pub_30d = _count_updated_since(
        db, TeacherAssignment, uid, ("active", "pending_review", "graded"), 30
    )
    ws_pub_30d = _count_updated_since(db, TeacherWorksheet, uid, ("published",), 30)
    exam_pub_30d = _count_updated_since(db, TeacherExam, uid, ("scheduled", "completed"), 30)

    quiz_pub_sum = quiz_counts.get("published", 0) + quiz_counts.get("scheduled", 0)

    return {
        "quizzes": {
            "total": sum(quiz_counts.values()),
            "draft": quiz_counts.get("draft", 0),
            "published": quiz_counts.get("published", 0),
            "scheduled": quiz_counts.get("scheduled", 0),
            "archived": quiz_counts.get("archived", 0),
        },
        "assignments": {
            "total": sum(asgn_counts.values()),
            "draft": asgn_counts.get("draft", 0),
            "published": asgn_live,
            "scheduled": 0,
            "archived": asgn_counts.get("archived", 0),
        },
        "worksheets": {
            "total": sum(ws_counts.values()),
            "draft": ws_counts.get("draft", 0),
            "published": ws_counts.get("published", 0),
            "archived": ws_counts.get("archived", 0),
        },
        "exams": {
            "total": sum(exam_counts.values()),
            "draft": exam_counts.get("draft", 0),
            "scheduled": exam_counts.get("scheduled", 0),
            "completed": exam_counts.get("completed", 0),
            "archived": exam_counts.get("archived", 0),
        },
        "summary": {
            "total_active": (
                _total_active(quiz_counts)
                + _total_active(asgn_counts)
                + _total_active(ws_counts)
                + _total_active(exam_counts)
            ),
            "total_draft": (
                quiz_counts.get("draft", 0)
                + asgn_counts.get("draft", 0)
                + ws_counts.get("draft", 0)
                + exam_counts.get("draft", 0)
            ),
            "total_published": quiz_pub_sum + asgn_live + ws_counts.get("published", 0) + exam_live,
            "scheduled_this_week": quiz_due + asgn_due + ws_due + exam_due,
            "published_last_30d": quiz_pub_30d + asgn_pub_30d + ws_pub_30d + exam_pub_30d,
        },
    }


@router.get("/analytics", response_model=TeacherToolsAnalyticsResponse)
def get_teacher_tools_analytics(
    period: str = "30d",
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_role(*_ALLOWED_ROLES)),
):
    if period not in ("7d", "30d", "90d", "365d"):
        period = "30d"
    uid = _owner_uuid(current_user)
    return _analytics_data(db, uid, period)
