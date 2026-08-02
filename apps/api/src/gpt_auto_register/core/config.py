from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

API_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATABASE_PATH = API_ROOT / "data" / "gpt-auto-register.db"
DEFAULT_LEGACY_RUNTIME_PATH = API_ROOT / "src" / "gpt_auto_register" / "runtime"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=API_ROOT / ".env",
        env_prefix="GPT_AUTO_",
        extra="ignore",
    )

    app_name: str = "GPT Auto Register"
    app_version: str = "0.1.0"
    host: Literal["127.0.0.1", "localhost"] = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    database_url: str = f"sqlite+pysqlite:///{DEFAULT_DATABASE_PATH}"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    legacy_runtime_path: Path = DEFAULT_LEGACY_RUNTIME_PATH

    @property
    def runtime_data_path(self) -> Path:
        return API_ROOT / "data" / "runtime"

    @property
    def backup_path(self) -> Path:
        return API_ROOT / "data" / "backups"

    @property
    def database_path(self) -> Path | None:
        prefix = "sqlite+pysqlite:///"
        if not self.database_url.startswith(prefix):
            return None
        return Path(self.database_url.removeprefix(prefix))

    def ensure_runtime_directories(self) -> None:
        if self.database_path:
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.runtime_data_path.mkdir(parents=True, exist_ok=True)
        self.backup_path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
