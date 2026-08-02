from datetime import timedelta

import pytest
from sqlalchemy.orm import Session

from gpt_auto_register.db.base import utc_now
from gpt_auto_register.db.models.kakao import KakaoCard, KakaoCardBatch
from gpt_auto_register.db.models.settings import AppSetting
from gpt_auto_register.modules.cards.allocator import CardAllocator
from gpt_auto_register.modules.kakao.client import KakaoClient


def test_card_allocator_reuses_fresh_usage_snapshot(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    batch = KakaoCardBatch(name="cache")
    db_session.add_all(
        [
            batch,
            AppSetting(
                key="kakao",
                value={
                    "base_url": "https://kakao.example.com",
                    "timeout": 30,
                    "card_usage_limit": 5,
                },
            ),
        ]
    )
    db_session.flush()
    card = KakaoCard(batch_id=batch.id, code="CACHE-CARD", position=0)
    db_session.add(card)
    db_session.flush()
    db_session.add(
        AppSetting(
            key="card_usage_cache",
            value={
                card.id: {
                    "charged": 1,
                    "pending": 1,
                    "remaining": 3,
                    "error": None,
                    "checked_at": (utc_now() - timedelta(seconds=5)).isoformat(),
                }
            },
        )
    )
    db_session.commit()

    def unexpected_request(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("fresh usage cache should avoid an upstream request")

    monkeypatch.setattr(KakaoClient, "list_all_tasks", unexpected_request)

    usages = CardAllocator(db_session).usage()

    assert len(usages) == 1
    assert usages[0].remaining == 3
