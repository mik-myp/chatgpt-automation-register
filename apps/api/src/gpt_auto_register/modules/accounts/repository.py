from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from gpt_auto_register.db.base import utc_now
from gpt_auto_register.db.models.accounts import AccountStatus, OutlookAccount
from gpt_auto_register.db.result import affected_rows
from gpt_auto_register.modules.accounts.parser import ParsedAccount


@dataclass(frozen=True, slots=True)
class ImportCounts:
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0


class AccountRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, email: str) -> OutlookAccount | None:
        return self.session.get(OutlookAccount, email.lower())

    def list_page(
        self,
        *,
        status: AccountStatus | None,
        search: str,
        limit: int,
        offset: int,
    ) -> tuple[list[OutlookAccount], int]:
        filters = []
        if status is not None:
            filters.append(OutlookAccount.status == status)
        if search:
            needle = f"%{search.strip().lower()}%"
            filters.append(
                or_(
                    func.lower(OutlookAccount.email).like(needle),
                    func.lower(OutlookAccount.failure_reason).like(needle),
                )
            )

        query = select(OutlookAccount).where(*filters)
        count_query = select(func.count()).select_from(OutlookAccount).where(*filters)
        total = self.session.scalar(count_query) or 0
        items = list(
            self.session.scalars(
                query.order_by(OutlookAccount.created_at.desc(), OutlookAccount.email)
                .limit(limit)
                .offset(offset)
            )
        )
        return items, total

    def stats(self) -> dict[AccountStatus, int]:
        rows = self.session.execute(
            select(OutlookAccount.status, func.count()).group_by(OutlookAccount.status)
        )
        return {status: count for status, count in rows}

    def import_accounts(self, accounts: list[ParsedAccount]) -> ImportCounts:
        inserted = updated = unchanged = 0
        for value in accounts:
            account = self.get(value.email)
            if account is None:
                self.session.add(
                    OutlookAccount(
                        email=value.email,
                        password=value.password,
                        client_id=value.client_id,
                        refresh_token=value.refresh_token,
                        mail_type=value.mail_type,
                        mail_url=value.mail_url,
                    )
                )
                inserted += 1
                continue

            source_changed = any(
                (
                    account.password != value.password,
                    account.client_id != value.client_id,
                    account.refresh_token != value.refresh_token,
                    account.mail_type != value.mail_type,
                    account.mail_url != value.mail_url,
                )
            )
            if not source_changed:
                unchanged += 1
                continue
            account.password = value.password
            account.client_id = value.client_id
            account.refresh_token = value.refresh_token
            account.mail_type = value.mail_type
            account.mail_url = value.mail_url
            updated += 1

        self.session.flush()
        return ImportCounts(inserted=inserted, updated=updated, unchanged=unchanged)

    def claim(self, email: str | None = None) -> OutlookAccount | None:
        filters = [OutlookAccount.status == AccountStatus.AVAILABLE]
        if email:
            filters.append(OutlookAccount.email == email.lower())
            target_email: str | ColumnElement[str] = email.lower()
        else:
            target_email = (
                select(OutlookAccount.email)
                .where(*filters)
                .order_by(OutlookAccount.created_at, OutlookAccount.email)
                .limit(1)
                .scalar_subquery()
            )

        statement = (
            update(OutlookAccount)
            .where(OutlookAccount.email == target_email, *filters)
            .values(
                status=AccountStatus.IN_USE,
                claimed_at=utc_now(),
                finished_at=None,
                failure_reason=None,
                version=OutlookAccount.version + 1,
            )
            .returning(OutlookAccount)
        )
        return self.session.scalars(statement).one_or_none()

    def release(self, email: str) -> OutlookAccount | None:
        statement = (
            update(OutlookAccount)
            .where(
                OutlookAccount.email == email.lower(),
                OutlookAccount.status == AccountStatus.IN_USE,
            )
            .values(
                status=AccountStatus.AVAILABLE,
                claimed_at=None,
                finished_at=None,
                failure_reason=None,
                version=OutlookAccount.version + 1,
            )
            .returning(OutlookAccount)
        )
        return self.session.scalars(statement).one_or_none()

    def reset(self, email: str) -> OutlookAccount | None:
        statement = (
            update(OutlookAccount)
            .where(
                OutlookAccount.email == email.lower(),
                OutlookAccount.status.in_([AccountStatus.DONE, AccountStatus.FAILED]),
            )
            .values(
                status=AccountStatus.AVAILABLE,
                claimed_at=None,
                finished_at=None,
                failure_reason=None,
                version=OutlookAccount.version + 1,
            )
            .returning(OutlookAccount)
        )
        return self.session.scalars(statement).one_or_none()

    def delete(self, email: str) -> bool:
        statement = (
            delete(OutlookAccount)
            .where(
                OutlookAccount.email == email.lower(),
                OutlookAccount.status != AccountStatus.IN_USE,
            )
            .returning(OutlookAccount.email)
        )
        return self.session.scalar(statement) is not None

    def reset_all_failed(self) -> int:
        result = self.session.execute(
            update(OutlookAccount)
            .where(OutlookAccount.status == AccountStatus.FAILED)
            .values(
                status=AccountStatus.AVAILABLE,
                claimed_at=None,
                finished_at=None,
                failure_reason=None,
                version=OutlookAccount.version + 1,
            )
        )
        return affected_rows(result)

    def release_stale(self, stale_minutes: int) -> int:
        threshold = utc_now() - timedelta(minutes=stale_minutes)
        result = self.session.execute(
            update(OutlookAccount)
            .where(
                OutlookAccount.status == AccountStatus.IN_USE,
                OutlookAccount.claimed_at < threshold,
            )
            .values(
                status=AccountStatus.AVAILABLE,
                claimed_at=None,
                finished_at=None,
                failure_reason=None,
                version=OutlookAccount.version + 1,
            )
        )
        return affected_rows(result)

    def delete_by_status(self, status: AccountStatus | None) -> tuple[int, int]:
        filters = [OutlookAccount.status != AccountStatus.IN_USE]
        if status is not None:
            filters.append(OutlookAccount.status == status)
        skipped = (
            self.session.scalar(
                select(func.count())
                .select_from(OutlookAccount)
                .where(
                    OutlookAccount.status == AccountStatus.IN_USE,
                    *([OutlookAccount.status == status] if status is not None else []),
                )
            )
            or 0
        )
        result = self.session.execute(delete(OutlookAccount).where(*filters))
        return affected_rows(result), skipped
