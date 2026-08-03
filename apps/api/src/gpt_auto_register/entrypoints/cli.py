import argparse
import getpass

from sqlalchemy import select

from gpt_auto_register.core.config import get_settings
from gpt_auto_register.core.encryption import ensure_master_key
from gpt_auto_register.core.security import hash_password
from gpt_auto_register.db.base import utc_now
from gpt_auto_register.db.models.auth import User
from gpt_auto_register.db.session import SessionLocal
from gpt_auto_register.infrastructure.authentication import AuthenticationService


def reset_password(username: str) -> None:
    first = getpass.getpass("New administrator password: ")
    second = getpass.getpass("Confirm administrator password: ")
    if len(first) < 12:
        raise SystemExit("Password must contain at least 12 characters")
    if first != second:
        raise SystemExit("Passwords do not match")
    with SessionLocal() as session:
        ensure_master_key(session)
        user = session.scalar(select(User).where(User.username == username.strip().lower()))
        if user is None:
            raise SystemExit(f"Administrator not found: {username}")
        user.password_hash = hash_password(first)
        user.password_changed_at = utc_now()
        AuthenticationService(session, get_settings()).revoke_all(user.id)
        session.commit()
    print("Administrator password reset; all sessions were revoked.")


def main() -> None:
    parser = argparse.ArgumentParser(prog="gpt-auto-cli")
    groups = parser.add_subparsers(dest="group", required=True)
    admin = groups.add_parser("admin")
    commands = admin.add_subparsers(dest="command", required=True)
    reset = commands.add_parser("reset-password")
    reset.add_argument("username", nargs="?", default="admin")
    arguments = parser.parse_args()
    if arguments.group == "admin" and arguments.command == "reset-password":
        reset_password(arguments.username)


if __name__ == "__main__":
    main()
