from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from gpt_auto_register.db.models.accounts import Credential, OutlookAccount
from gpt_auto_register.db.models.kakao import KakaoTask
from gpt_auto_register.modules.kakao.client import canonical_payment_url
from gpt_auto_register.modules.pipelines.schemas import PipelineDeliverySummary
from gpt_auto_register.modules.settings.schemas import DeliveryCopySettings

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


def list_deliveries(
    session: Session,
    run_id: str,
    *,
    task_ids: list[str] | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> DeliveryPage:
    filters = [KakaoTask.pipeline_run_id == run_id]
    if task_ids is not None:
        filters.append(KakaoTask.id.in_(task_ids))
    total = session.scalar(select(func.count()).select_from(KakaoTask).where(*filters)) or 0
    query = (
        select(KakaoTask, OutlookAccount, Credential)
        .outerjoin(OutlookAccount, OutlookAccount.email == KakaoTask.email)
        .outerjoin(Credential, Credential.email == KakaoTask.email)
        .where(*filters)
        .order_by(KakaoTask.created_at, KakaoTask.id)
        .offset(offset)
    )
    if limit is not None:
        query = query.limit(limit)
    items = []
    for task, account, credential in session.execute(query):
        payment_url = task.payment_url or canonical_payment_url(task.upstream_payload or {}) or None
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
                mail_url=account.mail_url if account is not None else None,
                chatgpt_password=credential.password if credential is not None else None,
                totp_secret=credential.totp_secret if credential is not None else None,
                deliverable=(
                    task.status.value == "done"
                    and bool(payment_url)
                    and task.payment_status not in {"failed", "canceled", "expired"}
                ),
            )
        )
    return DeliveryPage(items=items, total=total)


def format_deliveries(
    items: list[PipelineDeliverySummary], settings: DeliveryCopySettings
) -> tuple[str, int, int]:
    blocks: list[str] = []
    skipped = 0
    for item in items:
        if not item.deliverable:
            skipped += 1
            continue
        values = item.model_dump()
        lines: list[str] = []
        incomplete = False
        for row in settings.rows:
            parts: list[str] = []
            for field in row.fields:
                value = str(values.get(field) or "")
                if not value:
                    if settings.missing_policy == "skip":
                        incomplete = True
                        break
                    value = settings.placeholder
                if settings.show_labels:
                    value = f"{FIELD_LABELS[field]}: {value}"
                parts.append(value)
            if incomplete:
                break
            lines.append(row.separator.join(parts))
        if incomplete:
            skipped += 1
            continue
        index = len(blocks) + 1
        prefix = _sequence_label(index, settings.sequence_style)
        blocks.append("\n".join([prefix, *lines] if prefix else lines))
    separator = "\n\n" if settings.record_separator == "blank_line" else "\n"
    return separator.join(blocks), len(blocks), skipped


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
