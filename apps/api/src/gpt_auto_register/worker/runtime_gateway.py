from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from collections import deque
from collections.abc import Callable, Mapping
from typing import Any, Literal, TypedDict, cast

from gpt_auto_register.core.config import get_settings
from gpt_auto_register.core.redaction import redact_text
from gpt_auto_register.worker.legacy_runner import RESULT_PREFIX

RuntimeAction = Literal[
    "enable_mfa",
    "export",
    "export_test",
    "mail_test",
    "register",
    "set_password",
    "sms_countries",
    "sms_test",
    "verify_mfa",
]
SUPPORTED_ACTIONS: frozenset[str] = frozenset(RuntimeAction.__args__)  # type: ignore[attr-defined]


class RuntimeRequest(TypedDict, total=False):
    action: RuntimeAction
    account: dict[str, Any]
    credential: dict[str, Any]
    registration: dict[str, Any]
    sms: dict[str, Any]
    mail: dict[str, Any]
    export: dict[str, Any]
    target: str
    proxy: str


RuntimeLogSink = Callable[[str], None]


def runtime_call(
    payload: RuntimeRequest | Mapping[str, Any],
    timeout: int = 1800,
    *,
    log_sink: RuntimeLogSink | None = None,
    max_lines: int = 2000,
) -> dict[str, Any]:
    action = str(payload.get("action") or "")
    if action not in SUPPORTED_ACTIONS:
        raise ValueError(f"不支持的运行时动作: {action or '(empty)'}")
    settings = get_settings()
    environment = os.environ.copy()
    environment["GPT_AUTO_LEGACY_RUNTIME_PATH"] = str(settings.legacy_runtime_path)
    environment["GPT_AUTO_RUNTIME_DATA_PATH"] = str(settings.runtime_data_path)
    process = subprocess.Popen(
        [sys.executable, "-m", "gpt_auto_register.worker.legacy_runner"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=environment,
    )
    if process.stdin is None or process.stdout is None:
        process.kill()
        raise RuntimeError("无法连接协议运行时")
    timed_out = threading.Event()

    def terminate_on_timeout() -> None:
        timed_out.set()
        process.kill()

    timer = threading.Timer(timeout, terminate_on_timeout)
    timer.daemon = True
    timer.start()
    lines: deque[str] = deque(maxlen=max(100, min(max_lines, 20000)))
    result_line: str | None = None
    try:
        process.stdin.write(json.dumps(dict(payload), ensure_ascii=False))
        process.stdin.close()
        for raw_line in process.stdout:
            line = raw_line.rstrip("\r\n")
            if line.startswith(RESULT_PREFIX):
                if len(line) > 2_000_000:
                    raise RuntimeError("协议运行时结果超过 2 MB 限制")
                result_line = line
                continue
            line = redact_text(line, limit=4000)
            lines.append(line)
            if line and log_sink:
                log_sink(line)
        process.wait()
    finally:
        timer.cancel()
    if timed_out.is_set():
        raise RuntimeError(f"协议运行超时（{timeout} 秒）")
    if result_line is not None:
        value = json.loads(result_line.removeprefix(RESULT_PREFIX))
        if isinstance(value, dict):
            return cast(dict[str, Any], value)
        raise RuntimeError("协议运行时返回了无效结果类型")
    raise RuntimeError(lines[-1] if lines else "协议运行时未返回结果")


class RuntimeGateway:
    def call(
        self,
        payload: RuntimeRequest | Mapping[str, Any],
        timeout: int = 1800,
    ) -> dict[str, Any]:
        return runtime_call(payload, timeout)


runtime_gateway = RuntimeGateway()
