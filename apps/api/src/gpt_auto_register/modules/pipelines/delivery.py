import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, TypedDict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from gpt_auto_register.db.models.accounts import Credential, OutlookAccount
from gpt_auto_register.db.models.kakao import KakaoTask, KakaoTaskStatus
from gpt_auto_register.db.models.pipeline import PipelineItem
from gpt_auto_register.modules.kakao.client import canonical_payment_url
from gpt_auto_register.modules.pipelines.schemas import PipelineDeliverySummary
from gpt_auto_register.modules.settings.schemas import DeliveryCopySettings, DeliveryCopyType

FIELD_LABELS = {
    "payment_url": "支付链接",
    "email": "邮箱",
    "mail_url": "邮件查询地址",
    "chatgpt_password": "ChatGPT 密码",
    "totp_secret": "Authenticator 密钥",
}


@dataclass(frozen=True)
class DeliveryPage:
    items: list[PipelineDeliverySummary]
    total: int


class PlusCheckFields(TypedDict):
    plus_state: str | None
    plus_label: str | None
    plus_is_active: bool | None
    plus_error: str | None
    plus_checked_at: datetime | None


def _security_status(credential: Credential | None, name: str, fallback: str) -> str:
    if credential is None:
        return fallback
    metadata = credential.metadata_json if isinstance(credential.metadata_json, dict) else {}
    security = metadata.get("account_security")
    security = security if isinstance(security, dict) else {}
    outcome = security.get(name)
    outcome = outcome if isinstance(outcome, dict) else {}
    return str(outcome.get("status") or fallback)


def plus_check_fields(credential: Credential | None) -> PlusCheckFields:
    metadata = (
        credential.metadata_json
        if credential is not None and isinstance(credential.metadata_json, dict)
        else {}
    )
    plus_check = metadata.get("plus_check")
    plus_check = plus_check if isinstance(plus_check, dict) else {}
    checked_at = plus_check.get("checked_at")
    parsed_checked_at: datetime | None = None
    if checked_at:
        try:
            parsed_checked_at = datetime.fromisoformat(str(checked_at).replace("Z", "+00:00"))
        except ValueError:
            parsed_checked_at = None
    is_plus = plus_check.get("is_plus")
    return {
        "plus_state": str(plus_check.get("state") or "") or None,
        "plus_label": str(plus_check.get("label") or "") or None,
        "plus_is_active": is_plus if isinstance(is_plus, bool) else None,
        "plus_error": str(plus_check.get("error") or "") or None,
        "plus_checked_at": parsed_checked_at,
    }


