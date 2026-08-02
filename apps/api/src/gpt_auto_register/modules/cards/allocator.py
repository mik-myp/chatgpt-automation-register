import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from gpt_auto_register.db.base import utc_now
from gpt_auto_register.db.models.kakao import KakaoCard, PipelineCardAllocation
from gpt_auto_register.db.models.pipeline import PipelineRun, PipelineStatus
from gpt_auto_register.modules.cards.repository import CardRepository
from gpt_auto_register.modules.kakao.client import KakaoClient
from gpt_auto_register.modules.settings.service import SettingsService


class CardAllocationError(RuntimeError):
    pass


_CARD_ALLOCATION_LOCK = threading.RLock()


@contextmanager
def card_allocation_guard() -> Iterator[None]:
    with _CARD_ALLOCATION_LOCK:
        yield


@dataclass(frozen=True, slots=True)
class CardUsage:
    card_id: str
    code: str
    charged: int
    pending: int
    remaining: int
    error: str | None = None


class CardAllocator:
    CACHE_TTL_SECONDS = 30

    def __init__(self, session: Session) -> None:
        self.session = session

    def usage(self, *, force_refresh: bool = False) -> list[CardUsage]:
        return self._usage(
            CardRepository(self.session).active_cards(),
            force_refresh=force_refresh,
        )

    def inventory_usage(self) -> list[CardUsage]:
        return self._usage(CardRepository(self.session).all_cards(), force_refresh=True)

    def _usage(
        self,
        cards: list[KakaoCard],
        *,
        force_refresh: bool,
    ) -> list[CardUsage]:
        settings = SettingsService(self.session).kakao_internal()
        if not settings.base_url:
            raise CardAllocationError("请先配置 Kakao Base URL")
        try:
            client = KakaoClient(settings.base_url, settings.timeout)
        except ValueError as error:
            raise CardAllocationError(str(error)) from error

        repository = CardRepository(self.session)
        cache = repository.usage_cache()
        usages: list[CardUsage] = []
        stale_cards: list[KakaoCard] = []
        for card in cards:
            cached = None if force_refresh else self._cached_usage(card, cache.get(card.id))
            if cached is None:
                stale_cards.append(card)
            else:
                usages.append(cached)

        if stale_cards:
            workers = min(8, max(1, len(stale_cards)))
            with ThreadPoolExecutor(max_workers=workers) as executor:
                refreshed = list(
                    executor.map(
                        lambda card: self._query_card(
                            client,
                            card,
                            settings.card_usage_limit,
                        ),
                        stale_cards,
                    )
                )
            usages.extend(refreshed)
            checked_at = utc_now().isoformat()
            for usage in refreshed:
                cache[usage.card_id] = {
                    "charged": usage.charged if usage.error is None else None,
                    "pending": usage.pending if usage.error is None else None,
                    "remaining": usage.remaining if usage.error is None else None,
                    "error": usage.error,
                    "checked_at": checked_at,
                }
            repository.save_usage_cache(cache)
        return sorted(
            usages,
            key=lambda usage: (
                usage.error is not None,
                usage.remaining if usage.error is None else settings.card_usage_limit + 1,
                usage.card_id,
            ),
        )

    def _cached_usage(
        self,
        card: KakaoCard,
        cached: dict[str, object] | None,
    ) -> CardUsage | None:
        if not cached:
            return None
        try:
            checked_at = datetime.fromisoformat(str(cached["checked_at"]))
            age = (utc_now() - checked_at).total_seconds()
            if age < 0 or age > self.CACHE_TTL_SECONDS:
                return None
            error = str(cached.get("error") or "") or None
            return CardUsage(
                card_id=card.id,
                code=card.code,
                charged=int(str(cached.get("charged") or 0)),
                pending=int(str(cached.get("pending") or 0)),
                remaining=int(str(cached.get("remaining") or 0)),
                error=error,
            )
        except (KeyError, TypeError, ValueError):
            return None

    def select(self, target_count: int) -> tuple[list[str], list[CardUsage]]:
        usages = self.usage()
        reservations = {
            card_id: max(0, int(allocated or 0) - int(created or 0))
            for card_id, allocated, created in self.session.execute(
                select(
                    PipelineCardAllocation.card_id,
                    func.sum(PipelineCardAllocation.allocated_count),
                    func.sum(PipelineCardAllocation.created_count),
                )
                .join(PipelineRun, PipelineRun.id == PipelineCardAllocation.pipeline_run_id)
                .where(
                    PipelineRun.status.in_(
                        [
                            PipelineStatus.QUEUED,
                            PipelineStatus.RUNNING,
                            PipelineStatus.PAUSED,
                        ]
                    )
                )
                .group_by(PipelineCardAllocation.card_id)
            )
        }
        slots = [
            usage.code
            for usage in usages
            if usage.error is None and usage.remaining > 0
            for _ in range(max(0, usage.remaining - reservations.get(usage.card_id, 0)))
        ][:target_count]
        if len(slots) < target_count:
            raise CardAllocationError(
                f"卡密实时剩余次数只有 {len(slots)}，无法分配 {target_count} 个任务"
            )
        return slots, usages

    @staticmethod
    def _query_card(client: KakaoClient, card: KakaoCard, limit: int) -> CardUsage:
        try:
            tasks = client.list_all_tasks(card.code)
        except Exception as error:
            return CardUsage(card.id, card.code, 0, 0, 0, str(error))

        charged_ids: set[str] = set()
        pending_ids: set[str] = set()
        for index, task in enumerate(tasks):
            job_id = str(task.get("job_id") or task.get("id") or f"row-{index}")
            if task.get("card_charged") is True:
                charged_ids.add(job_id)
            elif str(task.get("status") or "").lower() in {"queued", "extracting"}:
                pending_ids.add(job_id)
        occupied = len(charged_ids | pending_ids)
        return CardUsage(
            card_id=card.id,
            code=card.code,
            charged=len(charged_ids),
            pending=len(pending_ids),
            remaining=max(0, limit - occupied),
        )
