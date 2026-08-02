"""通过邮件查看链接轮询 OpenAI OTP。"""

from __future__ import annotations

import logging
import time
from typing import Any
from urllib.parse import urlparse

from mail_cf import _extract_otp

logger = logging.getLogger(__name__)


def validate_mail_url(value: str) -> str:
    url = str(value or "").strip()
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("邮件查看链接必须是有效的 http:// 或 https:// 地址")
    return url


class LinkMailProvider:
    """与 OutlookMailProvider 兼容的邮件链接 Provider。"""

    def __init__(self, email: str, mail_url: str, session: Any | None = None):
        self.email = str(email or "").strip().lower()
        self.mail_url = validate_mail_url(mail_url)
        self.last_persona = None
        self._outlook_creds = None
        self.outlook_exhausted = False
        self._baseline_otp = ""

        if session is not None:
            self._session = session
        else:
            try:
                from curl_cffi.requests import Session

                self._session = Session(impersonate="chrome136")
                self._session.trust_env = False
            except ImportError:
                import requests

                self._session = requests.Session()
                self._session.trust_env = False

    def _fetch(self) -> str:
        response = self._session.get(
            self.mail_url,
            headers={
                "Accept": "text/html,application/xhtml+xml",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
            },
            params={"_poll": str(int(time.time() * 1000))},
            timeout=15,
        )
        if response.status_code != 200:
            raise RuntimeError(f"邮件查看链接返回 HTTP {response.status_code}")
        return response.text or ""

    def create_mailbox(self) -> str:
        logger.info(f"[mail-link] 使用邮箱: {self.email}")
        try:
            body = self._fetch()
            self._baseline_otp = _extract_otp(body) or ""
            logger.info(
                "[mail-link] 已记录当前邮件基线%s",
                "（含旧验证码，后续将忽略）" if self._baseline_otp else "",
            )
        except Exception as exc:
            logger.warning(f"[mail-link] 获取初始邮件基线失败，将继续轮询: {exc}")
        return self.email

    def wait_for_otp(
        self,
        email_addr: str,
        timeout: int = 120,
        issued_after: float | None = None,
    ) -> str:
        deadline = time.time() + max(1, int(timeout))
        last_error = ""
        logger.info(
            f"[mail-link] 等待 OTP -> {email_addr} (timeout={max(1, int(timeout))}s, interval=5s)"
        )

        while time.time() < deadline:
            try:
                body = self._fetch()
                otp = _extract_otp(body)
                if otp and (not self._baseline_otp or otp != self._baseline_otp):
                    logger.info("[mail-link] 获取 OTP 成功")
                    self._baseline_otp = otp
                    return str(otp)
            except Exception as exc:
                last_error = str(exc)
                logger.warning(f"[mail-link] 拉取邮件失败，继续重试: {exc}")
            time.sleep(min(5, max(0.2, deadline - time.time())))

        suffix = f"，最后错误: {last_error}" if last_error else ""
        raise TimeoutError(f"邮件链接 OTP timeout ({int(timeout)}s){suffix}")
