from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

from sqlalchemy import String, cast, desc, func, or_
from sqlalchemy.orm import Session, joinedload

from app.domains.teacher_worksheet.models import (
    TeacherWorksheet,
    TeacherWorksheetBlock,
    TeacherWorksheetGenerationRun,
    TeacherWorksheetSession,
)


@dataclass(frozen=True)
class WorksheetListFilters:
    q: str | None = None
    subject: str | None = None
    grade: str | None = None
    status: str | None = None
    class_key: str | None = None
    date_from: str | None = None
    date_to: str | None = None


class TeacherWorksheetRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_worksheets(
        self,
        tenant_id: UUID,
        filters: WorksheetListFilters,
        page: int = 1,
        page_size: int = 50,
    ) -> Tuple[List[TeacherWorksheet], int]:
        q = self.db.query(TeacherWorksheet).filter(TeacherWorksheet.tenant_id == tenant_id)

        if filters.q:
            term = f"%{filters.q.lower()}%"
            q = q.filter(func.lower(TeacherWorksheet.title).ilike(term))
        if filters.subject:
            q = q.filter(TeacherWorksheet.subject == filters.subject)
        if filters.grade:
            q = q.filter(TeacherWorksheet.grade == filters.grade)
        if filters.status:
            q = q.filter(TeacherWorksheet.status == filters.status)
        if filters.class_key:
            bind = self.db.get_bind()
            dialect = bind.dialect.name if bind is not None else ""
            if dialect == "postgresql":
                q = q.filter(TeacherWorksheet.class_keys.contains([filters.class_key]))  # type: ignore[attr-defined]
            else:
                q = q.filter(cast(TeacherWorksheet.class_keys, String).ilike(f"%{filters.class_key}%"))

        bind = self.db.get_bind()
        dialect = bind.dialect.name if bind is not None else ""
        if dialect == "postgresql":
            if filters.date_from:
                q = q.filter(
                    or_(
                        TeacherWorksheet.assigned_at.is_(None),
                        func.to_char(TeacherWorksheet.assigned_at, "YYYY-MM-DD") >= filters.date_from,
                    )
                )
            if filters.date_to:
                q = q.filter(
                    or_(
                        TeacherWorksheet.assigned_at.is_(None),
                        func.to_char(TeacherWorksheet.assigned_at, "YYYY-MM-DD") <= filters.date_to,
                    )
                )

        q = q.order_by(desc(TeacherWorksheet.updated_at), desc(TeacherWorksheet.created_at))
        total = q.count()
        offset = (page - 1) * page_size
        items = (
            q.options(
                joinedload(TeacherWorksheet.sessions).joinedload(TeacherWorksheetSession.blocks),
            )
            .offset(offset)
            .limit(page_size)
            .all()
        )
        return items, total

    def get_worksheet(
        self,
        tenant_id: UUID,
        worksheet_id: UUID,
        *,
        with_children: bool = True,
    ) -> Optional[TeacherWorksheet]:
        query = self.db.query(TeacherWorksheet).filter(
            TeacherWorksheet.tenant_id == tenant_id,
            TeacherWorksheet.id == worksheet_id,
        )
        if with_children:
            query = query.options(
                joinedload(TeacherWorksheet.sessions).joinedload(TeacherWorksheetSession.blocks),
            )
        return query.first()

    def get_session(
        self,
        tenant_id: UUID,
        worksheet_id: UUID,
        session_id: UUID,
    ) -> Optional[TeacherWorksheetSession]:
        return (
            self.db.query(TeacherWorksheetSession)
            .join(TeacherWorksheet, TeacherWorksheetSession.worksheet_id == TeacherWorksheet.id)
            .filter(
                TeacherWorksheet.tenant_id == tenant_id,
                TeacherWorksheet.id == worksheet_id,
                TeacherWorksheetSession.id == session_id,
            )
            .options(joinedload(TeacherWorksheetSession.blocks))
            .first()
        )

    def get_block(
        self,
        tenant_id: UUID,
        worksheet_id: UUID,
        session_id: UUID,
        block_id: UUID,
    ) -> Optional[TeacherWorksheetBlock]:
        return (
            self.db.query(TeacherWorksheetBlock)
            .join(TeacherWorksheetSession, TeacherWorksheetBlock.session_id == TeacherWorksheetSession.id)
            .join(TeacherWorksheet, TeacherWorksheetSession.worksheet_id == TeacherWorksheet.id)
            .filter(
                TeacherWorksheet.tenant_id == tenant_id,
                TeacherWorksheet.id == worksheet_id,
                TeacherWorksheetSession.id == session_id,
                TeacherWorksheetBlock.id == block_id,
            )
            .first()
        )

    def create_worksheet(self, ws: TeacherWorksheet) -> TeacherWorksheet:
        self.db.add(ws)
        self.db.commit()
        self.db.refresh(ws)
        return self.get_worksheet(ws.tenant_id, ws.id) or ws

    def update_worksheet(self, ws: TeacherWorksheet) -> TeacherWorksheet:
        self.db.add(ws)
        self.db.commit()
        self.db.refresh(ws)
        return self.get_worksheet(ws.tenant_id, ws.id) or ws

    def delete_worksheet(self, ws: TeacherWorksheet) -> None:
        self.db.delete(ws)
        self.db.commit()

    def find_generation_run_by_idempotency(
        self,
        worksheet_id: UUID,
        idempotency_key: str,
    ) -> Optional[TeacherWorksheetGenerationRun]:
        return (
            self.db.query(TeacherWorksheetGenerationRun)
            .filter(
                TeacherWorksheetGenerationRun.worksheet_id == worksheet_id,
                TeacherWorksheetGenerationRun.idempotency_key == idempotency_key,
            )
            .order_by(desc(TeacherWorksheetGenerationRun.created_at))
            .first()
        )

    def create_generation_run(self, run: TeacherWorksheetGenerationRun) -> TeacherWorksheetGenerationRun:
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    def delete_blocks_for_session(self, session_id: UUID) -> None:
        self.db.query(TeacherWorksheetBlock).filter(TeacherWorksheetBlock.session_id == session_id).delete(
            synchronize_session=False
        )
        self.db.flush()

    def duplicate_worksheet(self, *, source: TeacherWorksheet, new_id: UUID, new_title: str, now: datetime) -> TeacherWorksheet:
        copy = TeacherWorksheet(
            id=new_id,
            tenant_id=source.tenant_id,
            owner_user_id=source.owner_user_id,
            title=new_title,
            subject=source.subject,
            grade=source.grade,
            output_format=source.output_format,
            class_keys=list(source.class_keys or []),
            student_instructions=source.student_instructions,
            teacher_notes=source.teacher_notes,
            status="draft" if source.status == "archived" else "draft",
            assigned_at=None,
            due_at=None,
            source_pack_ids=list(source.source_pack_ids or []),
            scope_topics=list(source.scope_topics or []),
            scope_refinement=source.scope_refinement,
            topic_summary=source.topic_summary,
            generate_without_sources=bool(source.generate_without_sources),
            difficulty=source.difficulty,
            handout_layout=source.handout_layout,
            sessions_count=0,
            blocks_count=0,
            submission_count=0,
            avg_score=0.0,
            content_version=1,
            created_at=now,
            updated_at=now,
        )
        self.db.add(copy)
        self.db.flush()

        for s in sorted(source.sessions or [], key=lambda x: x.sort_order):
            ns = TeacherWorksheetSession(
                id=uuid4(),
                worksheet_id=copy.id,
                sort_order=s.sort_order,
                title=s.title,
                created_at=now,
            )
            self.db.add(ns)
            self.db.flush()
            for b in sorted(s.blocks or [], key=lambda x: x.sort_order):
                nb = TeacherWorksheetBlock(
                    id=uuid4(),
                    worksheet_id=copy.id,
                    session_id=ns.id,
                    sort_order=b.sort_order,
                    type=b.type,
                    prompt=b.prompt,
                    points=b.points,
                    data=dict(b.data or {}),
                )
                self.db.add(nb)

        self.db.commit()
        self._update_denorm_counts(copy.tenant_id, copy.id)
        return self.get_worksheet(copy.tenant_id, copy.id) or copy

    def _update_denorm_counts(self, tenant_id: UUID, worksheet_id: UUID) -> None:
        ws = (
            self.db.query(TeacherWorksheet)
            .filter(TeacherWorksheet.tenant_id == tenant_id, TeacherWorksheet.id == worksheet_id)
            .first()
        )
        if not ws:
            return
        s_count = (
            self.db.query(func.count(TeacherWorksheetSession.id))
            .filter(TeacherWorksheetSession.worksheet_id == worksheet_id)
            .scalar()
            or 0
        )
        b_count = (
            self.db.query(func.count(TeacherWorksheetBlock.id))
            .filter(TeacherWorksheetBlock.worksheet_id == worksheet_id)
            .scalar()
            or 0
        )
        ws.sessions_count = int(s_count)
        ws.blocks_count = int(b_count)
        ws.updated_at = datetime.now(timezone.utc)
        self.db.add(ws)
        self.db.commit()

    def add_session(self, ws: TeacherWorksheet, title: str) -> TeacherWorksheet:
        orders = (
            self.db.query(TeacherWorksheetSession.sort_order)
            .filter(TeacherWorksheetSession.worksheet_id == ws.id)
            .all()
        )
        order_vals = [int(o[0]) for o in orders] if orders else []
        next_order = (max(order_vals) + 1) if order_vals else 0
        sess = TeacherWorksheetSession(
            id=uuid4(),
            worksheet_id=ws.id,
            sort_order=next_order,
            title=title or "New Session",
        )
        self.db.add(sess)
        self.db.commit()
        self._update_denorm_counts(ws.tenant_id, ws.id)
        return self.get_worksheet(ws.tenant_id, ws.id) or ws

    def patch_session(self, ws: TeacherWorksheet, session: TeacherWorksheetSession, patch: Dict[str, Any]) -> TeacherWorksheet:
        if "title" in patch and patch["title"] is not None:
            session.title = patch["title"]
        if "sort_order" in patch and patch["sort_order"] is not None:
            session.sort_order = int(patch["sort_order"])
        self.db.add(session)
        self.db.commit()
        self._update_denorm_counts(ws.tenant_id, ws.id)
        return self.get_worksheet(ws.tenant_id, ws.id) or ws

    def delete_session(self, ws: TeacherWorksheet, session: TeacherWorksheetSession) -> TeacherWorksheet:
        self.db.delete(session)
        self.db.commit()
        self._update_denorm_counts(ws.tenant_id, ws.id)
        return self.get_worksheet(ws.tenant_id, ws.id) or ws

    def reorder_sessions(self, ws: TeacherWorksheet, order: List[Dict[str, Any]]) -> TeacherWorksheet:
        id_map = {str(item["id"]): int(item["sort_order"]) for item in order}
        for s in ws.sessions or []:
            sid = str(s.id)
            if sid in id_map:
                s.sort_order = id_map[sid]
                self.db.add(s)
        self.db.commit()
        self._update_denorm_counts(ws.tenant_id, ws.id)
        return self.get_worksheet(ws.tenant_id, ws.id) or ws

    def add_block(self, ws: TeacherWorksheet, session: TeacherWorksheetSession, block: TeacherWorksheetBlock) -> TeacherWorksheet:
        orders = (
            self.db.query(TeacherWorksheetBlock.sort_order)
            .filter(TeacherWorksheetBlock.session_id == session.id)
            .all()
        )
        order_vals = [int(o[0]) for o in orders] if orders else []
        block.sort_order = (max(order_vals) + 1) if order_vals else 0
        block.worksheet_id = ws.id
        block.session_id = session.id
        self.db.add(block)
        self.db.commit()
        self._update_denorm_counts(ws.tenant_id, ws.id)
        return self.get_worksheet(ws.tenant_id, ws.id) or ws

    def patch_block(self, ws: TeacherWorksheet, block: TeacherWorksheetBlock, data_patch: Dict[str, Any]) -> TeacherWorksheet:
        if "prompt" in data_patch:
            block.prompt = data_patch["prompt"]
        if "points" in data_patch and data_patch["points"] is not None:
            block.points = float(data_patch["points"])
        if "data" in data_patch:
            block.data = data_patch["data"]
        self.db.add(block)
        self.db.commit()
        self._update_denorm_counts(ws.tenant_id, ws.id)
        return self.get_worksheet(ws.tenant_id, ws.id) or ws

    def delete_block(self, ws: TeacherWorksheet, block: TeacherWorksheetBlock) -> TeacherWorksheet:
        self.db.delete(block)
        self.db.commit()
        self._update_denorm_counts(ws.tenant_id, ws.id)
        return self.get_worksheet(ws.tenant_id, ws.id) or ws

    def reorder_blocks(self, ws: TeacherWorksheet, session: TeacherWorksheetSession, order: List[Dict[str, Any]]) -> TeacherWorksheet:
        id_map = {str(item["id"]): int(item["sort_order"]) for item in order}
        for b in session.blocks or []:
            bid = str(b.id)
            if bid in id_map:
                b.sort_order = id_map[bid]
                self.db.add(b)
        self.db.commit()
        self._update_denorm_counts(ws.tenant_id, ws.id)
        return self.get_worksheet(ws.tenant_id, ws.id) or ws

    def replace_session_blocks(
        self,
        ws: TeacherWorksheet,
        session: TeacherWorksheetSession,
        blocks: List[TeacherWorksheetBlock],
    ) -> TeacherWorksheet:
        self.delete_blocks_for_session(session.id)
        for i, b in enumerate(blocks):
            b.id = uuid4()
            b.worksheet_id = ws.id
            b.session_id = session.id
            b.sort_order = i
            self.db.add(b)
        self.db.commit()
        self._update_denorm_counts(ws.tenant_id, ws.id)
        return self.get_worksheet(ws.tenant_id, ws.id) or ws
