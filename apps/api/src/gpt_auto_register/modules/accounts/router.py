from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status

from gpt_auto_register.api.dependencies import DatabaseSession
from gpt_auto_register.db.models.accounts import AccountStatus
from gpt_auto_register.modules.accounts.repository import AccountRepository
from gpt_auto_register.modules.accounts.schemas import (
    AccountDetail,
    AccountListResponse,
    AccountMaintenanceRequest,
    AccountMaintenanceResponse,
    AccountStats,
    BulkAccountRequest,
    BulkAccountResponse,
    ClaimAccountRequest,
    ImportAccountsRequest,
    ImportAccountsResponse,
)
from gpt_auto_register.modules.accounts.service import (
    AccountNotFoundError,
    AccountPoolEmptyError,
    AccountService,
    AccountStateError,
    account_stats,
)

router = APIRouter(prefix="/accounts", tags=["accounts"])


def _summary(
    account: object, credential: object | None = None
) -> AccountDetail | dict[str, object]:
    value = AccountDetail.model_validate(account).model_dump()
    value.pop("password", None)
    value.pop("client_id", None)
    value.pop("refresh_token", None)
    value.pop("mail_url", None)
    if credential is None:
        return value
    metadata = getattr(credential, "metadata_json", {}) or {}
    security = metadata.get("account_security", {}) if isinstance(metadata, dict) else {}
    password = security.get("password", {}) if isinstance(security, dict) else {}
    mfa = security.get("mfa", {}) if isinstance(security, dict) else {}
    password_default = "set" if getattr(credential, "password", None) else "not_set"
    mfa_default = "enabled" if getattr(credential, "totp_secret", None) else "not_enabled"
    value["password_status"] = str(password.get("status") or password_default)
    value["mfa_status"] = str(mfa.get("status") or mfa_default)
    value["security_error"] = str(mfa.get("error") or password.get("error") or "") or None
    return value


def _handle_account_error(error: Exception) -> HTTPException:
    if isinstance(error, AccountNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, "账号不存在")
    if isinstance(error, AccountPoolEmptyError):
        return HTTPException(status.HTTP_409_CONFLICT, "号池没有可用账号")
    if isinstance(error, AccountStateError):
        return HTTPException(status.HTTP_409_CONFLICT, str(error))
    raise error


@router.get("", response_model=AccountListResponse)
def list_accounts(
    db: DatabaseSession,
    account_status: Annotated[AccountStatus | None, Query(alias="status")] = None,
    search: str = "",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AccountListResponse:
    items, total = AccountRepository(db).list_page(
        status=account_status,
        search=search,
        limit=limit,
        offset=offset,
    )
    credentials = AccountRepository(db).credentials([item.email for item in items])
    return AccountListResponse(
        items=[_summary(item, credentials.get(item.email)) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/stats", response_model=AccountStats)
def get_account_stats(db: DatabaseSession) -> AccountStats:
    return AccountStats(**account_stats(AccountRepository(db)))


@router.post("/import", response_model=ImportAccountsResponse)
def import_accounts(request: ImportAccountsRequest, db: DatabaseSession) -> ImportAccountsResponse:
    return AccountService(db).import_accounts(request.text)


@router.post("/claim", response_model=AccountDetail)
def claim_account(request: ClaimAccountRequest, db: DatabaseSession) -> AccountDetail:
    try:
        return AccountDetail.model_validate(AccountService(db).claim(request.email))
    except (AccountNotFoundError, AccountPoolEmptyError, AccountStateError) as error:
        raise _handle_account_error(error) from error


@router.post("/batch", response_model=BulkAccountResponse)
def bulk_account_action(request: BulkAccountRequest, db: DatabaseSession) -> BulkAccountResponse:
    return AccountService(db).bulk_action(request.action, request.emails)


@router.post("/maintenance", response_model=AccountMaintenanceResponse)
def maintain_accounts(
    request: AccountMaintenanceRequest, db: DatabaseSession
) -> AccountMaintenanceResponse:
    return AccountService(db).maintain(
        request.action,
        status=request.status,
        stale_minutes=request.stale_minutes,
    )


@router.get("/{email}", response_model=AccountDetail)
def get_account(email: str, db: DatabaseSession) -> AccountDetail:
    account = AccountRepository(db).get(email)
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "账号不存在")
    return AccountDetail.model_validate(account)


@router.post("/{email}/release", response_model=AccountDetail)
def release_account(email: str, db: DatabaseSession) -> AccountDetail:
    try:
        return AccountDetail.model_validate(AccountService(db).release(email))
    except (AccountNotFoundError, AccountStateError) as error:
        raise _handle_account_error(error) from error


@router.post("/{email}/reset", response_model=AccountDetail)
def reset_account(email: str, db: DatabaseSession) -> AccountDetail:
    try:
        return AccountDetail.model_validate(AccountService(db).reset(email))
    except (AccountNotFoundError, AccountStateError) as error:
        raise _handle_account_error(error) from error


@router.delete("/{email}", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(email: str, db: DatabaseSession) -> Response:
    try:
        AccountService(db).delete(email)
    except (AccountNotFoundError, AccountStateError) as error:
        raise _handle_account_error(error) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)
