from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from curl_cffi.requests.cookies import Cookies

from gpt_auto_register.runtime.account_security import (
    _prefer_fresh_session_cookie,
    enable_authenticator_mfa,
    password_outcome,
    security_outcome,
    set_account_password,
    verify_authenticator_mfa,
)


class FakeResponse:
    def __init__(self, payload: dict[str, Any], status_code: int = 200, url: str = "") -> None:
        self.payload = payload
        self.status_code = status_code
        self.url = url
        self.text = ""

    def json(self) -> dict[str, Any]:
        return self.payload


class FakeSession:
    def __init__(self) -> None:
        self.posts: list[tuple[str, dict[str, Any]]] = []
        self.gets: list[str] = []
        self.cookies = Cookies()

    def post(self, url: str, **kwargs: Any) -> FakeResponse:
        self.posts.append((url, kwargs))
        if "/api/auth/signin/openai?" in url:
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
        if url == "https://auth.openai.com/authorize":
            return FakeResponse({}, url="https://auth.openai.com/email-verification")
        if url.endswith("/backend-api/accounts/mfa_info"):
            return FakeResponse({"mfa_enabled": True, "factors": {"totp": [{"id": "factor"}]}})
        if url.endswith("/api/auth/session"):
            return FakeResponse({"user": {"mfa": False}})
        return FakeResponse({}, url=url)


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

    def _sentinel_fp_kwargs(self) -> dict[str, Any]:
        return {}

    def get_sentinel_token(self, device_id: str) -> str:
        assert device_id == "device"
        return "sentinel-token"

    def authorize_continue(self, **kwargs: Any) -> dict[str, Any]:
        assert kwargs["email"] == "user@example.com"
        assert kwargs["screen_hint"] == "login"
        return {
            "page": {"type": "email_otp_verification"},
            "continue_url": "https://auth.openai.com/email-verification",
        }

    @staticmethod
    def _extract_page_type(value: dict[str, Any]) -> str:
        return str(value.get("page", {}).get("type") or "")

    @staticmethod
    def _extract_continue_url_from_step(value: dict[str, Any]) -> str:
        return str(value.get("continue_url") or "")


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
        {"set_password": True, "enable_authenticator_mfa": True, "mfa_otp_timeout": 180},
    )

    assert outcome["password"]["status"] == "set"
    assert outcome["mfa"]["status"] == "enabled"
    assert outcome["totp_secret"] == "JBSWY3DPEHPK3PXP"
    assert "prompt=login" in flow.session.posts[0][0]
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
        {"set_password": True, "enable_authenticator_mfa": True, "mfa_otp_timeout": 180},
    )

    assert outcome["mfa"]["status"] == "failed"
    assert "HTTP 409" in outcome["mfa"]["error"]
    assert outcome["totp_secret"] == ""


def test_mfa_reauthentication_advances_authorize_intermediate_state() -> None:
    flow = FakeFlow()
    original_get = flow.session.get

    def authorize_get(url: str, **kwargs: Any) -> FakeResponse:
        if url == "https://auth.openai.com/authorize":
            return FakeResponse({}, url="https://auth.openai.com/api/accounts/authorize")
        return original_get(url, **kwargs)

    flow.session.get = authorize_get  # type: ignore[method-assign]

    secret = enable_authenticator_mfa(
        flow,
        FakeMail(),
        email="user@example.com",
        otp_timeout=180,
    )

    assert secret == "JBSWY3DPEHPK3PXP"


def test_set_account_password_uses_add_flow_and_confirms_eligibility(
    monkeypatch: Any,
) -> None:
    flow = FakeFlow()
    flow.password_registration_status = "unsupported"
    flow.result.password = ""
    add_checks = 0

    def password_get(url: str, **kwargs: Any) -> FakeResponse:
        nonlocal add_checks
        flow.session.gets.append(url)
        if url.endswith("/add_password/eligibility"):
            add_checks += 1
            return FakeResponse({"eligible": add_checks == 1})
        if url == "https://auth.openai.com/authorize":
            return FakeResponse({}, url="https://auth.openai.com/email-verification")
        if url == "https://auth.openai.com/reset-password/new-password":
            return FakeResponse({}, url=url)
        return FakeResponse({}, url=url)

    original_post = flow.session.post

    def password_post(url: str, **kwargs: Any) -> FakeResponse:
        if "screen_hint=login" in url and "post_login_add_password=true" in url:
            flow.session.posts.append((url, kwargs))
            return FakeResponse({"url": "https://auth.openai.com/authorize"})
        if url.endswith("/api/accounts/email-otp/validate"):
            flow.session.posts.append((url, kwargs))
            return FakeResponse(
                {"continue_url": "https://auth.openai.com/reset-password/new-password"}
            )
        if url.endswith("/api/accounts/password/add"):
            flow.session.posts.append((url, kwargs))
            return FakeResponse({"type": "reset_password_success"})
        return original_post(url, **kwargs)

    flow.session.get = password_get  # type: ignore[method-assign]
    flow.session.post = password_post  # type: ignore[method-assign]
    monkeypatch.setattr(
        "gpt_auto_register.runtime.sentinel.get_sentinel_token",
        lambda *args, **kwargs: ("sentinel-token", "sentinel-so-token"),
    )

    result = set_account_password(
        flow,
        FakeMail(),
        email="user@example.com",
        password="KnownPassword!2026",
        otp_timeout=180,
    )

    assert result == "KnownPassword!2026"
    assert flow.result.password == "KnownPassword!2026"
    password_request = next(
        kwargs for url, kwargs in flow.session.posts if url.endswith("/password/add")
    )
    assert password_request["json"] == {"password": "KnownPassword!2026"}
    assert password_request["headers"]["openai-sentinel-token"] == "sentinel-token"


