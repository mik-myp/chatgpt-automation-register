import io
import json
import threading

import pytest

from gpt_auto_register.worker.legacy_runner import RESULT_PREFIX
from gpt_auto_register.worker.runtime_gateway import RuntimeCanceledError, runtime_call


def test_runtime_gateway_rejects_unknown_action_before_starting_process() -> None:
    with pytest.raises(ValueError, match="不支持的运行时动作"):
        runtime_call({"action": "unknown"})


def test_runtime_gateway_parses_result_and_preserves_streamed_log(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeProcess:
        pid = 1

        def __init__(self) -> None:
            self.stdin = io.StringIO()
            self.stdout = io.StringIO(
                "获取 OTP 成功: 123456\n"
                + RESULT_PREFIX
                + json.dumps(
                    {
                        "ok": True,
                        "credential": {
                            "password": "known-password",
                            "access_token": "returned-token",
                        },
                    }
                )
                + "\n"
            )

        def kill(self) -> None:
            return None

        def wait(self, timeout: float | None = None) -> int:
            return 0

    monkeypatch.setattr(
        "gpt_auto_register.worker.runtime_gateway.subprocess.Popen",
        lambda *args, **kwargs: FakeProcess(),
    )
    logs: list[str] = []
    result = runtime_call({"action": "sms_test", "sms": {}}, log_sink=logs.append)
    assert result["credential"] == {
        "password": "known-password",
        "access_token": "returned-token",
    }
    assert logs == ["获取 OTP 成功: 123456"]


def test_runtime_gateway_stops_process_when_canceled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stopped = threading.Event()

    class BlockingOutput:
        def __iter__(self) -> "BlockingOutput":
            return self

        def __next__(self) -> str:
            stopped.wait(2)
            raise StopIteration

    class FakeProcess:
        pid = 2

        def __init__(self) -> None:
            self.stdin = io.StringIO()
            self.stdout = BlockingOutput()

        def kill(self) -> None:
            stopped.set()

        def wait(self, timeout: float | None = None) -> int:
            stopped.wait(timeout)
            return 0

    monkeypatch.setattr(
        "gpt_auto_register.worker.runtime_gateway.subprocess.Popen",
        lambda *args, **kwargs: FakeProcess(),
    )
    monkeypatch.setattr(
        "gpt_auto_register.worker.runtime_gateway._terminate_process_group",
        lambda process: process.kill(),
    )

    with pytest.raises(RuntimeCanceledError, match="协议运行已取消"):
        runtime_call(
            {"action": "sms_test", "sms": {}},
            cancel_check=lambda: True,
        )

    assert stopped.is_set()
