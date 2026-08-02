from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import func, select

from gpt_auto_register.api.dependencies import DatabaseSession
from gpt_auto_register.db.models.accounts import AccountStatus
from gpt_auto_register.db.models.jobs import Job, JobEvent
from gpt_auto_register.modules.accounts.repository import AccountRepository
from gpt_auto_register.modules.accounts.schemas import (
    AccountDetail,
    AccountListResponse,
    AccountMaintenanceRequest,
    AccountMaintenanceResponse,
    AccountSecurityJobDetail,
    AccountSecurityJobEvent,
    AccountSecurityJobListResponse,
    AccountSecurityJobSummary,
    AccountStats,
    AccountSummary,
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
from gpt_auto_register.modules.settings.service import SettingsService

router = APIRouter(prefix="/accounts", tags=["accounts"])


def _security_job_summary(job: Job) -> AccountSecurityJobSummary:
    payload = job.payload if isinstance(job.payload, dict) else {}
    result = job.result if isinstance(job.result, dict) else {}
    emails = [str(value) for value in payload.get("emails", [])]
    return AccountSecurityJobSummary(
        id=job.id,
        status=job.status,
        action=str(payload.get("action") or ""),
        emails=emails,
        succeeded=int(result.get("succeeded") or 0),
        failed=int(result.get("failed") or 0),
        skipped=int(result.get("skipped") or 0),
        total=int(result.get("total") or len(emails)),
        error=job.error,
        created_at=job.created_at,
        updated_at=job.updated_at,
        finished_at=job.finished_at,
    )


def _summary(
    account: object,
    credential: object | None = None,
    fixed_password: str = "",
) -> AccountSummary:
    value = AccountSummary.model_validate(account)
    if credential is None:
        return value
    metadata = getattr(credential, "metadata_json", {}) or {}
    security = metadata.get("account_security", {}) if isinstance(metadata, dict) else {}
    password = security.get("password", {}) if isinstance(security, dict) else {}
    mfa = security.get("mfa", {}) if isinstance(security, dict) else {}
    password_default = "set" if getattr(credential, "password", None) else "not_set"
    mfa_default = "enabled" if getattr(credential, "totp_secret", None) else "not_enabled"
    password_status = str(password.get("status") or password_default)
    stored_password = str(getattr(credential, "password", None) or "")
    return value.model_copy(
        update={
            "password_status": password_status,
            "mfa_status": str(mfa.get("status") or mfa_default),
            "security_error": str(mfa.get("error") or password.get("error") or "") or None,
            "chatgpt_password": stored_password
            or (fixed_password if password_status in {"set", "available"} else None),
            "totp_secret": getattr(credential, "totp_secret", None),
        }
    )


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
    security_filter: Literal["all", "incomplete", "complete"] = "all",
    search: str = "",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AccountListResponse:
    registration = SettingsService(db).registration_internal()
    fixed_password = registration.fixed_password if registration.password_mode == "fixed" else ""
    items, total = AccountRepository(db).list_page(
        status=account_status,
        security_filter=security_filter,
        fixed_password_available=bool(fixed_password),
        search=search,
        limit=limit,
        offset=offset,
    )
    credentials = AccountRepository(db).credentials([item.email for item in items])
    return AccountListResponse(
        items=[_summary(item, credentials.get(item.email), fixed_password) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/stats", response_model=AccountStats)
def get_account_stats(db: DatabaseSession) -> AccountStats:
    return AccountStats(**account_stats(AccountRepository(db)))


@router.get("/security-jobs", response_model=AccountSecurityJobListResponse)
def list_account_security_jobs(
    db: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AccountSecurityJobListResponse:
    filters = [Job.kind == "account.security"]
    total = db.scalar(select(func.count()).select_from(Job).where(*filters)) or 0
    jobs = list(
        db.scalars(
            select(Job)
            .where(*filters)
            .order_by(Job.created_at.desc(), Job.id)
            .limit(limit)
            .offset(offset)
        )
    )
    return AccountSecurityJobListResponse(
        items=[_security_job_summary(job) for job in jobs],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/security-jobs/{job_id}", response_model=AccountSecurityJobDetail)
def get_account_security_job(
    job_id: str,
    db: DatabaseSession,
) -> AccountSecurityJobDetail:
    job = db.get(Job, job_id)
    if job is None or job.kind != "account.security":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "账号安全任务不存在")
    events = list(
        db.scalars(
            select(JobEvent)
            .where(JobEvent.job_id == job.id)
            .order_by(JobEvent.sequence)
            .limit(5000)
        )
    )
    summary = _security_job_summary(job)
    return AccountSecurityJobDetail(
        **summary.model_dump(),
        events=[
            AccountSecurityJobEvent(
                id=event.id,
                sequence=event.sequence,
                level=event.level,
                event_type=event.event_type,
                message=event.message,
                data=event.data,
                created_at=event.created_at,
            )
            for event in events
        ],
    )


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
