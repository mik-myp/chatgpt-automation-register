import pytest
from sqlalchemy.orm import Session, sessionmaker

from gpt_auto_register.db.models.jobs import Job
from gpt_auto_register.db.models.kakao import (
    KakaoCard,
    KakaoCardBatch,
    PipelineCardAllocation,
)
from gpt_auto_register.db.models.pipeline import PipelineItem, PipelineRun
from gpt_auto_register.modules.cards.allocator import CardAllocator
from gpt_auto_register.worker import manager


def test_first_card_allocation_initializes_counters(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = PipelineRun(target_count=1, kakao_enabled=True, config_snapshot={})
    batch = KakaoCardBatch(name="test")
    db_session.add_all([run, batch])
    db_session.flush()
    item = PipelineItem(pipeline_run_id=run.id, position=0)
    card = KakaoCard(batch_id=batch.id, code="test-card", position=0)
    job = Job(id="allocation-job", kind="pipeline.run", payload={})
    db_session.add_all([item, card, job])
    db_session.commit()

    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    monkeypatch.setattr(manager, "SessionLocal", factory)
    monkeypatch.setattr(
        CardAllocator,
        "select",
        lambda _self, _count: (["test-card"], []),
    )

    mapping = manager.PipelineExecutor("allocation-job", run.id)._allocate_cards([item.id])

    with factory() as session:
        allocation = session.get(PipelineCardAllocation, (run.id, card.id))
        assert mapping == {item.id: "test-card"}
        assert allocation is not None
        assert allocation.allocated_count == 1
        assert allocation.created_count == 0
