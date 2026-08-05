from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
from collections import deque
from collections.abc import Callable, Mapping
from contextlib import suppress
from typing import Any, Literal, TypedDict, cast

from gpt_auto_register.core.config import get_settings
from gpt_auto_register.worker.legacy_runner import RESULT_PREFIX

RuntimeAction = Literal[
    "enable_mfa",
    "export",
    "export_test",
    "mail_test",
    "register",
    "refresh_authorization",
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
RuntimeCancelCheck = Callable[[], bool]


class RuntimeCanceledError(RuntimeError):
    pass


def _terminate_process_group(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name != "nt":
            os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
        process.wait(timeout=3)
        return
    except (ProcessLookupError, subprocess.TimeoutExpired):
        pass
    if os.name != "nt":
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
            return
    process.kill()


def runtime_call(
    payload: RuntimeRequest | Mapping[str, Any],
    timeout: int = 1800,
    *,
    log_sink: RuntimeLogSink | None = None,
    max_lines: int = 2000,
    cancel_check: RuntimeCancelCheck | None = None,
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
        start_new_session=os.name != "nt",
    )
    if process.stdin is None or process.stdout is None:
        process.kill()
        raise RuntimeError("无法连接协议运行时")
    timed_out = threading.Event()
    canceled = threading.Event()
    monitor_stop = threading.Event()

    def terminate_on_timeout() -> None:
        timed_out.set()
        _terminate_process_group(process)

    def monitor_cancellation() -> None:
        if cancel_check is None:
            return
        while not monitor_stop.wait(0.1):
            if cancel_check():
                canceled.set()
                _terminate_process_group(process)
                return

    timer = threading.Timer(timeout, terminate_on_timeout)
    timer.daemon = True
    timer.start()
    monitor = threading.Thread(
        target=monitor_cancellation,
        daemon=True,
        name=f"runtime-cancel-{process.pid}",
    )
    monitor.start()
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
            line = line[:4000]
            lines.append(line)
            if line and log_sink:
                log_sink(line)
        process.wait()
    finally:
        timer.cancel()
        monitor_stop.set()
        monitor.join(timeout=1)
    if canceled.is_set():
        raise RuntimeCanceledError("协议运行已取消")
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
        *,
        cancel_check: RuntimeCancelCheck | None = None,
    ) -> dict[str, Any]:
        return runtime_call(payload, timeout, cancel_check=cancel_check)


runtime_gateway = RuntimeGateway()
