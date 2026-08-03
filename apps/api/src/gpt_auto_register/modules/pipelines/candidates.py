from collections.abc import Collection

from sqlalchemy import and_, case, exists, func, literal, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from gpt_auto_register.db.models.accounts import Credential, OutlookAccount
from gpt_auto_register.db.models.kakao import KakaoClaimState, KakaoEmailClaim


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
        Credential.metadata_json["account_security"]["password"]["status"].as_string(),
        case(
            (Credential.password.is_not(None), "set"),
            else_="not_set",
        ),
    )
    mfa_status = func.coalesce(
        Credential.metadata_json["account_security"]["mfa"]["status"].as_string(),
        case(
            (Credential.totp_secret.is_not(None), "enabled"),
            else_="not_enabled",
        ),
    )
    password_value_available = or_(
        Credential.password.is_not(None),
        literal(fixed_password_available),
    )
    password_complete = and_(
        password_status.in_(["set", "available"]),
        password_value_available,
    )
    mfa_complete = and_(
        Credential.totp_secret.is_not(None),
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
    completed_claim = exists(
        select(KakaoEmailClaim.email).where(
            func.lower(KakaoEmailClaim.email) == func.lower(Credential.email),
            KakaoEmailClaim.state == KakaoClaimState.COMPLETED,
        )
    )
    filters: list[ColumnElement[bool]] = [
        Credential.access_token.is_not(None),
        ~completed_claim,
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
