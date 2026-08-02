from collections.abc import Collection

from sqlalchemy import and_, exists, func, literal, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from gpt_auto_register.db.models.accounts import Credential, OutlookAccount
from gpt_auto_register.db.models.kakao import KakaoTask


def _search_filter(search: str) -> ColumnElement[bool] | None:
    value = search.strip().lower()
    if not value:
        return None
    return func.lower(Credential.email).like(f"%{value}%")


def list_security_candidate_credentials(
    session: Session,
    *,
    busy_emails: Collection[str],
    fixed_password_available: bool,
    search: str,
    limit: int,
    offset: int,
) -> tuple[list[Credential], int]:
    password_status = func.coalesce(
        func.json_extract(Credential.metadata_json, "$.account_security.password.status"),
        func.iif(
            and_(Credential.password.is_not(None), Credential.password != ""),
            "set",
            "not_set",
        ),
    )
    mfa_status = func.coalesce(
        func.json_extract(Credential.metadata_json, "$.account_security.mfa.status"),
        func.iif(
            and_(Credential.totp_secret.is_not(None), Credential.totp_secret != ""),
            "enabled",
            "not_enabled",
        ),
    )
    password_value_available = or_(
        and_(Credential.password.is_not(None), Credential.password != ""),
        literal(fixed_password_available),
    )
    password_complete = and_(
        password_status.in_(["set", "available"]),
        password_value_available,
    )
    mfa_complete = and_(
        Credential.totp_secret.is_not(None),
        Credential.totp_secret != "",
        mfa_status == "enabled",
    )
    filters: list[ColumnElement[bool]] = [or_(~password_complete, ~mfa_complete)]
    search_filter = _search_filter(search)
    if search_filter is not None:
        filters.append(search_filter)
    if busy_emails:
        filters.append(~func.lower(Credential.email).in_(busy_emails))

    base = (
        select(Credential)
        .join(OutlookAccount, OutlookAccount.email == Credential.email)
        .where(*filters)
    )
    total = session.scalar(select(func.count()).select_from(base.order_by(None).subquery())) or 0
    items = list(session.scalars(base.order_by(Credential.email).limit(limit).offset(offset)))
    return items, total


def list_kakao_candidate_credentials(
    session: Session,
    *,
    busy_emails: Collection[str],
    search: str,
    limit: int,
    offset: int,
) -> tuple[list[Credential], int]:
    payment_fields = (
        "nicepay_checkout_url",
        "kakao_pay_url",
        "provider_redirect_url",
        "long_url",
        "link",
        "payment_url",
    )
    completed_task = exists(
        select(KakaoTask.id).where(
            func.lower(KakaoTask.email) == func.lower(Credential.email),
            or_(
                and_(KakaoTask.payment_url.is_not(None), KakaoTask.payment_url != ""),
                *[
                    func.coalesce(
                        func.json_extract(KakaoTask.upstream_payload, f"$.{field}"),
                        "",
                    )
                    != ""
                    for field in payment_fields
                ],
            ),
        )
    )
    extraction_completed = (
        func.coalesce(
            func.json_extract(Credential.metadata_json, "$.kakao_extraction.completed"),
            0,
        )
        == 1
    )
    filters: list[ColumnElement[bool]] = [
        Credential.access_token.is_not(None),
        Credential.access_token != "",
        ~extraction_completed,
        ~completed_task,
    ]
    search_filter = _search_filter(search)
    if search_filter is not None:
        filters.append(search_filter)
    if busy_emails:
        filters.append(~func.lower(Credential.email).in_(busy_emails))

    base = select(Credential).where(*filters)
    total = session.scalar(select(func.count()).select_from(base.order_by(None).subquery())) or 0
    items = list(session.scalars(base.order_by(Credential.email).limit(limit).offset(offset)))
    return items, total
