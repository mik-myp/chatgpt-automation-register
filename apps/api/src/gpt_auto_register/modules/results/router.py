from concurrent.futures import ThreadPoolExecutor
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, status

from gpt_auto_register.api.dependencies import DatabaseSession
from gpt_auto_register.db.base import utc_now
from gpt_auto_register.modules.results.plus_checker import check_plus
from gpt_auto_register.modules.results.repository import ResultRepository
from gpt_auto_register.modules.results.schemas import (
    BulkResultRequest,
    BulkResultResponse,
    ExportResultsResponse,
    PlusCheckItem,
    PlusCheckRequest,
    PlusCheckResponse,
    PublishResultsRequest,
    PublishResultsResponse,
    RegistrationResultDetail,
    RegistrationResultListResponse,
    RegistrationResultSummary,
    ResultTokenFilter,
)
from gpt_auto_register.modules.settings.service import SettingsService
from gpt_auto_register.worker.runtime_gateway import runtime_gateway

router = APIRouter(prefix="/results", tags=["registration-results"])


def _object_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _security_status(item: object, name: str) -> str | None:
    metadata = _object_dict(getattr(item, "metadata_json", {}))
    security = _object_dict(metadata.get("account_security"))
    outcome = _object_dict(security.get(name))
    status_value = outcome.get("status")
    return str(status_value) if status_value else None


def _fixed_password(db: DatabaseSession) -> str:
    registration = SettingsService(db).registration_internal()
    return registration.fixed_password if registration.password_mode == "fixed" else ""


def _password_value(item: object, fixed_password: str) -> str | None:
    stored = str(getattr(item, "password", None) or "")
    status_value = _security_status(item, "password")
    return stored or (fixed_password if status_value in {"set", "available"} else None)


def _detail(item: object, fixed_password: str) -> RegistrationResultDetail:
    detail = RegistrationResultDetail.model_validate(item)
    return detail.model_copy(update={"password": _password_value(item, fixed_password)})


def _plus_check(item: object) -> dict[str, Any]:
    metadata = _object_dict(getattr(item, "metadata_json", {}))
    return _object_dict(metadata.get("plus_check"))


