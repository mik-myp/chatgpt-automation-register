from gpt_auto_register.db.models.kakao import KakaoTaskStatus
from gpt_auto_register.modules.pipelines.delivery import format_deliveries
from gpt_auto_register.modules.pipelines.schemas import PipelineDeliverySummary
from gpt_auto_register.modules.settings.schemas import DeliveryCopySettings


def _delivery(**overrides: object) -> PipelineDeliverySummary:
    values = {
        "task_id": "task-1",
        "upstream_job_id": "job-1",
        "email": "user@example.com",
        "task_status": KakaoTaskStatus.DONE,
        "payment_status": "ready",
        "payment_message": "等待扫码",
        "payment_url": "https://pay.example.com/checkout",
        "payment_expires_at": None,
        "card_charged": True,
        "mail_url": "https://mail.example.com/inbox",
        "chatgpt_password": "known-password",
        "totp_secret": "JBSWY3DPEHPK3PXP",
        "deliverable": True,
    }
    values.update(overrides)
    return PipelineDeliverySummary.model_validate(values)


def test_delivery_copy_formats_link_and_corresponding_account() -> None:
    text, copied, skipped = format_deliveries([_delivery()], DeliveryCopySettings())

    assert copied == 1
    assert skipped == 0
    assert text == (
        "第一个\n"
        "https://pay.example.com/checkout\n"
        "user@example.com --- https://mail.example.com/inbox --- "
        "known-password --- JBSWY3DPEHPK3PXP"
    )


def test_delivery_copy_skips_items_without_payment_link() -> None:
    text, copied, skipped = format_deliveries(
        [_delivery(payment_url=None, deliverable=False)], DeliveryCopySettings()
    )

    assert text == ""
    assert copied == 0
    assert skipped == 1
