from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gpt_auto_register.worker.manager import WorkerManager

__all__ = ["WorkerManager"]


def __getattr__(name: str) -> Any:
    if name != "WorkerManager":
        raise AttributeError(name)
    from gpt_auto_register.worker.manager import WorkerManager

    return WorkerManager
