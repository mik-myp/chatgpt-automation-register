from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from gpt_auto_register.db.base import Base
from gpt_auto_register.db.models import AppSetting  # noqa: F401
from gpt_auto_register.db.session import get_db
from gpt_auto_register.main import create_app


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory() as session:
        yield session
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    application = create_app(authentication_enabled=False, worker_enabled=False)
    application.state.session_factory = sessionmaker(
        bind=db_session.get_bind(), expire_on_commit=False
    )

    def override_db() -> Generator[Session, None, None]:
        yield db_session

    application.dependency_overrides[get_db] = override_db
    with TestClient(application) as test_client:
        yield test_client
