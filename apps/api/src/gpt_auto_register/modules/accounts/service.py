from typing import NoReturn

from sqlalchemy.orm import Session

from gpt_auto_register.db.models.accounts import AccountStatus, OutlookAccount
from gpt_auto_register.modules.accounts.parser import parse_accounts
from gpt_auto_register.modules.accounts.repository import AccountRepository
from gpt_auto_register.modules.accounts.schemas import (
    AccountMaintenanceAction,
    AccountMaintenanceResponse,
    BulkAccountAction,
    BulkAccountResponse,
    ImportAccountsResponse,
)


class AccountNotFoundError(Exception):
    pass


class AccountStateError(Exception):
    pass


class AccountPoolEmptyError(Exception):
    pass


class AccountService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = AccountRepository(session)

    def import_accounts(self, text: str) -> ImportAccountsResponse:
        parsed = parse_accounts(text)
        counts = self.repository.import_accounts(parsed.accounts)
        self.session.commit()
        return ImportAccountsResponse(
            inserted=counts.inserted,
            updated=counts.updated,
            unchanged=counts.unchanged,
            invalid=len(parsed.invalid_lines),
            invalid_lines=parsed.invalid_lines[:20],
        )

    def claim(self, email: str | None) -> OutlookAccount:
        account = self.repository.claim(email)
        if account is None:
            if email and self.repository.get(email) is None:
                raise AccountNotFoundError(email)
            if email:
                raise AccountStateError("账号当前不可领取")
            raise AccountPoolEmptyError
        self.session.commit()
        return account

    def release(self, email: str) -> OutlookAccount:
        account = self.repository.release(email)
        if account is None:
            self._raise_missing_or_state(email, "只有使用中的账号可以释放")
        self.session.commit()
        return account

    def reset(self, email: str) -> OutlookAccount:
        account = self.repository.reset(email)
        if account is None:
            self._raise_missing_or_state(email, "只有已完成或失败的账号可以重置")
        self.session.commit()
        return account

    def delete(self, email: str) -> None:
        if self.repository.delete(email):
            self.session.commit()
            return
        self._raise_missing_or_state(email, "使用中的账号不能删除")

    def bulk_action(self, action: BulkAccountAction, emails: list[str]) -> BulkAccountResponse:
        processed = skipped = 0
        unique_emails = list(
            dict.fromkeys(email.strip().lower() for email in emails if email.strip())
        )
        for email in unique_emails:
            if action == BulkAccountAction.RELEASE:
                changed = self.repository.release(email) is not None
            elif action == BulkAccountAction.RESET:
                changed = self.repository.reset(email) is not None
            else:
                changed = self.repository.delete(email)
            if changed:
                processed += 1
            else:
                skipped += 1

        self.session.commit()
        return BulkAccountResponse(processed=processed, skipped=skipped)

    def maintain(
        self,
        action: AccountMaintenanceAction,
        *,
        status: AccountStatus | None,
        stale_minutes: int,
    ) -> AccountMaintenanceResponse:
        skipped = 0
        if action == AccountMaintenanceAction.RESET_FAILED:
            processed = self.repository.reset_all_failed()
        elif action == AccountMaintenanceAction.RELEASE_STALE:
            processed = self.repository.release_stale(stale_minutes)
        else:
            processed, skipped = self.repository.delete_by_status(status)
        self.session.commit()
        return AccountMaintenanceResponse(processed=processed, skipped=skipped)

    def _raise_missing_or_state(self, email: str, message: str) -> NoReturn:
        account = self.repository.get(email)
        if account is None:
            raise AccountNotFoundError(email)
        raise AccountStateError(message)


def account_stats(repository: AccountRepository) -> dict[str, int]:
    counts = repository.stats()
    return {
        "total": sum(counts.values()),
        "available": counts.get(AccountStatus.AVAILABLE, 0),
        "in_use": counts.get(AccountStatus.IN_USE, 0),
        "done": counts.get(AccountStatus.DONE, 0),
        "failed": counts.get(AccountStatus.FAILED, 0),
    }
