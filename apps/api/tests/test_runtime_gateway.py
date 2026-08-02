import io
import json

import pytest

from gpt_auto_register.worker.legacy_runner import RESULT_PREFIX
from gpt_auto_register.worker.runtime_gateway import runtime_call


def test_runtime_gateway_rejects_unknown_action_before_starting_process() -> None:
    with pytest.raises(ValueError, match="不支持的运行时动作"):
        runtime_call({"action": "unknown"})


def test_runtime_gateway_parses_result_and_redacts_streamed_log(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeProcess:
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

        def wait(self) -> int:
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
    assert logs == ["获取 OTP 成功: [REDACTED]"]
