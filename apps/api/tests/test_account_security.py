from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from gpt_auto_register.runtime.account_security import password_outcome, security_outcome


class FakeResponse:
    def __init__(self, payload: dict[str, Any], status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code

    def json(self) -> dict[str, Any]:
        return self.payload


class FakeSession:
    def __init__(self) -> None:
        self.posts: list[tuple[str, dict[str, Any]]] = []
        self.gets: list[str] = []

    def post(self, url: str, **kwargs: Any) -> FakeResponse:
        self.posts.append((url, kwargs))
        if url.endswith(
            "/api/auth/signin/openai?connection=password&login_hint=user%40example.com&reauth=password&max_age=0&ext-oai-did=device"
        ):
            return FakeResponse({"url": "https://auth.openai.com/authorize"})
        if url.endswith("/api/accounts/email-otp/validate"):
            return FakeResponse({"continue_url": "https://chatgpt.com/api/auth/callback/openai"})
        if url.endswith("/backend-api/accounts/mfa/enroll"):
            return FakeResponse({"secret": "JBSWY3DPEHPK3PXP", "session_id": "enrollment"})
        if url.endswith("/backend-api/accounts/mfa/user/activate_enrollment"):
            return FakeResponse({"success": True})
        raise AssertionError(f"unexpected POST {url}")

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.gets.append(url)
        return FakeResponse({})


class FakeMail:
    def wait_for_otp(self, email: str, **kwargs: Any) -> str:
        assert email == "user@example.com"
        assert kwargs["timeout"] == 180
        return "123456"


class FakeFlow:
    def __init__(self) -> None:
        self.password_registration_status = "set"
        self.result = SimpleNamespace(
            email="user@example.com",
            password="generated-password",
            device_id="device",
        )
        self.session = FakeSession()

    def get_csrf_token(self) -> str:
        return "csrf-token"

    def _common_headers(self, referer: str) -> dict[str, str]:
        return {"Referer": referer}

    def get_auth_session(self) -> tuple[str, str]:
        return "session-token", "access-token"


def test_password_outcome_marks_passwordless_as_unsupported() -> None:
    flow = FakeFlow()
    flow.password_registration_status = "unsupported"
    flow.result.password = ""

    outcome = password_outcome(flow, requested=True)

    assert outcome["status"] == "unsupported"
    assert "passwordless_signup" in outcome["error"]


def test_security_outcome_enrolls_and_activates_totp_without_logging_secrets(
    caplog: Any,
) -> None:
    flow = FakeFlow()

    outcome = security_outcome(
        flow,
        FakeMail(),
        {"set_password": True, "enable_authenticator_mfa": True, "otp_timeout": 180},
    )

    assert outcome["password"]["status"] == "set"
    assert outcome["mfa"]["status"] == "enabled"
    assert outcome["totp_secret"] == "JBSWY3DPEHPK3PXP"
    assert [url.rsplit("/", 1)[-1].split("?", 1)[0] for url, _ in flow.session.posts] == [
        "openai",
        "validate",
        "enroll",
        "activate_enrollment",
    ]
    activation_body = flow.session.posts[-1][1]["json"]
    assert activation_body["session_id"] == "enrollment"
    assert len(activation_body["code"]) == 6
    assert "JBSWY3DPEHPK3PXP" not in caplog.text
    assert activation_body["code"] not in caplog.text
    assert "123456" not in caplog.text


def test_security_outcome_records_mfa_failure_without_secret() -> None:
    flow = FakeFlow()
    original_post = flow.session.post

    def failing_post(url: str, **kwargs: Any) -> FakeResponse:
        if url.endswith("/backend-api/accounts/mfa/enroll"):
            return FakeResponse({}, status_code=409)
        return original_post(url, **kwargs)

    flow.session.post = failing_post  # type: ignore[method-assign]
    outcome = security_outcome(
        flow,
        FakeMail(),
        {"set_password": True, "enable_authenticator_mfa": True, "otp_timeout": 180},
    )

    assert outcome["mfa"]["status"] == "failed"
    assert "HTTP 409" in outcome["mfa"]["error"]
    assert outcome["totp_secret"] == ""
