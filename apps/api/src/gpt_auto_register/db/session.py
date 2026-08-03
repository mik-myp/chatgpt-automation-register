from collections.abc import Generator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from gpt_auto_register.core.config import Settings, get_settings


def create_database_engine(settings: Settings) -> Engine:
    settings.ensure_runtime_directories()
    driver = make_url(settings.database_url).drivername
    connect_args: dict[str, object] = {}
    if driver == "sqlite+pysqlite":
        connect_args["check_same_thread"] = False
    database_engine = create_engine(
        settings.database_url,
        connect_args=connect_args,
        pool_pre_ping=True,
    )
    if driver == "sqlite+pysqlite":

        @event.listens_for(database_engine, "connect")
        def configure_sqlite(connection: object, _connection_record: object) -> None:
            cursor = connection.cursor()  # type: ignore[attr-defined]
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()
            settings.ensure_database_file_permissions()

    return database_engine


settings = get_settings()
engine = create_database_engine(settings)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session
