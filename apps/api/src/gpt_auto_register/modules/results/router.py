from concurrent.futures import ThreadPoolExecutor
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, status

from gpt_auto_register.api.dependencies import DatabaseSession
from gpt_auto_register.db.base import utc_now
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
from gpt_auto_register.worker.manager import _legacy_call

router = APIRouter(prefix="/results", tags=["registration-results"])


def _object_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _security_status(item: object, name: str) -> str | None:
    metadata = _object_dict(getattr(item, "metadata_json", {}))
    security = _object_dict(metadata.get("account_security"))
    outcome = _object_dict(security.get(name))
    status_value = outcome.get("status")
    return str(status_value) if status_value else None


def _check_plus_token(email: str, access_token: str, proxy: str) -> PlusCheckItem:
    from curl_cffi import requests as cffi_requests

    try:
        proxies: Any = {"http": proxy, "https": proxy} if proxy else None
        response = cffi_requests.get(
            "https://chatgpt.com/backend-api/accounts/check/v4-2023-04-27",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/145.0.0.0 Safari/537.36"
                ),
            },
            proxies=proxies,
            impersonate="chrome110",
            timeout=15,
        )
        if response.status_code == 401:
            return PlusCheckItem(
                email=email,
                status="banned",
                label="封号",
                eligible=False,
            )
        if response.status_code != 200:
            return PlusCheckItem(
                email=email,
                status="error",
                label="检查失败",
                error=f"HTTP {response.status_code}",
            )
        payload: dict[str, Any] = response.json()  # type: ignore[no-untyped-call]
        accounts = payload.get("accounts")
        if not isinstance(accounts, dict) or not accounts:
            return PlusCheckItem(
                email=email,
                status="error",
                label="检查失败",
                error="响应中没有账号数据",
            )
        info = _object_dict(next(iter(accounts.values())))
        account = _object_dict(info.get("account"))
        entitlement = _object_dict(info.get("entitlement"))
        campaigns = _object_dict(info.get("eligible_promo_campaigns"))
        if account.get("is_deactivated") is True:
            return PlusCheckItem(
                email=email,
                status="banned",
                label="封号",
                eligible=False,
            )
        plus_campaign = campaigns.get("plus")
        has_promo = (
            isinstance(plus_campaign, dict) and plus_campaign.get("id") == "plus-1-month-free"
        )
        if account.get("plan_type") == "plus" or entitlement.get("has_active_subscription"):
            return PlusCheckItem(
                email=email,
                status="plus_active",
                label="Plus 生效中",
                eligible=True,
            )
        if has_promo:
            return PlusCheckItem(
                email=email,
                status="plus_eligible",
                label="可领 Plus 试用",
                eligible=True,
            )
        return PlusCheckItem(
            email=email,
            status="free",
            label="Free",
            eligible=False,
        )
    except Exception as error:
        return PlusCheckItem(
            email=email,
            status="error",
            label="检查失败",
            error=str(error),
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
    summaries = [
        RegistrationResultSummary(
            email=item.email,
            has_password=bool(item.password),
            has_access_token=bool(item.access_token),
            has_session_token=bool(item.session_token),
            has_refresh_token=bool(item.refresh_token),
            password_status=_security_status(item, "password"),
            mfa_status=_security_status(item, "mfa"),
            plus_eligible=(
                item.metadata_json.get("plus_eligible")
                if isinstance(item.metadata_json.get("plus_eligible"), bool)
                else None
            ),
            plus_state=str(item.metadata_json.get("plus_state") or "") or None,
            plus_error=str(item.metadata_json.get("plus_error") or "") or None,
            plus_checked_at=item.metadata_json.get("plus_checked_at"),
            created_at=item.created_at,
            updated_at=item.updated_at,
        )
        for item in items
    ]
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
    return ExportResultsResponse(
        items=[
            RegistrationResultDetail.model_validate(item)
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
        result = _legacy_call(
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
def check_plus(
    request: PlusCheckRequest,
    db: DatabaseSession,
) -> PlusCheckResponse:
    emails = list(dict.fromkeys(email.strip().lower() for email in request.emails if email.strip()))
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
    workers = min(8, max(1, len(jobs)))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        checked = list(executor.map(lambda args: _check_plus_token(*args), jobs))
    checked_by_email = {item.email: item for item in checked}
    items: list[PlusCheckItem] = []
    checked_at = utc_now().isoformat()
    for email in selected_emails:
        credential = by_email.get(email)
        if credential is None:
            items.append(PlusCheckItem(email=email, status="not_found", label="未找到"))
            continue
        item = checked_by_email.get(email)
        if item is None:
            item = PlusCheckItem(email=email, status="no_at", label="无 Access Token")
        items.append(item)
        credential.metadata_json = {
            **credential.metadata_json,
            "plus_eligible": item.eligible,
            "plus_state": item.status,
            "plus_label": item.label,
            "plus_error": item.error,
            "plus_checked_at": checked_at,
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
    return RegistrationResultDetail.model_validate(result)
