from collections.abc import Generator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from gpt_auto_register.core.config import get_settings

settings = get_settings()
settings.ensure_runtime_directories()

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@event.listens_for(Engine, "connect")
def configure_sqlite(connection: object, _connection_record: object) -> None:
    if not settings.database_url.startswith("sqlite"):
        return
    cursor = connection.cursor()  # type: ignore[attr-defined]
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()
    settings.ensure_database_file_permissions()


def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session
