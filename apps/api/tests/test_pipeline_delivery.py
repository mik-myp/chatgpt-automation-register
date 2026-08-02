import pytest
from pydantic import ValidationError

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
        "password_status": "set",
        "mfa_status": "enabled",
        "account_format": "security_credentials",
        "account_missing_reason": None,
        "deliverable": True,
    }
    values.update(overrides)
    return PipelineDeliverySummary.model_validate(values)


def test_delivery_copy_formats_payment_links_separately() -> None:
    text, copied, skipped, *_ = format_deliveries(
        [_delivery()], DeliveryCopySettings(), "payment_links"
    )

    assert copied == 1
    assert skipped == 0
    assert text == "第一个\nhttps://pay.example.com/checkout"


def test_delivery_copy_formats_account_info_separately() -> None:
    text, copied, skipped, *_ = format_deliveries(
        [_delivery()], DeliveryCopySettings(), "account_info"
    )
    assert copied == 1
    assert skipped == 0
    assert text == ("user@example.com --- known-password --- JBSWY3DPEHPK3PXP")


def test_delivery_copy_can_require_confirmed_plus() -> None:
    settings = DeliveryCopySettings(only_copy_plus=True)
    values = [
        _delivery(plus_state="plus", plus_is_active=True),
        _delivery(
            task_id="task-2",
            email="free@example.com",
            plus_state="free",
            plus_is_active=False,
        ),
        _delivery(
            task_id="task-3",
            email="unchecked@example.com",
            plus_state=None,
            plus_is_active=None,
        ),
    ]

    result = format_deliveries(values, settings, "account_info")

    assert result[1] == 1
    assert result[2] == 2
    assert result[7] == 2
    assert "user@example.com" in result[0]
    assert "free@example.com" not in result[0]


def test_plus_only_setting_does_not_filter_payment_links() -> None:
    result = format_deliveries(
        [_delivery(plus_state="free", plus_is_active=False)],
        DeliveryCopySettings(only_copy_plus=True),
        "payment_links",
    )

    assert result[1] == 1
    assert result[7] == 0


def test_delivery_copy_skips_items_without_payment_link() -> None:
    text, copied, skipped, *_ = format_deliveries(
        [_delivery(payment_url=None, deliverable=False)],
        DeliveryCopySettings(),
        "payment_links",
    )

    assert text == ""
    assert copied == 0
    assert skipped == 1


def test_delivery_copy_rejects_mixed_payment_and_account_fields() -> None:
    with pytest.raises(ValidationError, match="支付链接配置只能包含支付链接字段"):
        DeliveryCopySettings.model_validate(
            {
                "payment_links": {
                    "rows": [{"fields": ["payment_url", "email"]}],
                },
                "account_info": {
                    "rows": [{"fields": ["email"]}],
                },
            }
        )
