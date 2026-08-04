import httpx
import pytest
from sqlalchemy.orm import Session, sessionmaker

from gpt_auto_register.db.models.jobs import Job
from gpt_auto_register.modules.settings.schemas import ProxySettings
from gpt_auto_register.worker.proxy_service import (
    ProxyAllocator,
    ProxyApiError,
    _request_url,
    normalize_proxy,
)


def test_normalize_proxy_accepts_host_port() -> None:
    assert normalize_proxy("162.128.157.89:7000") == "http://162.128.157.89:7000"


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://proxy.example/api?num=1", "https://proxy.example/api?num=6"),
        ("https://proxy.example/api?token=x", "https://proxy.example/api?token=x&num=6"),
        ("https://proxy.example/api?count={count}", "https://proxy.example/api?count=6"),
    ],
)
def test_request_url_injects_requested_count(url: str, expected: str) -> None:
    assert _request_url(url, 6) == expected


def test_request_url_overrides_region_and_preserves_other_parameters() -> None:
    assert (
        _request_url(
            "https://proxy.example/api?token=x&num=1&region=US",
            6,
            region="vn",
        )
        == "https://proxy.example/api?token=x&num=6&region=VN"
    )


def test_allocator_preserves_order_and_assigns_contiguous_groups(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job = Job(kind="pipeline.run", payload={})
    db_session.add(job)
    db_session.commit()
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)

    class Response:
        text = ""

        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> object:
            return {"data": [f"10.0.0.{index}:7000" for index in range(1, 7)]}

    monkeypatch.setattr(httpx, "get", lambda *_args, **_kwargs: Response())
    batch = ProxyAllocator(
        ProxySettings(api_url="https://proxy.example/api", max_attempts_per_account=3),
        factory,
        job.id,
        "registration",
    ).allocate(["first", "second"])

    assert batch.assignments == {
        "first": [
            "http://10.0.0.1:7000",
            "http://10.0.0.2:7000",
            "http://10.0.0.3:7000",
        ],
        "second": [
            "http://10.0.0.4:7000",
            "http://10.0.0.5:7000",
            "http://10.0.0.6:7000",
        ],
    }


def test_allocator_rejects_duplicates_and_does_not_start_partial_account(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job = Job(kind="pipeline.run", payload={})
    db_session.add(job)
    db_session.commit()
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)

    class Response:
        text = ""

        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> object:
            return ["10.0.0.1:7000", "10.0.0.2:7000", "10.0.0.2:7000"]

    monkeypatch.setattr(httpx, "get", lambda *_args, **_kwargs: Response())
    batch = ProxyAllocator(
        ProxySettings(api_url="https://proxy.example/api", max_attempts_per_account=2),
        factory,
        job.id,
        "kakao",
    ).allocate(["first", "second"])

    assert batch.assignments == {
        "first": ["http://10.0.0.1:7000", "http://10.0.0.2:7000"]
    }
    assert batch.duplicate_count == 1
    assert "second" not in batch.assignments


def test_allocator_keeps_invalid_positions_in_the_original_account_group(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job = Job(kind="pipeline.run", payload={})
    db_session.add(job)
    db_session.commit()
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)

    class Response:
        text = ""

        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> object:
            return [
                "10.0.0.1:7000",
                "10.0.0.1:7000",
                "10.0.0.3:7000",
                "10.0.0.4:7000",
            ]

    monkeypatch.setattr(httpx, "get", lambda *_args, **_kwargs: Response())
    batch = ProxyAllocator(
        ProxySettings(api_url="https://proxy.example/api", max_attempts_per_account=2),
        factory,
        job.id,
        "registration",
    ).allocate(["first", "second"])

    assert "first" not in batch.assignments
    assert batch.assignments["second"] == [
        "http://10.0.0.3:7000",
        "http://10.0.0.4:7000",
    ]


def test_allocator_requires_proxy_api_configuration(db_session: Session) -> None:
    job = Job(kind="pipeline.run", payload={})
    db_session.add(job)
    db_session.commit()
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)

    with pytest.raises(ProxyApiError, match="禁止使用直连或旧代理池"):
        ProxyAllocator(ProxySettings(), factory, job.id, "registration").allocate(["first"])
