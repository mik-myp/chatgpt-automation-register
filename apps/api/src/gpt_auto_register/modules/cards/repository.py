from dataclasses import dataclass

from sqlalchemy import delete, distinct, exists, false, func, select, update
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from gpt_auto_register.core.encryption import secret_fingerprint
from gpt_auto_register.db.models.kakao import (
    KakaoCard,
    KakaoCardBatch,
    PipelineCardAllocation,
)
from gpt_auto_register.db.models.pipeline import PipelineRun, PipelineStatus
from gpt_auto_register.db.models.settings import AppSetting
from gpt_auto_register.db.result import affected_rows


@dataclass(frozen=True, slots=True)
class CardInventoryRow:
    card: KakaoCard
    run_count: int
    allocated_count: int
    created_count: int
    duplicate_count: int
    failed_count: int


class CardRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_page(
        self,
        *,
        active: bool | None,
        search: str,
        limit: int,
        offset: int,
    ) -> tuple[list[CardInventoryRow], int]:
        filters: list[ColumnElement[bool]] = []
        if active is not None:
            filters.append(KakaoCard.active.is_(active))
        if search:
            needle = search.strip().lower()
            matching_ids = [
                card.id
                for card in self.session.scalars(select(KakaoCard))
                if needle in card.code.lower()
            ]
            filters.append(KakaoCard.id.in_(matching_ids) if matching_ids else false())

        total = (
            self.session.scalar(select(func.count()).select_from(KakaoCard).where(*filters)) or 0
        )
        rows = self.session.execute(
            select(
                KakaoCard,
                func.count(distinct(PipelineCardAllocation.pipeline_run_id)),
                func.coalesce(func.sum(PipelineCardAllocation.allocated_count), 0),
                func.coalesce(func.sum(PipelineCardAllocation.created_count), 0),
                func.coalesce(func.sum(PipelineCardAllocation.duplicate_count), 0),
                func.coalesce(func.sum(PipelineCardAllocation.failed_count), 0),
            )
            .outerjoin(PipelineCardAllocation)
            .where(*filters)
            .group_by(KakaoCard.id)
            .order_by(KakaoCard.created_at.desc(), KakaoCard.position)
            .limit(limit)
            .offset(offset)
        )
        return (
            [
                CardInventoryRow(
                    card=card,
                    run_count=run_count,
                    allocated_count=allocated,
                    created_count=created,
                    duplicate_count=duplicate,
                    failed_count=failed,
                )
                for card, run_count, allocated, created, duplicate, failed in rows
            ],
            total,
        )

    def stats(self) -> tuple[int, int]:
        total = self.session.scalar(select(func.count()).select_from(KakaoCard)) or 0
        active = (
            self.session.scalar(
                select(func.count()).select_from(KakaoCard).where(KakaoCard.active.is_(True))
            )
            or 0
        )
        return total, active

    def active_cards(self) -> list[KakaoCard]:
        return list(
            self.session.scalars(
                select(KakaoCard)
                .where(KakaoCard.active.is_(True))
                .order_by(KakaoCard.created_at, KakaoCard.position, KakaoCard.id)
            )
        )

    def all_cards(self) -> list[KakaoCard]:
        return list(
            self.session.scalars(
                select(KakaoCard).order_by(
                    KakaoCard.created_at,
                    KakaoCard.position,
                    KakaoCard.id,
                )
            )
        )

    def import_cards(self, codes: list[str], batch_name: str) -> tuple[str | None, int, int]:
        inserted = duplicates = 0
        batch: KakaoCardBatch | None = None
        existing: set[str] = set()
        for start in range(0, len(codes), 500):
            existing.update(
                self.session.scalars(
                    select(KakaoCard.code_fingerprint).where(
                        KakaoCard.code_fingerprint.in_(
                            [secret_fingerprint(code) for code in codes[start : start + 500]]
                        )
                    )
                )
            )
        for code in codes:
            fingerprint = secret_fingerprint(code)
            if fingerprint in existing:
                duplicates += 1
                continue
            if batch is None:
                name = batch_name.strip() or f"卡密批次 {self._next_batch_number()}"
                batch = KakaoCardBatch(name=name)
                self.session.add(batch)
                self.session.flush()
            self.session.add(
                KakaoCard(batch_id=batch.id, code=code, position=inserted, active=True)
            )
            existing.add(fingerprint)
            inserted += 1
        self.session.flush()
        return (batch.id if batch else None), inserted, duplicates

    def set_active(self, card_ids: list[str], active: bool) -> int:
        processed = 0
        for start in range(0, len(card_ids), 500):
            result = self.session.execute(
                update(KakaoCard)
                .where(
                    KakaoCard.id.in_(card_ids[start : start + 500]),
                    KakaoCard.active.is_not(active),
                )
                .values(active=active)
            )
            processed += affected_rows(result)
        return processed

    def delete_cards(self, card_ids: list[str]) -> int:
        active_runs = select(PipelineRun.id).where(
            PipelineRun.status.in_(
                [
                    PipelineStatus.QUEUED,
                    PipelineStatus.RUNNING,
                    PipelineStatus.PAUSED,
                ]
            )
        )
        deleted_ids = list(
            self.session.scalars(
                select(KakaoCard.id).where(
                    KakaoCard.id.in_(card_ids),
                    ~exists().where(
                        PipelineCardAllocation.card_id == KakaoCard.id,
                        PipelineCardAllocation.pipeline_run_id.in_(active_runs),
                    ),
                )
            )
        )
        if deleted_ids:
            self.session.execute(
                delete(PipelineCardAllocation).where(
                    PipelineCardAllocation.card_id.in_(deleted_ids)
                )
            )
            self.session.execute(delete(KakaoCard).where(KakaoCard.id.in_(deleted_ids)))
        self.session.execute(
            delete(KakaoCardBatch).where(~exists().where(KakaoCard.batch_id == KakaoCardBatch.id))
        )
        cache = self.usage_cache()
        if any(card_id in cache for card_id in deleted_ids):
            self.save_usage_cache(
                {card_id: value for card_id, value in cache.items() if card_id not in deleted_ids}
            )
        return len(deleted_ids)

    def usage_cache(self) -> dict[str, dict[str, object]]:
        row = self.session.get(AppSetting, "card_usage_cache")
        if row is None or not isinstance(row.value, dict):
            return {}
        return {
            str(card_id): dict(value)
            for card_id, value in row.value.items()
            if isinstance(value, dict)
        }

    def save_usage_cache(self, value: dict[str, dict[str, object]]) -> None:
        row = self.session.get(AppSetting, "card_usage_cache")
        if row is None:
            self.session.add(AppSetting(key="card_usage_cache", value=value, sensitive=False))
        else:
            row.value = value

    def _next_batch_number(self) -> int:
        return (self.session.scalar(select(func.count()).select_from(KakaoCardBatch)) or 0) + 1
