"""
Aggregates history across multiple source tables via a UNION ALL query.

We use raw SQL intentionally; expressing cross-model unions cleanly in the ORM is painful.
All user-provided values are passed via bindings (no string interpolation except safe table/column constants).
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session


SOURCE_TYPES_ALL: tuple[str, ...] = (
    "quiz",
    "assignment",
    "worksheet",
    "exam",
    "chatbot_conversation",
    "pixgen_generation",
    "youtube_quiz",
    "template_execution",
)


def clear_history(
    *,
    db: Session,
    user_id: str,
    source_types: list[str] | None,
    search: str | None,
    date_from: datetime | None,
    date_to: datetime | None,
    keep_pinned: bool,
) -> int:
    """Hard-delete rows matching the same filters as list_history (minus pagination)."""
    if source_types:
        types = tuple(t for t in source_types if t in SOURCE_TYPES_ALL)
        if not types:
            return 0
    else:
        types = SOURCE_TYPES_ALL

    q_like = f"%{search.lower()}%" if search else None
    total = 0

    def pin_sql(table_ref: str, pk_col: str, st_key: str) -> str:
        if not keep_pinned:
            return ""
        return f"""
          AND NOT EXISTS (
            SELECT 1 FROM user_content_pins p
            WHERE p.user_id = CAST(:uid AS uuid)
              AND p.source_type = '{st_key}'
              AND p.source_id = {table_ref}.{pk_col}
          )
        """

    def date_clause_for(alias: str) -> str:
        parts = []
        if date_from:
            parts.append(f" AND {alias}.created_at >= :date_from")
        if date_to:
            parts.append(f" AND {alias}.created_at <= :date_to")
        return "".join(parts)

    def search_clause(title_sql: str) -> str:
        if q_like is None:
            return ""
        return f" AND ({title_sql}) ILIKE :q_like"

    for st in types:
        params: dict = {"uid": user_id}
        if date_from:
            params["date_from"] = date_from
        if date_to:
            params["date_to"] = date_to
        if q_like is not None:
            params["q_like"] = q_like

        if st == "quiz":
            dc = date_clause_for("q")
            sql = f"""
              DELETE FROM teacher_quizzes q
              WHERE q.owner_user_id = CAST(:uid AS uuid)
              {dc}
              {search_clause('q.title')}
              {pin_sql('q', 'id', 'quiz')}
            """
        elif st == "assignment":
            dc = date_clause_for("a")
            sql = f"""
              DELETE FROM teacher_assignments a
              WHERE a.owner_user_id = CAST(:uid AS uuid)
              {dc}
              {search_clause('a.title')}
              {pin_sql('a', 'id', 'assignment')}
            """
        elif st == "worksheet":
            dc = date_clause_for("w")
            sql = f"""
              DELETE FROM teacher_worksheets w
              WHERE w.owner_user_id = CAST(:uid AS uuid)
              {dc}
              {search_clause('w.title')}
              {pin_sql('w', 'id', 'worksheet')}
            """
        elif st == "exam":
            dc = date_clause_for("e")
            sql = f"""
              DELETE FROM teacher_exams e
              WHERE e.owner_user_id = CAST(:uid AS uuid)
              {dc}
              {search_clause('e.title')}
              {pin_sql('e', 'id', 'exam')}
            """
        elif st == "chatbot_conversation":
            dc = date_clause_for("c")
            sql = f"""
              DELETE FROM chatbot_conversations c
              USING chatbots b
              WHERE c.chatbot_id = b.id
                AND b.exclude_from_history = FALSE
                AND c.user_id = CAST(:uid AS uuid)
              {dc}
              {search_clause("COALESCE(c.title, 'Conversation')")}
              {pin_sql('c', 'id', 'chatbot_conversation')}
            """
        elif st == "pixgen_generation":
            dc = date_clause_for("p")
            sql = f"""
              DELETE FROM pixgen_generations p
              WHERE p.user_id = CAST(:uid AS uuid)
              {dc}
              {search_clause('p.prompt')}
              {pin_sql('p', 'id', 'pixgen_generation')}
            """
        elif st == "youtube_quiz":
            dc = date_clause_for("y")
            sql = f"""
              DELETE FROM youtube_quiz_generations y
              WHERE y.user_id = CAST(:uid AS uuid)
              {dc}
              {search_clause('y.title')}
              {pin_sql('y', 'id', 'youtube_quiz')}
            """
        elif st == "template_execution":
            dc = date_clause_for("te")
            join_search = ""
            if q_like:
                join_search = " AND t.name ILIKE :q_like "
            pin_part = ""
            if keep_pinned:
                pin_part = """
                  AND NOT EXISTS (
                    SELECT 1 FROM user_content_pins p
                    WHERE p.user_id = CAST(:uid AS uuid)
                      AND p.source_type = 'template_execution'
                      AND p.source_id = te.id
                  )
                """
            sql = f"""
              DELETE FROM template_executions te
              USING templates t
              WHERE te.template_id = t.id
                AND te.user_id = CAST(:uid AS uuid)
                {dc}
                {join_search}
                {pin_part}
            """
        else:
            continue

        result = db.execute(text(sql), params)
        total += result.rowcount or 0

    db.commit()
    return total


def list_history(
    *,
    db: Session,
    user_id: str,
    source_types: list[str] | None,
    search: str | None,
    date_from: datetime | None,
    date_to: datetime | None,
    pinned_only: bool,
    page: int,
    page_size: int,
) -> tuple[int, list[dict]]:
    offset = (page - 1) * page_size

    cte_sql = """
    WITH all_items AS (
      -- Teacher tools
      SELECT
        q.id::text AS id,
        'quiz'::text AS source_type,
        q.title AS title,
        q.subject AS subject,
        q.grade AS grade,
        q.status AS status,
        false AS pinned_default,
        q.created_at AS created_at,
        q.updated_at AS updated_at,
        0::int AS usage_count,
        NULL::timestamptz AS last_used_at,
        '{}'::jsonb AS meta
      FROM teacher_quizzes q
      WHERE q.owner_user_id = CAST(:uid AS uuid)

      UNION ALL
      SELECT
        a.id::text AS id,
        'assignment'::text AS source_type,
        a.title AS title,
        a.subject AS subject,
        a.grade AS grade,
        a.status AS status,
        false AS pinned_default,
        a.created_at AS created_at,
        a.updated_at AS updated_at,
        0::int AS usage_count,
        NULL::timestamptz AS last_used_at,
        '{}'::jsonb AS meta
      FROM teacher_assignments a
      WHERE a.owner_user_id = CAST(:uid AS uuid)

      UNION ALL
      SELECT
        w.id::text AS id,
        'worksheet'::text AS source_type,
        w.title AS title,
        w.subject AS subject,
        w.grade AS grade,
        w.status AS status,
        false AS pinned_default,
        w.created_at AS created_at,
        w.updated_at AS updated_at,
        0::int AS usage_count,
        NULL::timestamptz AS last_used_at,
        '{}'::jsonb AS meta
      FROM teacher_worksheets w
      WHERE w.owner_user_id = CAST(:uid AS uuid)

      UNION ALL
      SELECT
        e.id::text AS id,
        'exam'::text AS source_type,
        e.title AS title,
        e.subject AS subject,
        e.grade AS grade,
        e.status AS status,
        false AS pinned_default,
        e.created_at AS created_at,
        e.updated_at AS updated_at,
        0::int AS usage_count,
        NULL::timestamptz AS last_used_at,
        '{}'::jsonb AS meta
      FROM teacher_exams e
      WHERE e.owner_user_id = CAST(:uid AS uuid)

      -- Chatbots
      UNION ALL
      SELECT
        c.id::text AS id,
        'chatbot_conversation'::text AS source_type,
        COALESCE(c.title, 'Conversation') AS title,
        NULL::text AS subject,
        NULL::text AS grade,
        NULL::text AS status,
        false AS pinned_default,
        c.created_at AS created_at,
        c.updated_at AS updated_at,
        0::int AS usage_count,
        NULL::timestamptz AS last_used_at,
        jsonb_build_object(
          'chatbot_slug', b.slug,
          'chatbot_name', b.name,
          'message_count', COALESCE(
            (SELECT COUNT(*)::int FROM chatbot_messages m WHERE m.conversation_id = c.id),
            0
          )
        ) AS meta
      FROM chatbot_conversations c
      JOIN chatbots b ON b.id = c.chatbot_id
      WHERE c.user_id = CAST(:uid AS uuid)
        AND b.exclude_from_history = FALSE

      -- PixGen
      UNION ALL
      SELECT
        p.id::text AS id,
        'pixgen_generation'::text AS source_type,
        p.prompt AS title,
        NULL::text AS subject,
        NULL::text AS grade,
        p.status AS status,
        false AS pinned_default,
        p.created_at AS created_at,
        p.updated_at AS updated_at,
        0::int AS usage_count,
        NULL::timestamptz AS last_used_at,
        jsonb_build_object(
          'prompt', p.prompt,
          'image_urls',
            CASE
              WHEN p.image_url IS NOT NULL AND length(trim(p.image_url)) > 0
              THEN jsonb_build_array(p.image_url)
              ELSE '[]'::jsonb
            END,
          'image_url', p.image_url,
          'style_preset', p.style_preset,
          'aspect_ratio', p.aspect_ratio
        ) AS meta
      FROM pixgen_generations p
      WHERE p.user_id = CAST(:uid AS uuid)

      -- YouTube quiz
      UNION ALL
      SELECT
        y.id::text AS id,
        'youtube_quiz'::text AS source_type,
        y.title AS title,
        y.subject_lens AS subject,
        y.grade_band AS grade,
        NULL::text AS status,
        false AS pinned_default,
        y.created_at AS created_at,
        y.updated_at AS updated_at,
        COALESCE(y.usage_count, 0)::int AS usage_count,
        y.last_used_at AS last_used_at,
        jsonb_build_object(
          'video_url', y.video_url,
          'result_json', y.result_json
        ) AS meta
      FROM youtube_quiz_generations y
      WHERE y.user_id = CAST(:uid AS uuid)

      -- Templates (executions)
      UNION ALL
      SELECT
        te.id::text AS id,
        'template_execution'::text AS source_type,
        t.name AS title,
        t.subject_default AS subject,
        NULL::text AS grade,
        NULL::text AS status,
        false AS pinned_default,
        te.created_at AS created_at,
        te.updated_at AS updated_at,
        0::int AS usage_count,
        NULL::timestamptz AS last_used_at,
        jsonb_build_object(
          'template_slug', t.slug,
          'template_name', t.name,
          'template_category', t.category
        ) AS meta
      FROM template_executions te
      JOIN templates t ON t.id = te.template_id
      WHERE te.user_id = CAST(:uid AS uuid)
    ),
    annotated AS (
      SELECT
        i.*,
        (p.id IS NOT NULL) AS pinned,
        f.hint AS performance_hint
      FROM all_items i
      LEFT JOIN user_content_pins p
        ON p.user_id = CAST(:uid AS uuid)
       AND p.source_type = i.source_type
       AND p.source_id::text = i.id
      LEFT JOIN user_content_feedback f
        ON f.user_id = CAST(:uid AS uuid)
       AND f.source_type = i.source_type
       AND f.source_id::text = i.id
    )
    """

    filters = []
    params: dict = {"uid": user_id, "limit": page_size, "offset": offset}

    if source_types:
        filters.append("AND source_type = ANY(:source_types)")
        params["source_types"] = source_types

    if search:
        filters.append("AND title ILIKE :q")
        params["q"] = f"%{search}%"

    if date_from:
        filters.append("AND created_at >= :date_from")
        params["date_from"] = date_from

    if date_to:
        filters.append("AND created_at <= :date_to")
        params["date_to"] = date_to

    if pinned_only:
        filters.append("AND pinned = true")

    list_sql = text(
        "\n".join(
            [
                cte_sql,
                "SELECT * FROM annotated WHERE 1=1",
                *filters,
                "ORDER BY pinned DESC, updated_at DESC",
                "LIMIT :limit OFFSET :offset",
            ]
        )
    )
    rows = db.execute(list_sql, params).mappings().all()

    count_sql = text(
        "\n".join(
            [
                cte_sql,
                "SELECT COUNT(*) AS cnt FROM annotated WHERE 1=1",
                *filters,
            ]
        )
    )
    total = int(db.execute(count_sql, params).scalar() or 0)

    items = []
    for r in rows:
        items.append(
            {
                "id": r["id"],
                "source_type": r["source_type"],
                "title": r["title"],
                "subject": r["subject"],
                "grade": r["grade"],
                "status": r["status"],
                "pinned": bool(r["pinned"]),
                "performance_hint": r["performance_hint"],
                "usage_count": int(r["usage_count"] or 0),
                "last_used_at": r["last_used_at"].isoformat() if r["last_used_at"] else None,
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
                "meta": r["meta"] or {},
            }
        )

    return total, items


def get_stats(db: Session, user_id: str) -> dict:
    since = datetime.now(timezone.utc) - timedelta(days=7)
    sql = text(
        """
        WITH all_items AS (
          SELECT id::text AS id, 'quiz'::text AS source_type, created_at FROM teacher_quizzes WHERE owner_user_id = CAST(:uid AS uuid)
          UNION ALL SELECT id::text, 'assignment', created_at FROM teacher_assignments WHERE owner_user_id = CAST(:uid AS uuid)
          UNION ALL SELECT id::text, 'worksheet', created_at FROM teacher_worksheets WHERE owner_user_id = CAST(:uid AS uuid)
          UNION ALL SELECT id::text, 'exam', created_at FROM teacher_exams WHERE owner_user_id = CAST(:uid AS uuid)
          UNION ALL SELECT c.id::text, 'chatbot_conversation', c.created_at
          FROM chatbot_conversations c
          JOIN chatbots b ON b.id = c.chatbot_id
          WHERE c.user_id = CAST(:uid AS uuid) AND b.exclude_from_history = FALSE
          UNION ALL SELECT id::text, 'pixgen_generation', created_at FROM pixgen_generations WHERE user_id = CAST(:uid AS uuid)
          UNION ALL SELECT id::text, 'youtube_quiz', created_at FROM youtube_quiz_generations WHERE user_id = CAST(:uid AS uuid)
          UNION ALL SELECT id::text, 'template_execution', created_at FROM template_executions WHERE user_id = CAST(:uid AS uuid)
        ),
        pinned AS (
          SELECT COUNT(*)::int AS cnt
          FROM user_content_pins
          WHERE user_id = CAST(:uid AS uuid)
        ),
        by_type AS (
          SELECT source_type, COUNT(*)::int AS cnt
          FROM all_items
          GROUP BY source_type
        )
        SELECT
          (SELECT COUNT(*)::int FROM all_items) AS total,
          (SELECT COUNT(*)::int FROM all_items WHERE created_at >= :since) AS this_week,
          (SELECT cnt FROM pinned) AS pinned,
          (SELECT jsonb_object_agg(source_type, cnt) FROM by_type) AS by_source_type
        """
    )
    row = db.execute(sql, {"uid": user_id, "since": since}).mappings().first()
    return {
        "total": int(row["total"] or 0),
        "this_week": int(row["this_week"] or 0),
        "pinned": int(row["pinned"] or 0),
        "by_source_type": dict(row["by_source_type"] or {}),
    }


def toggle_pin(db: Session, user_id: str, source_type: str, source_id: str, pinned: bool) -> None:
    import uuid
    from datetime import datetime, timezone

    from app.domains.user_history.models import UserContentPin

    uid = uuid.UUID(user_id)
    sid = uuid.UUID(source_id)

    existing = (
        db.query(UserContentPin)
        .filter(
            UserContentPin.user_id == uid,
            UserContentPin.source_type == source_type,
            UserContentPin.source_id == sid,
        )
        .first()
    )
    if pinned:
        if not existing:
            db.add(
                UserContentPin(
                    user_id=uid,
                    source_type=source_type,
                    source_id=sid,
                    created_at=datetime.now(timezone.utc),
                )
            )
            db.commit()
    else:
        if existing:
            db.delete(existing)
            db.commit()


def upsert_feedback(db: Session, user_id: str, source_type: str, source_id: str, hint: str, note: str | None) -> None:
    import uuid
    from datetime import datetime, timezone

    from app.domains.user_history.models import UserContentFeedback

    uid = uuid.UUID(user_id)
    sid = uuid.UUID(source_id)
    now = datetime.now(timezone.utc)

    existing = (
        db.query(UserContentFeedback)
        .filter(
            UserContentFeedback.user_id == uid,
            UserContentFeedback.source_type == source_type,
            UserContentFeedback.source_id == sid,
        )
        .first()
    )
    if existing:
        existing.hint = hint
        existing.note = note
        existing.updated_at = now
    else:
        db.add(
            UserContentFeedback(
                user_id=uid,
                source_type=source_type,
                source_id=sid,
                hint=hint,
                note=note,
                created_at=now,
                updated_at=now,
            )
        )
    db.commit()

