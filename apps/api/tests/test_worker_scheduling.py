import threading

from sqlalchemy.orm import Session, sessionmaker

from gpt_auto_register.db.models.jobs import Job
from gpt_auto_register.db.models.pipeline import PipelineRun, PipelineRunKind
from gpt_auto_register.db.models.settings import AppSetting
from gpt_auto_register.worker.manager import WorkerManager
from gpt_auto_register.worker.pipeline_kakao_executor import pair_kakao_proxy_assignments


def test_kakao_proxy_pairs_reject_cross_region_reuse() -> None:
    assignments, failures = pair_kakao_proxy_assignments(
        ["first", "second", "third"],
        {
            "first": ["kr-1", "kr-2"],
            "second": ["kr-3", "kr-4"],
            "third": ["kr-5", "kr-6"],
        },
        {
            "first": ["vn-1", "vn-2"],
            "second": ["kr-1", "vn-4"],
            "third": ["vn-5", "kr-5"],
        },
    )

    assert assignments == {"first": [("kr-1", "vn-1"), ("kr-2", "vn-2")]}
    assert failures == {
        "second": "Kakao 账号预分配代理已被前序账号占用",
        "third": "Kakao 账号预分配的 KR/VN 代理存在重复",
    }


def test_worker_uses_persisted_step_order(db_session: Session) -> None:
    registration = PipelineRun(target_count=1, config_snapshot={})
    kakao = PipelineRun(
        kind=PipelineRunKind.KAKAO,
        target_count=1,
        kakao_enabled=True,
        config_snapshot={},
    )
    db_session.add_all(
        [
            registration,
            kakao,
            AppSetting(
                key="pipeline",
                value={"step_order": ["kakao", "account_security", "registration"]},
            ),
        ]
    )
    db_session.flush()
    registration_job = Job(
        kind="pipeline.run",
        pipeline_run_id=registration.id,
        priority=100,
        payload={},
    )
    security_job = Job(kind="account.security", priority=100, payload={})
    kakao_job = Job(kind="pipeline.run", pipeline_run_id=kakao.id, payload={})
    db_session.add_all([registration_job, security_job, kakao_job])
    db_session.commit()
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)

    claimed = WorkerManager(session_factory=factory)._claim()

    assert claimed is not None
    assert claimed.id == kakao_job.id


def test_worker_enforces_task_type_concurrency_limit(db_session: Session) -> None:
    first_run = PipelineRun(target_count=1, config_snapshot={})
    second_run = PipelineRun(target_count=1, config_snapshot={})
    db_session.add_all(
        [
            first_run,
            second_run,
            AppSetting(
                key="pipeline",
                value={"registration_task_concurrency": 1},
            ),
        ]
    )
    db_session.flush()
    db_session.add_all(
        [
            Job(kind="pipeline.run", pipeline_run_id=first_run.id, payload={}),
            Job(kind="pipeline.run", pipeline_run_id=second_run.id, payload={}),
        ]
    )
    db_session.commit()
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    worker = WorkerManager(session_factory=factory)
    worker._active_jobs["active"] = (
        threading.Thread(),
        threading.Event(),
        "registration",
    )

    assert worker._claim() is None

    with factory() as session:
        row = session.get(AppSetting, "pipeline")
        assert row is not None
        row.value = {"registration_task_concurrency": 2}
        session.commit()

    assert worker._claim() is not None
