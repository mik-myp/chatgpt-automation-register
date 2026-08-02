from gpt_auto_register.runtime.auth_phone import AuthPhoneMixin


class _PhoneFlow(AuthPhoneMixin):
    _sms_callback = None

    @staticmethod
    def _extract_page_type(response: dict) -> str:
        return str(response["page"]["type"])

    @staticmethod
    def _extract_continue_url_from_step(response: dict) -> str:
        return str(response.get("continue_url") or "")

    @staticmethod
    def _normalize_continue_url(url: str) -> str:
        return url

    @staticmethod
    def _add_phone_send(phone: str) -> dict:
        assert phone == "+15550000001"
        return {"page": {"type": "phone_otp_verification"}}

    @staticmethod
    def _phone_otp_validate(code: str) -> dict:
        assert code == "123456"
        return {}


class _Controller:
    provider_key = "test"
    config = {
        "sms_max_phone_attempts": 1,
        "sms_code_retries_per_phone": 1,
    }

    def get_phone(self) -> str:
        return "+15550000001"

    def mark_send_succeeded(self) -> None:
        return None

    def get_code(self, *, timeout: int) -> str:
        assert timeout > 0
        return "123456"

    def report_success(self) -> None:
        return None


def test_extract_phone_otp_ignores_non_six_digit_values() -> None:
    assert AuthPhoneMixin._extract_otp6("code: 123456") == "123456"
    assert AuthPhoneMixin._extract_otp6("code: 12345") == ""
    assert AuthPhoneMixin._extract_otp6("code: 0123456") == ""


def test_sms_loop_keeps_original_continue_url_when_validation_has_no_next_url() -> None:
    flow = _PhoneFlow()

    assert flow._do_sms_loop(_Controller(), "https://auth.openai.com/original") == (
        "https://auth.openai.com/original"
    )
