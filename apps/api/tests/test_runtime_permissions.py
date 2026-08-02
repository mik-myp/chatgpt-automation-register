import stat
from pathlib import Path

from gpt_auto_register.core.config import Settings


def permission_bits(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_sqlite_files_are_owner_only(tmp_path: Path) -> None:
    database = tmp_path / "data" / "app.db"
    database.parent.mkdir(mode=0o755)
    for path in (database, Path(f"{database}-wal"), Path(f"{database}-shm")):
        path.touch(mode=0o644)
        path.chmod(0o644)

    settings = Settings(database_url=f"sqlite+pysqlite:///{database}")
    settings.ensure_runtime_directories()

    assert permission_bits(database.parent) == 0o700
    assert permission_bits(database) == 0o600
    assert permission_bits(Path(f"{database}-wal")) == 0o600
    assert permission_bits(Path(f"{database}-shm")) == 0o600
