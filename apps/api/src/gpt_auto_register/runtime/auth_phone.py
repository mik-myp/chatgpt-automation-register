# mypy: ignore-errors
"""Phone verification support for the legacy protocol authentication flow."""

import logging
import os
import re
import subprocess
import time
from contextlib import suppress

logger = logging.getLogger(__name__)


class AuthPhoneMixin:
    """Handle the optional add-phone branch without owning the main auth flow."""

    @staticmethod
    def _is_add_phone_state(page_type: str = "", continue_url: str = "") -> bool:
        pt = (page_type or "").strip().lower()
        cu = (continue_url or "").strip().lower()
        return (pt == "add_phone") or ("add-phone" in cu)

    def _phone_headers(self, referer: str) -> dict:
        headers = self._common_headers(referer)
        headers["Accept"] = "application/json"
        headers["Content-Type"] = "application/json"
        headers["Origin"] = "https://auth.openai.com"
        device_id = (self.result.device_id or "").strip() or (
            self.session.cookies.get("oai-did", "") or ""
        ).strip()
        if device_id:
            headers["oai-device-id"] = device_id
        return headers

    def _add_phone_send(self, phone_number: str) -> dict:
        headers = self._phone_headers("https://auth.openai.com/add-phone")
        try:
            resp = self.session.post(
                "https://auth.openai.com/api/accounts/add-phone/send",
                headers=headers,
                json={"phone_number": phone_number},
                timeout=30,
            )
        except Exception as exc:
            logger.warning("[add-phone] 网络异常: %s (phone=%s)", exc, phone_number)
            raise
        self._trace_http("add_phone_send", resp)

        if resp.status_code != 200:
            try:
                data = resp.json()
                message = data.get("error", {}).get("message", "")
            except Exception:
                message = resp.text[:150]
            raise RuntimeError(message or f"HTTP {resp.status_code}")

        try:
            return resp.json() if resp is not None else {}
        except Exception:
            return {}

    def _phone_otp_resend(self) -> bool:
        headers = self._phone_headers("https://auth.openai.com/phone-verification")
        resp = self.session.post(
            "https://auth.openai.com/api/accounts/phone-otp/resend",
            headers=headers,
            timeout=30,
        )
        self._trace_http("phone_otp_resend", resp)
        return resp.status_code == 200

    def _phone_otp_validate(self, code: str) -> dict:
        headers = self._phone_headers("https://auth.openai.com/phone-verification")
        resp = self.session.post(
            "https://auth.openai.com/api/accounts/phone-otp/validate",
            headers=headers,
            json={"code": code},
            timeout=30,
        )
        self._trace_http("phone_otp_validate", resp)
        if resp.status_code != 200:
            raise RuntimeError(
                f"phone-otp/validate 失败: {resp.status_code} - {(resp.text or '')[:220]}"
            )
        try:
            return resp.json() if resp is not None else {}
        except Exception:
            return {}

    @staticmethod
    def _extract_otp6(text: str) -> str:
        if not text:
            return ""
        match = re.search(r"(?<!\d)(\d{6})(?!\d)", text)
        return (match.group(1) if match else "").strip()

    def _read_phone_otp_from_cmd(self) -> str:
        """Read a six-digit phone OTP from ``OPENAI_PHONE_OTP_CMD`` stdout."""
        cmd = (os.getenv("OPENAI_PHONE_OTP_CMD", "") or "").strip()
        if not cmd:
            return ""
        try:
            output = subprocess.check_output(cmd, shell=True, text=True, timeout=20)
            return self._extract_otp6(output or "")
        except Exception:
            return ""

    def _wait_phone_otp(self, timeout: int = 180) -> str:
        static_otp = self._extract_otp6(os.getenv("OPENAI_PHONE_OTP", "") or "")
        if static_otp:
            return static_otp

        deadline = time.time() + max(20, int(timeout))
        while time.time() < deadline:
            code = self._read_phone_otp_from_cmd()
            if code:
                return code
            time.sleep(4)
        raise TimeoutError(f"等待手机 OTP 超时 ({timeout}s)")

    def _handle_add_phone_verification(self, continue_url: str = "") -> str:
        """Use the configured SMS controller, then fall back to environment input."""
        if self._sms_callback is not None:
            try:
                return self._handle_add_phone_via_sms(continue_url)
            except Exception as exc:
                logger.warning("SMS 接码流程失败，回退环境变量路径: %s", exc)
                with suppress(Exception):
                    self._sms_callback.cleanup()
        return self._handle_add_phone_via_env(continue_url)

    def _handle_add_phone_via_sms(self, continue_url: str = "") -> str:
        """Rent and validate phone numbers through the configured SMS controller."""
        controller = self._sms_callback
        with suppress(Exception):
            controller.set_resend_callback(self._phone_otp_resend)

        try:
            return self._do_sms_loop(controller, continue_url)
        finally:
            with suppress(Exception):
                controller.cleanup()
            with suppress(Exception):
                controller._release_lock()

    @staticmethod
    def _sms_int_setting(
        config: dict,
        config_key: str,
        env_key: str,
        default: str,
        minimum: int = 1,
    ) -> int:
        raw = str(config.get(config_key) or "").strip() or os.getenv(env_key, default)
        try:
            return max(minimum, int(raw))
        except Exception:
            return int(default)

    def _do_sms_loop(self, controller, continue_url: str = "") -> str:
        """Try one or more rented phone numbers until verification succeeds."""
        provider_key = (getattr(controller, "provider_key", "") or "").lower()
        controller_config = getattr(controller, "config", None) or {}
        per_phone_timeout = max(
            40,
            self._sms_int_setting(
                controller_config,
                "sms_per_phone_timeout",
                "OPENAI_PHONE_OTP_TIMEOUT",
                "80",
                minimum=40,
            ),
        )
        max_phone_attempts = self._sms_int_setting(
            controller_config,
            "sms_max_phone_attempts",
            "OPENAI_PHONE_MAX_ATTEMPTS",
            "3",
        )
        max_code_retries = self._sms_int_setting(
            controller_config,
            "sms_code_retries_per_phone",
            "OPENAI_PHONE_OTP_CODE_RETRIES",
            "2",
        )

        logger.info(
            "[sms] 配置: provider=%s 单号窗口=%ds 最多换号=%d 单号内验证重试=%d",
            provider_key,
            per_phone_timeout,
            max_phone_attempts,
            max_code_retries,
        )

        rejected_patterns = (
            "phone_number_already_in_use",
            "already_in_use",
            "already_taken",
            "phone_already_verified",
            "already_verified",
            "disallowed_phone",
            "invalid_phone_number",
            "phone_number_invalid",
            "blocked_phone",
            "phone_number_blocked",
            "suspicious behavior from phone",
        )

        def is_phone_rejected(message: str) -> bool:
            lowered = (message or "").lower()
            return any(pattern in lowered for pattern in rejected_patterns)

        last_error = None
        for phone_attempt in range(1, max_phone_attempts + 1):
            logger.info("[sms] 第 %d/%d 个号尝试...", phone_attempt, max_phone_attempts)
            try:
                phone = controller.get_phone()
            except Exception as exc:
                last_error = exc
                logger.warning("[sms] 第 %d 个号租号失败: %s", phone_attempt, exc)
                continue
            if not phone:
                last_error = RuntimeError("SMS 接码 controller 未返回手机号")
                continue

            try:
                logger.info("[sms] 准备 POST add-phone/send (phone=%s) ...", phone)
                send_response = self._add_phone_send(phone)
                logger.info("[sms] POST add-phone/send 成功 (phone=%s)", phone)
            except Exception as exc:
                error_text = str(exc)
                if (
                    "too many phone verification" in error_text.lower()
                    or "phone_verification_rate_limit" in error_text.lower()
                ):
                    logger.warning(
                        "OpenAI 频控: 当前账号或 IP 已累积过多 add-phone 请求，放弃本阶段"
                    )
                    controller.mark_send_failed(error_text)
                    last_error = exc
                    break
                if is_phone_rejected(error_text):
                    logger.warning(
                        "[sms] 号 %s 被 OpenAI 拒（已用过/不允许）: %s",
                        phone,
                        error_text[:200],
                    )
                else:
                    logger.warning(
                        "[sms] 号 %s POST add-phone/send 失败（未识别错误）: %s",
                        phone,
                        error_text[:300],
                    )
                controller.mark_send_failed(error_text)
                last_error = exc
                continue

            send_page_type = self._extract_page_type(send_response)
            send_continue = self._normalize_continue_url(
                self._extract_continue_url_from_step(send_response)
            )
            if send_page_type not in (
                "phone_otp_verification",
                "external_url",
            ) and "phone-verification" not in (send_continue or ""):
                logger.warning(
                    "add-phone/send 未进入手机验证码页: page=%s continue=%s",
                    send_page_type or "(empty)",
                    (send_continue or "")[:180],
                )
                controller.mark_send_failed("did not enter phone-verification page")
                last_error = RuntimeError(
                    f"add-phone/send 未进入 phone-verification: page={send_page_type}"
                )
                continue

            controller.mark_send_succeeded()
            phone_started_at = time.time()
            seen_codes: set[str] = set()
            code_attempt = 0

            while (
                time.time() - phone_started_at < per_phone_timeout
                and code_attempt < max_code_retries
            ):
                remaining = per_phone_timeout - (time.time() - phone_started_at)
                if remaining < 10:
                    break
                code_attempt += 1
                logger.info(
                    "[sms] 号 %s 第 %d/%d 次等 SMS (剩余 %ds)",
                    phone,
                    code_attempt,
                    max_code_retries,
                    int(remaining),
                )
                code = controller.get_code(timeout=int(remaining))
                if not code:
                    break
                if code in seen_codes:
                    logger.warning("[sms] 收到重复 code=%s，跳过", code)
                    continue
                seen_codes.add(code)

                try:
                    validate_response = self._phone_otp_validate(code)
                    next_url = self._normalize_continue_url(
                        self._extract_continue_url_from_step(validate_response)
                    )
                    logger.info(
                        "[sms] phone-otp/validate 通过 (phone=%s code=%s) next=%s",
                        phone,
                        code,
                        (next_url or "")[:160],
                    )
                    controller.report_success()
                    return next_url or continue_url or ""
                except Exception as exc:
                    last_error = exc
                    error_text = str(exc)
                    logger.warning(
                        "[sms] validate 失败 (phone=%s code=%s): %s",
                        phone,
                        code,
                        error_text[:200],
                    )
                    controller.mark_code_failed(error_text)

            logger.warning("[sms] 号 %s 已用尽 %ds 窗口", phone, per_phone_timeout)
            with suppress(Exception):
                controller.cleanup()

        if last_error:
            raise last_error
        raise RuntimeError(f"SMS 接码 {max_phone_attempts} 个号均失败")

    def _handle_add_phone_via_env(self, continue_url: str = "") -> str:
        """Handle add-phone using environment-provided numbers and OTP input."""
        phone_raw = (os.getenv("OPENAI_PHONE_NUMBER", "") or "").strip()
        phone_candidates = [value.strip() for value in phone_raw.split(",") if value.strip()]
        if not phone_candidates:
            logger.warning("命中 add-phone，但未配置 SMS 接码 / OPENAI_PHONE_NUMBER，无法继续推进")
            return continue_url or ""

        try:
            otp_timeout = max(30, int(os.getenv("OPENAI_PHONE_OTP_TIMEOUT", "180")))
        except Exception:
            otp_timeout = 180

        last_error = ""
        for index, phone in enumerate(phone_candidates, 1):
            try:
                logger.info("add-phone 尝试号码 %s/%s: %s", index, len(phone_candidates), phone)
                send_response = self._add_phone_send(phone)
                send_page_type = self._extract_page_type(send_response)
                send_continue = self._normalize_continue_url(
                    self._extract_continue_url_from_step(send_response)
                )
                if send_page_type not in (
                    "phone_otp_verification",
                    "external_url",
                ) and "phone-verification" not in (send_continue or ""):
                    logger.warning(
                        "add-phone/send 未进入手机验证码页: page=%s continue=%s",
                        send_page_type or "(empty)",
                        (send_continue or "")[:180],
                    )
                    continue

                phone_code = self._wait_phone_otp(timeout=otp_timeout)
                validate_response = self._phone_otp_validate(phone_code)
                next_url = self._normalize_continue_url(
                    self._extract_continue_url_from_step(validate_response)
                )
                logger.info("add-phone 验证通过，next=%s", (next_url or "")[:180])
                return next_url or continue_url or ""
            except Exception as exc:
                last_error = str(exc)
                logger.warning("add-phone 号码 %s 失败: %s", phone, exc)
                with suppress(Exception):
                    self._phone_otp_resend()

        if last_error:
            logger.warning("add-phone 阶段未成功: %s", last_error)
        return continue_url or ""
