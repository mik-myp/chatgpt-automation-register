from gpt_auto_register.core.redaction import REDACTED, redact_text, redact_value


def test_redacts_contextual_otp_without_hiding_unrelated_numbers() -> None:
    value = redact_text("获取 OTP 成功: 123456；任务编号 654321")
    assert f"OTP 成功: {REDACTED}" in value
    assert "任务编号 654321" in value
    assert "123456" not in value


def test_redacts_tokens_passwords_and_nested_values() -> None:
    value = redact_value(
        {
            "email": "user@example.com",
            "password": "known-password",
            "nested": {
                "totp_secret": "JBSWY3DPEHPK3PXP",
                "message": "Authorization: Bearer secret.jwt.value",
            },
        }
    )
    assert value["email"] == "user@example.com"
    assert value["password"] == REDACTED
    assert value["nested"]["totp_secret"] == REDACTED
    assert "secret.jwt.value" not in value["nested"]["message"]


def test_redacted_text_is_bounded() -> None:
    value = redact_text("x" * 20, limit=10)
    assert len(value) == 10
    assert value.endswith("…")
