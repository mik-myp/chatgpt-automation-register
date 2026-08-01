from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from gpt_auto_register.api.dependencies import DatabaseSession
from gpt_auto_register.db.base import utc_now
from gpt_auto_register.modules.cards.allocator import CardAllocationError, CardAllocator
from gpt_auto_register.modules.cards.repository import CardRepository
from gpt_auto_register.modules.cards.schemas import (
    BulkCardAction,
    BulkCardRequest,
    BulkCardResponse,
    CardInventoryItem,
    CardInventoryResponse,
    CardInventoryStats,
    CardSelectionRequest,
    CardSelectionResponse,
    CardUsageItem,
    CardUsageResponse,
    ImportCardsRequest,
    ImportCardsResponse,
)

router = APIRouter(prefix="/kakao/cards", tags=["kakao-cards"])


@router.get("", response_model=CardInventoryResponse)
def list_cards(
    db: DatabaseSession,
    active: bool | None = None,
    search: str = "",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CardInventoryResponse:
    rows, total = CardRepository(db).list_page(
        active=active,
        search=search,
        limit=limit,
        offset=offset,
    )
    usage_cache = CardRepository(db).usage_cache()
    items: list[CardInventoryItem] = []
    for row in rows:
        cached = usage_cache.get(row.card.id, {})
        items.append(
            CardInventoryItem(
                id=row.card.id,
                code=row.card.code,
                batch_id=row.batch.id,
                batch_name=row.batch.name,
                batch_status=row.batch.status,
                position=row.card.position,
                active=row.card.active,
                run_count=row.run_count,
                allocated_count=row.allocated_count,
                created_count=row.created_count,
                duplicate_count=row.duplicate_count,
                failed_count=row.failed_count,
                cached_charged=cached.get("charged"),
                cached_pending=cached.get("pending"),
                cached_remaining=cached.get("remaining"),
                usage_error=str(cached.get("error") or "") or None,
                usage_checked_at=cached.get("checked_at"),
                created_at=row.card.created_at,
            )
        )
    return CardInventoryResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/stats", response_model=CardInventoryStats)
def get_card_stats(db: DatabaseSession) -> CardInventoryStats:
    total, active, batches = CardRepository(db).stats()
    return CardInventoryStats(
        total=total,
        active=active,
        inactive=total - active,
        batches=batches,
    )


@router.post("/import", response_model=ImportCardsResponse)
def import_cards(request: ImportCardsRequest, db: DatabaseSession) -> ImportCardsResponse:
    codes = list(
        dict.fromkeys(
            line.strip()
            for line in request.text.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )
    )
    repository = CardRepository(db)
    batch_id, inserted, duplicates = repository.import_cards(codes, request.batch_name)
    db.commit()
    return ImportCardsResponse(
        batch_id=batch_id,
        inserted=inserted,
        duplicates=duplicates,
    )


@router.post("/batch", response_model=BulkCardResponse)
def bulk_card_action(request: BulkCardRequest, db: DatabaseSession) -> BulkCardResponse:
    card_ids = list(
        dict.fromkeys(card_id.strip() for card_id in request.card_ids if card_id.strip())
    )
    repository = CardRepository(db)
    if request.action == BulkCardAction.DELETE:
        processed = repository.delete_cards(card_ids)
    else:
        processed = repository.set_active(
            card_ids,
            request.action == BulkCardAction.ACTIVATE,
        )
    db.commit()
    return BulkCardResponse(processed=processed, skipped=len(card_ids) - processed)


@router.post("/select", response_model=CardSelectionResponse)
def select_cards(request: CardSelectionRequest, db: DatabaseSession) -> CardSelectionResponse:
    try:
        slots, usages = CardAllocator(db).select(request.target_count)
    except CardAllocationError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    return CardSelectionResponse(
        slots=slots,
        usage=[CardUsageItem(**asdict(usage)) for usage in usages],
    )


@router.get("/usage", response_model=CardUsageResponse)
def get_card_usage(db: DatabaseSession) -> CardUsageResponse:
    try:
        usages = CardAllocator(db).inventory_usage()
    except CardAllocationError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    except Exception as error:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            f"卡密用量查询失败: {error}",
        ) from error
    checked_at = utc_now().isoformat()
    repository = CardRepository(db)
    cache = repository.usage_cache()
    for usage in usages:
        cache[usage.card_id] = {
            "charged": usage.charged if usage.error is None else None,
            "pending": usage.pending if usage.error is None else None,
            "remaining": usage.remaining if usage.error is None else None,
            "error": usage.error,
            "checked_at": checked_at,
        }
    repository.save_usage_cache(cache)
    db.commit()
    return CardUsageResponse(items=[CardUsageItem(**asdict(usage)) for usage in usages])
