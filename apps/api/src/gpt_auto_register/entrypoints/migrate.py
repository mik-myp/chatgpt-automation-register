from pathlib import Path

from alembic.config import Config

from alembic import command
from gpt_auto_register.core.config import API_ROOT
from gpt_auto_register.core.encryption import ensure_master_key
from gpt_auto_register.db.session import SessionLocal


def main() -> None:
    local_config = Path.cwd() / "alembic.ini"
    config_path = local_config if local_config.is_file() else API_ROOT / "alembic.ini"
    command.upgrade(Config(str(config_path)), "head")
    with SessionLocal() as session:
        ensure_master_key(session)


if __name__ == "__main__":
    main()
