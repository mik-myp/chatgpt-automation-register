from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from gpt_auto_register.db.models.kakao import KakaoTask, KakaoTaskStatus


class KakaoTaskRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_page(
        self,
        *,
        pipeline_run_id: str | None,
        status: KakaoTaskStatus | None,
        payment_status: str,
        search: str,
        limit: int,
        offset: int,
    ) -> tuple[list[KakaoTask], int]:
        filters: list[ColumnElement[bool]] = []
        if pipeline_run_id:
            filters.append(KakaoTask.pipeline_run_id == pipeline_run_id)
        if status is not None:
            filters.append(KakaoTask.status == status)
        if payment_status:
            filters.append(func.lower(KakaoTask.payment_status) == payment_status.lower())
        if search:
            needle = f"%{search.strip().lower()}%"
            filters.append(
                or_(
                    func.lower(KakaoTask.email).like(needle),
                    func.lower(KakaoTask.upstream_job_id).like(needle),
                    func.lower(KakaoTask.error).like(needle),
                )
            )

        total = (
            self.session.scalar(select(func.count()).select_from(KakaoTask).where(*filters)) or 0
        )
        items = list(
            self.session.scalars(
                select(KakaoTask)
                .where(*filters)
                .order_by(KakaoTask.created_at.desc(), KakaoTask.id.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        return items, total

    def get(self, task_id: str) -> KakaoTask | None:
        return self.session.get(KakaoTask, task_id)

    def selected(
        self,
        task_ids: list[str],
        pipeline_run_id: str | None,
    ) -> list[KakaoTask]:
        filters: list[ColumnElement[bool]] = []
        if task_ids:
            filters.append(KakaoTask.id.in_(task_ids))
        if pipeline_run_id:
            filters.append(KakaoTask.pipeline_run_id == pipeline_run_id)
        if not filters:
            return []
        return list(self.session.scalars(select(KakaoTask).where(*filters)))