def test_verify_authenticator_mfa_requires_a_totp_factor() -> None:
    flow = FakeFlow()

    flow.session.get = lambda *_args, **_kwargs: FakeResponse(  # type: ignore[method-assign]
        {"mfa_enabled": True, "factors": {"totp": []}}
    )

    assert verify_authenticator_mfa(flow) is False


def test_reauthentication_prefers_a_new_session_cookie() -> None:
    flow = FakeFlow()
    cookie_name = "__Secure-next-auth.session-token"
    flow.session.cookies.set(cookie_name, "old-session", domain="chatgpt.com", secure=True)
    flow.session.cookies.set(cookie_name, "new-session", domain=".chatgpt.com", secure=True)

    selected = _prefer_fresh_session_cookie(flow, "old-session")

    assert selected == "new-session"
    assert flow.result.session_token == "new-session"
    matching = [cookie for cookie in flow.session.cookies.jar if cookie.name == cookie_name]
    assert len(matching) == 1
    assert matching[0].value == "new-session"


def test_set_account_password_uses_reset_for_an_existing_password(
    monkeypatch: Any,
) -> None:
    flow = FakeFlow()
    flow.result.password = "CurrentPassword!2026"

    def password_get(url: str, **kwargs: Any) -> FakeResponse:
        flow.session.gets.append(url)
        if url.endswith("/add_password/eligibility"):
            return FakeResponse({"eligible": False})
        if url.endswith("/change_password/eligibility"):
            return FakeResponse({"eligible": True})
        if url == "https://auth.openai.com/authorize":
            return FakeResponse({}, url="https://auth.openai.com/log-in/password")
        if url == "https://auth.openai.com/reset-password/new-password":
            return FakeResponse({}, url=url)
        return FakeResponse({}, url=url)

    original_post = flow.session.post

    def password_post(url: str, **kwargs: Any) -> FakeResponse:
        if "screen_hint=login" in url and "post_login_add_password=true" in url:
            flow.session.posts.append((url, kwargs))
            return FakeResponse({"url": "https://auth.openai.com/authorize"})
        if url.endswith("/api/accounts/password/reset"):
            flow.session.posts.append((url, kwargs))
            return FakeResponse({"type": "reset_password_success"})
        return original_post(url, **kwargs)

    flow.session.get = password_get  # type: ignore[method-assign]
    flow.session.post = password_post  # type: ignore[method-assign]
    flow.login_password_verify = lambda password: {  # type: ignore[attr-defined]
        "continue_url": "https://auth.openai.com/reset-password/new-password"
    }
    flow.get_sentinel_token = lambda _device_id: "token"  # type: ignore[attr-defined]
    monkeypatch.setattr(
        "gpt_auto_register.runtime.sentinel.get_sentinel_token",
        lambda *args, **kwargs: ("sentinel-token", ""),
    )

    result = set_account_password(
        flow,
        FakeMail(),
        email="user@example.com",
        password="ReplacementPassword!2026",
        otp_timeout=180,
    )

    assert result == "ReplacementPassword!2026"
    reset_request = next(
        kwargs for url, kwargs in flow.session.posts if url.endswith("/password/reset")
    )
    assert reset_request["json"] == {"password": "ReplacementPassword!2026"}


def test_set_account_password_recovers_when_configured_password_already_works() -> None:
    flow = FakeFlow()
    flow.result.password = ""
    original_get = flow.session.get

    def password_get(url: str, **kwargs: Any) -> FakeResponse:
        if url.endswith("/add_password/eligibility"):
            return FakeResponse({}, status_code=401)
        if url == "https://auth.openai.com/authorize":
            return FakeResponse({}, url="https://auth.openai.com/log-in/password")
        if url == "https://auth.openai.com/reset-password/new-password":
            return FakeResponse({}, url=url)
        return original_get(url, **kwargs)

    flow.session.get = password_get  # type: ignore[method-assign]
    flow.login_password_verify = lambda password: {  # type: ignore[attr-defined]
        "continue_url": "https://auth.openai.com/reset-password/new-password"
    }

    result = set_account_password(
        flow,
        FakeMail(),
        email="user@example.com",
        password="KnownPassword!2026",
        otp_timeout=180,
    )

    assert result == "KnownPassword!2026"
    assert flow.result.password == "KnownPassword!2026"
    assert not any(url.endswith("/password/reset") for url, _ in flow.session.posts)
