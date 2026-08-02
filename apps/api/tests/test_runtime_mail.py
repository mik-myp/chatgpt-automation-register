from io import BytesIO
from urllib.error import HTTPError

from gpt_auto_register.runtime.mail_cf import CFTempEmailProvider
from gpt_auto_register.runtime.mail_outlook import _xoauth2_callback


class _FailingSession:
    def get(self, *args, **kwargs):
        raise RuntimeError("use urllib fallback")


def test_cf_mail_http_error_keeps_json_body_after_except(
    monkeypatch,
) -> None:
    error = HTTPError(
        "https://mail.example.test/admin/mails",
        403,
        "Forbidden",
        {},
        BytesIO(b'{"error":"denied"}'),
    )

    def raise_http_error(*args, **kwargs):
        raise error

    monkeypatch.setattr("urllib.request.urlopen", raise_http_error)
    provider = CFTempEmailProvider(
        api_url="https://mail.example.test",
        domain="example.test",
        session=_FailingSession(),
    )

    response = provider._request("GET", "/admin/mails")

    assert response.status_code == 403
    assert response.json() == {"error": "denied"}


def test_xoauth2_callback_captures_credentials() -> None:
    callback = _xoauth2_callback("user@example.test", "access-token")
    expected = b"user=user@example.test\x01auth=Bearer access-token\x01\x01"

    assert callback(b"challenge") == expected
