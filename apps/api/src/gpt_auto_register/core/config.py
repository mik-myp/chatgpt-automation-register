from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

API_ROOT = Path(__file__).resolve().parents[3]
REPOSITORY_ROOT = API_ROOT.parents[1]
DEFAULT_DATA_PATH = API_ROOT / "data"
DEFAULT_DATABASE_PATH = DEFAULT_DATA_PATH / "gpt-auto-register.db"
DEFAULT_LEGACY_RUNTIME_PATH = API_ROOT / "src" / "gpt_auto_register" / "runtime"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=API_ROOT / ".env",
        env_prefix="GPT_AUTO_",
        extra="ignore",
    )

    app_name: str = "GPT Auto Register"
    app_version: str = "0.2.0"
    environment: Literal["development", "test", "production"] = "development"
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    database_url: str = f"sqlite+pysqlite:///{DEFAULT_DATABASE_PATH}"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    legacy_runtime_path: Path = DEFAULT_LEGACY_RUNTIME_PATH
    data_path: Path = DEFAULT_DATA_PATH
    frontend_dist_path: Path = REPOSITORY_ROOT / "apps" / "web" / "dist"

    authentication_enabled: bool = True
    cookie_secure: bool = False
    session_idle_days: int = Field(default=7, ge=1, le=30)
    session_absolute_days: int = Field(default=30, ge=1, le=90)
    setup_token_minutes: int = Field(default=30, ge=1, le=120)
    trusted_origins: str = "http://127.0.0.1:5173,http://localhost:5173"
    trusted_hosts: str = "127.0.0.1,localhost,testserver"
    forwarded_allow_ips: str = "127.0.0.1"
    master_key_file: Path | None = None

    @model_validator(mode="after")
    def validate_deployment(self) -> "Settings":
        driver = make_url(self.database_url).drivername
        if driver not in {"sqlite+pysqlite", "postgresql+psycopg"}:
            raise ValueError(
                "GPT_AUTO_DATABASE_URL only supports sqlite+pysqlite or postgresql+psycopg"
            )
        if self.environment == "production" and not self.authentication_enabled:
            raise ValueError("authentication cannot be disabled in production")
        return self

    @property
    def session_cookie_secure(self) -> bool:
        return self.environment == "production" or self.cookie_secure

    @property
    def database_dialect(self) -> Literal["sqlite", "postgresql"]:
        return (
            "sqlite"
            if make_url(self.database_url).drivername == "sqlite+pysqlite"
            else "postgresql"
        )

    @property
    def trusted_origin_set(self) -> set[str]:
        return {
            value.strip().rstrip("/") for value in self.trusted_origins.split(",") if value.strip()
        }

    @property
    def trusted_host_list(self) -> list[str]:
        return [value.strip() for value in self.trusted_hosts.split(",") if value.strip()]

    @property
    def runtime_data_path(self) -> Path:
        return self.data_path / "runtime"

    @property
    def backup_path(self) -> Path:
        return self.data_path / "backups"

    @property
    def resolved_master_key_file(self) -> Path:
        return self.master_key_file or self.data_path / "master.key"

    @property
    def database_path(self) -> Path | None:
        if self.database_dialect != "sqlite":
            return None
        database = make_url(self.database_url).database
        return Path(database) if database and database != ":memory:" else None

    def ensure_runtime_directories(self) -> None:
        self.data_path.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.data_path.chmod(0o700)
        if self.database_path:
            self.database_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            self.database_path.parent.chmod(0o700)
        for path in (self.runtime_data_path, self.backup_path):
            path.mkdir(parents=True, exist_ok=True, mode=0o700)
            path.chmod(0o700)
        self.ensure_database_file_permissions()

    def ensure_database_file_permissions(self) -> None:
        if not self.database_path:
            return
        for path in (
            self.database_path,
            Path(f"{self.database_path}-wal"),
            Path(f"{self.database_path}-shm"),
        ):
            if path.exists():
                path.chmod(0o600)


@lru_cache
def get_settings() -> Settings:
    return Settings()