def list_deliveries(
    session: Session,
    run_id: str,
    *,
    fixed_password: str = "",
    task_ids: list[str] | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> DeliveryPage:
    filters = [KakaoTask.pipeline_run_id == run_id]
    if task_ids is not None:
        filters.append(KakaoTask.id.in_(task_ids))
    total = session.scalar(select(func.count()).select_from(KakaoTask).where(*filters)) or 0
    query = (
        select(KakaoTask, PipelineItem, OutlookAccount, Credential)
        .outerjoin(PipelineItem, PipelineItem.id == KakaoTask.pipeline_item_id)
        .outerjoin(OutlookAccount, OutlookAccount.email == KakaoTask.email)
        .outerjoin(Credential, Credential.email == KakaoTask.email)
        .where(*filters)
        .order_by(KakaoTask.created_at, KakaoTask.id)
        .offset(offset)
    )
    if limit is not None:
        query = query.limit(limit)
    items = []
    for task, pipeline_item, account, credential in session.execute(query):
        payment_url = task.payment_url or canonical_payment_url(task.upstream_payload or {}) or None
        mail_url = (
            pipeline_item.mail_url_snapshot
            if pipeline_item is not None and pipeline_item.mail_url_snapshot
            else account.mail_url
            if account is not None
            else None
        )
        password_status = _security_status(credential, "password", "not_set")
        mfa_status = _security_status(credential, "mfa", "not_enabled")
        stored_password = credential.password if credential is not None else None
        chatgpt_password = stored_password or (
            fixed_password if password_status in {"set", "available"} else None
        )
        totp_secret = credential.totp_secret if credential is not None else None
        security_ready = (
            bool(chatgpt_password)
            and password_status in {"set", "available"}
            and bool(totp_secret)
            and mfa_status == "enabled"
        )
        account_format: Literal["security_credentials", "mail_access", "unavailable"] = (
            "security_credentials"
            if security_ready
            else "mail_access"
            if mail_url
            else "unavailable"
        )
        payment_copyable = task.status == KakaoTaskStatus.DONE and bool(payment_url)
        account_copyable = account_format != "unavailable"
        items.append(
            PipelineDeliverySummary(
                task_id=task.id,
                upstream_job_id=task.upstream_job_id,
                email=task.email,
                task_status=task.status,
                payment_status=task.payment_status,
                payment_message=task.payment_message,
                payment_url=payment_url,
                payment_expires_at=task.payment_expires_at,
                card_charged=task.card_charged,
                mail_url=mail_url,
                chatgpt_password=chatgpt_password,
                totp_secret=totp_secret,
                password_status=password_status,
                mfa_status=mfa_status,
                account_format=account_format,
                account_missing_reason=(
                    "密码或 MFA 未全部完成，且缺少邮件查询地址"
                    if account_format == "unavailable"
                    else None
                ),
                payment_copyable=payment_copyable,
                account_copyable=account_copyable,
                deliverable=payment_copyable or account_copyable,
                **plus_check_fields(credential),
            )
        )
    return DeliveryPage(items=items, total=total)


def list_security_deliveries(
    session: Session,
    run_id: str,
    *,
    fixed_password: str = "",
    item_ids: list[str] | None = None,
) -> DeliveryPage:
    filters = [PipelineItem.pipeline_run_id == run_id]
    if item_ids is not None:
        filters.append(PipelineItem.id.in_(item_ids))
    rows = list(
        session.execute(
            select(PipelineItem, Credential)
            .outerjoin(Credential, Credential.email == PipelineItem.account_email)
            .where(*filters)
            .order_by(PipelineItem.position)
        )
    )
    items: list[PipelineDeliverySummary] = []
    for pipeline_item, credential in rows:
        email = str(pipeline_item.account_email or "")
        password_status = _security_status(credential, "password", "not_set")
        mfa_status = _security_status(credential, "mfa", "not_enabled")
        stored_password = credential.password if credential is not None else None
        password = stored_password or (
            fixed_password if password_status in {"set", "available"} else None
        )
        secret = credential.totp_secret if credential is not None else None
        security_ready = (
            bool(password)
            and password_status in {"set", "available"}
            and bool(secret)
            and mfa_status == "enabled"
        )
        items.append(
            PipelineDeliverySummary(
                task_id=pipeline_item.id,
                upstream_job_id="",
                email=email,
                task_status=KakaoTaskStatus.DONE,
                payment_status=None,
                payment_message=None,
                payment_url=None,
                payment_expires_at=None,
                card_charged=None,
                mail_url=None,
                chatgpt_password=password,
                totp_secret=secret,
                password_status=password_status,
                mfa_status=mfa_status,
                account_format="security_credentials" if security_ready else "unavailable",
                account_missing_reason=None if security_ready else "密码或 MFA 尚未全部完成",
                payment_copyable=False,
                account_copyable=security_ready,
                deliverable=security_ready,
                **plus_check_fields(credential),
            )
        )
    return DeliveryPage(items=items, total=len(items))


def account_copy_fingerprint(item: PipelineDeliverySummary) -> str:
    if item.account_format == "security_credentials":
        values = [item.email, item.chatgpt_password or "", item.totp_secret or ""]
    elif item.account_format == "mail_access":
        values = [item.email, item.mail_url or ""]
    else:
        return ""
    return hashlib.sha256("\0".join(values).encode("utf-8")).hexdigest()


def format_deliveries(
    items: list[PipelineDeliverySummary],
    settings: DeliveryCopySettings,
    copy_type: DeliveryCopyType,
    copied_account_fingerprints: dict[str, str] | None = None,
) -> tuple[str, int, int, int, int, int, int, int, list[tuple[str, str]]]:
    blocks: list[str] = []
    separators: list[str] = []
    skipped = 0
    security_credentials = 0
    mail_access = 0
    missing_mail_url = 0
    duplicates = 0
    plus_restricted = 0
    seen: set[str] = set()
    copy_marks: list[tuple[str, str]] = []
    copied_account_fingerprints = copied_account_fingerprints or {}
    for item in items:
        copyable = item.payment_copyable if copy_type == "payment_links" else item.account_copyable
        if not copyable:
            skipped += 1
            continue
        if copy_type == "account_info":
            if settings.only_copy_plus and not (
                item.plus_state == "plus" and item.plus_is_active is True
            ):
                skipped += 1
                plus_restricted += 1
                continue
            if item.account_format == "unavailable":
                skipped += 1
                missing_mail_url += 1
                continue
            format_settings = getattr(settings, item.account_format)
            identity = item.email.strip().lower()
            fingerprint = account_copy_fingerprint(item)
            if copied_account_fingerprints.get(identity) == fingerprint:
                skipped += 1
                duplicates += 1
                continue
        else:
            format_settings = settings.payment_links
            identity = str(item.payment_url or "").strip()
            fingerprint = ""
        if not identity:
            skipped += 1
            continue
        if identity in seen:
            skipped += 1
            duplicates += 1
            continue
        values = item.model_dump()
        lines: list[str] = []
        incomplete = False
        for row in format_settings.rows:
            parts: list[str] = []
            for field in row.fields:
                value = str(values.get(field) or "")
                if not value:
                    if format_settings.missing_policy == "skip":
                        incomplete = True
                        break
                    value = format_settings.placeholder
                if format_settings.show_labels:
                    value = f"{FIELD_LABELS[field]}: {value}"
                parts.append(value)
            if incomplete:
                break
            lines.append(row.separator.join(parts))
        if incomplete:
            skipped += 1
            continue
        seen.add(identity)
        index = len(blocks) + 1
        prefix = _sequence_label(index, format_settings.sequence_style)
        blocks.append("\n".join([prefix, *lines] if prefix else lines))
        separators.append("\n\n" if format_settings.record_separator == "blank_line" else "\n")
        if copy_type == "account_info":
            copy_marks.append((identity, fingerprint))
            if item.account_format == "security_credentials":
                security_credentials += 1
            else:
                mail_access += 1
    text = ""
    for index, block in enumerate(blocks):
        text += (separators[index] if index else "") + block
    return (
        text,
        len(blocks),
        skipped,
        security_credentials,
        mail_access,
        missing_mail_url,
        duplicates,
        plus_restricted,
        copy_marks,
    )


def _sequence_label(index: int, style: str) -> str:
    if style == "number":
        return f"{index}."
    if style == "chinese_number":
        return f"第{index}个"
    if style == "chinese":
        return f"第{_chinese_number(index)}个"
    return ""


def _chinese_number(value: int) -> str:
    digits = "零一二三四五六七八九"
    if value < 10:
        return digits[value]
    if value < 20:
        return "十" + (digits[value % 10] if value % 10 else "")
    if value < 100:
        return digits[value // 10] + "十" + (digits[value % 10] if value % 10 else "")
    return str(value)
