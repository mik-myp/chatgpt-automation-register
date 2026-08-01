import argparse
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from gpt_auto_register.db.models.accounts import AccountStatus, MailType, OutlookAccount
from gpt_auto_register.db.session import SessionLocal
from gpt_auto_register.modules.accounts.parser import EMAIL_PATTERN

LEGACY_COLUMNS = {
    "email",
    "password",
    "client_id",
    "refresh_token",
    "status",
    "imported_at",
    "claimed_at",
    "finished_at",
    "fail_reason",
    "mail_type",
    "mail_url",
}


@dataclass(frozen=True, slots=True)
class MigrationReport:
    inserted: int = 0
    replaced: int = 0
    skipped: int = 0
    invalid: int = 0


def _legacy_connection(source: Path) -> sqlite3.Connection:
    resolved = source.expanduser().resolve(strict=True)
    connection = sqlite3.connect(f"file:{resolved}?mode=ro&immutable=1", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _timestamp(value: object) -> datetime | None:
    if value is None or value == "":
        return None
    if not isinstance(value, (str, int, float)):
        raise ValueError(f"不支持的时间戳类型: {type(value).__name__}")
    return datetime.fromtimestamp(float(value), UTC)


def _account_from_row(row: sqlite3.Row) -> OutlookAccount | None:
    try:
        email = str(row["email"]).strip().lower()
        if len(email) > 320 or EMAIL_PATTERN.fullmatch(email) is None:
            return None

        status = AccountStatus(str(row["status"] or AccountStatus.AVAILABLE.value))
        mail_type = MailType(str(row["mail_type"] or MailType.OUTLOOK.value))
        imported_at = _timestamp(row["imported_at"]) or datetime.now(UTC)
        return OutlookAccount(
            email=email,
            password=row["password"],
            client_id=row["client_id"],
            refresh_token=row["refresh_token"],
            status=status,
            mail_type=mail_type,
            mail_url=row["mail_url"],
            claimed_at=_timestamp(row["claimed_at"]),
            finished_at=_timestamp(row["finished_at"]),
            failure_reason=row["fail_reason"],
            created_at=imported_at,
            updated_at=imported_at,
        )
    except (TypeError, ValueError, OverflowError):
        return None


def migrate_legacy_accounts(
    source: Path,
    session: Session,
    *,
    replace_existing: bool = False,
) -> MigrationReport:
    inserted = replaced = skipped = invalid = 0

    with _legacy_connection(source) as connection:
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(outlook_accounts)")}
        missing = LEGACY_COLUMNS - columns
        if missing:
            names = ", ".join(sorted(missing))
            raise ValueError(f"旧数据库 outlook_accounts 表缺少字段: {names}")

        rows = connection.execute(
            """
            SELECT email, password, client_id, refresh_token, status, imported_at,
                   claimed_at, finished_at, fail_reason, mail_type, mail_url
            FROM outlook_accounts
            ORDER BY email
            """
        )
        for row in rows:
            incoming = _account_from_row(row)
            if incoming is None:
                invalid += 1
                continue

            existing = session.scalar(
                select(OutlookAccount).where(OutlookAccount.email == incoming.email)
            )
            if existing is None:
                session.add(incoming)
                inserted += 1
                continue
            if not replace_existing:
                skipped += 1
                continue

            for attribute in (
                "password",
                "client_id",
                "refresh_token",
                "status",
                "mail_type",
                "mail_url",
                "claimed_at",
                "finished_at",
                "failure_reason",
                "created_at",
                "updated_at",
            ):
                setattr(existing, attribute, getattr(incoming, attribute))
            existing.version += 1
            replaced += 1

    session.commit()
    return MigrationReport(
        inserted=inserted,
        replaced=replaced,
        skipped=skipped,
        invalid=invalid,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="迁移旧项目中的 Outlook 账号池")
    parser.add_argument("--source", required=True, type=Path, help="旧项目 SQLite 数据库路径")
    parser.add_argument(
        "--replace-existing",
        action="store_true",
        help="覆盖目标库中邮箱相同的账号及其状态",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        with SessionLocal() as session:
            report = migrate_legacy_accounts(
                args.source,
                session,
                replace_existing=args.replace_existing,
            )
    except (OSError, sqlite3.Error, ValueError) as error:
        print(f"迁移失败: {error}")
        return 1

    print(
        "迁移完成: "
        f"新增 {report.inserted}, 覆盖 {report.replaced}, "
        f"跳过 {report.skipped}, 无效 {report.invalid}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