def _summary(item: Any, fixed_password: str) -> RegistrationResultSummary:
    plus = _plus_check(item)
    is_plus = plus.get("is_plus")
    active_subscription = plus.get("has_active_subscription")
    password = _password_value(item, fixed_password)
    return RegistrationResultSummary(
        email=item.email,
        has_password=bool(password),
        chatgpt_password=password,
        totp_secret=item.totp_secret,
        has_access_token=bool(item.access_token),
        has_session_token=bool(item.session_token),
        has_refresh_token=bool(item.refresh_token),
        password_status=_security_status(item, "password"),
        mfa_status=_security_status(item, "mfa"),
        plus_state=str(plus.get("state") or "") or None,
        plus_label=str(plus.get("label") or "") or None,
        plus_is_active=is_plus if isinstance(is_plus, bool) else None,
        plus_error=str(plus.get("error") or "") or None,
        plus_checked_at=plus.get("checked_at"),
        plus_plan_type=str(plus.get("plan_type") or "") or None,
        plus_subscription_plan=str(plus.get("subscription_plan") or "") or None,
        plus_has_active_subscription=(
            active_subscription if isinstance(active_subscription, bool) else None
        ),
        plus_expires_at=str(plus.get("expires_at") or "") or None,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.get("", response_model=RegistrationResultListResponse)
def list_results(
    db: DatabaseSession,
    search: str = "",
    token_filter: ResultTokenFilter = "all",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RegistrationResultListResponse:
    items, total = ResultRepository(db).list_page(
        search=search.strip(),
        token_filter=token_filter,
        limit=limit,
        offset=offset,
    )
    fixed_password = _fixed_password(db)
    summaries = [_summary(item, fixed_password) for item in items]
    return RegistrationResultListResponse(
        items=summaries,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/export", response_model=ExportResultsResponse)
def export_results(request: BulkResultRequest, db: DatabaseSession) -> ExportResultsResponse:
    emails = list(dict.fromkeys(email.lower() for email in request.emails if email.strip()))
    if not request.all and not emails:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "请选择要导出的注册结果")
    fixed_password = _fixed_password(db)
    return ExportResultsResponse(
        items=[
            _detail(item, fixed_password)
            for item in ResultRepository(db).export(emails, request.all)
        ]
    )


@router.post("/publish", response_model=PublishResultsResponse)
def publish_results(
    request: PublishResultsRequest,
    db: DatabaseSession,
) -> PublishResultsResponse:
    emails = list(dict.fromkeys(email.lower() for email in request.emails if email.strip()))
    if not request.all and not emails:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "请选择要发布的注册结果")
    values = ResultRepository(db).export(emails, request.all)
    export = SettingsService(db).export_internal()
    for name in ("cpa", "sub2api"):
        export[name]["enabled"] = name in request.targets
    succeeded = failed = 0
    errors: list[str] = []
    for value in values:
        result = runtime_gateway.call(
            {
                "action": "export",
                "credential": RegistrationResultDetail.model_validate(value).model_dump(
                    mode="json", exclude={"totp_secret"}
                ),
                "export": export,
            },
            timeout=300,
        )
        target_results = dict(result.get("results") or {})
        failures = [
            f"{value.email} / {target}: {target_results.get(target, {}).get('error', '导出失败')}"
            for target in request.targets
            if not target_results.get(target, {}).get("ok")
        ]
        if result.get("ok") and not failures:
            succeeded += 1
        else:
            failed += 1
            errors.extend(failures or [f"{value.email}: {result.get('error', '导出失败')}"])
    return PublishResultsResponse(
        processed=len(values),
        succeeded=succeeded,
        failed=failed,
        errors=errors[:20],
    )


@router.post("/check-plus", response_model=PlusCheckResponse)
def check_plus_results(
    request: PlusCheckRequest,
    db: DatabaseSession,
) -> PlusCheckResponse:
    emails = list(
        dict.fromkeys(email.strip().lower() for email in request.emails if email.strip())
    )
    if not request.all and not emails:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "请选择要检查的注册结果")
    values = ResultRepository(db).export(emails, request.all)
    by_email = {value.email: value for value in values}
    selected_emails = list(by_email) if request.all else emails
    proxy = request.proxy.strip() or SettingsService(db).registration_internal().proxy.strip()
    jobs = [
        (email, str(by_email[email].access_token), proxy)
        for email in selected_emails
        if email in by_email and by_email[email].access_token
    ]
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(jobs)))) as executor:
        checked = list(executor.map(lambda args: check_plus(args[1], args[2]), jobs))
    checked_by_email = {
        email: result for (email, _, _), result in zip(jobs, checked, strict=True)
    }
    checked_at = utc_now().isoformat()
    items: list[PlusCheckItem] = []
    for email in selected_emails:
        credential = by_email.get(email)
        if credential is None:
            result: dict[str, object] = {
                "state": "not_found",
                "label": "未找到",
                "is_plus": None,
                "error": "注册结果不存在",
            }
        elif not credential.access_token:
            result = {
                "state": "no_access_token",
                "label": "无 Access Token",
                "is_plus": None,
                "error": "",
            }
        else:
            result = checked_by_email[email]
        item = PlusCheckItem.model_validate({"email": email, **result})
        items.append(item)
        if credential is not None:
            credential.metadata_json = {
                **(credential.metadata_json or {}),
                "plus_check": {**result, "checked_at": checked_at},
            }
    db.commit()
    return PlusCheckResponse(items=items)


@router.post("/batch-delete", response_model=BulkResultResponse)
def delete_results(request: BulkResultRequest, db: DatabaseSession) -> BulkResultResponse:
    emails = list(dict.fromkeys(email.lower() for email in request.emails if email.strip()))
    if not request.all and not emails:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "请选择要删除的注册结果")
    processed = ResultRepository(db).delete(emails, request.all)
    db.commit()
    return BulkResultResponse(processed=processed)


@router.get("/{email}", response_model=RegistrationResultDetail)
def get_result(email: str, db: DatabaseSession) -> RegistrationResultDetail:
    result = ResultRepository(db).get(email)
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "注册结果不存在")
    return _detail(result, _fixed_password(db))
