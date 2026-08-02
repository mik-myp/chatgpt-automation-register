from gpt_auto_register.modules.kakao.client import (
    canonical_payment_url,
    normalized_payment_state,
)


def test_canonical_payment_url_uses_documented_priority() -> None:
    value = {
        "nicepay_checkout_url": "https://pay.example.com/nicepay",
        "kakao_pay_url": "https://pay.example.com/kakao",
        "provider_redirect_url": "https://pay.example.com/provider",
        "long_url": "https://pay.example.com/long",
        "link": "https://pay.example.com/legacy",
    }

    assert canonical_payment_url(value) == "https://pay.example.com/nicepay"
    assert canonical_payment_url({"link": value["link"]}) == value["link"]


def test_payment_state_applies_terminal_overrides() -> None:
    assert normalized_payment_state({"status": "READY"})["status"] == "ready"
    assert normalized_payment_state({"status": "OPENED"})["status"] == "opened"
    assert normalized_payment_state({"status": "AUTHENTICATED"})["status"] == "succeeded"
    assert (
        normalized_payment_state({"status": "COMPLETED", "need_redirect_fail_url": True})["status"]
        == "failed"
    )
    assert normalized_payment_state({"status": "OPENED", "expired": True})["status"] == "expired"
    assert (
        normalized_payment_state({"ok": True, "payment": {"status": "EXPIRED", "expired": True}})[
            "status"
        ]
        == "expired"
    )
