import threading
from collections.abc import Iterator
from contextlib import contextmanager

from gpt_auto_register.db.models.pipeline import PipelineRun, PipelineStatus
from gpt_auto_register.worker.runtime_service import SessionFactory


@contextmanager
def monitor_run_cancellation(
    run_id: str,
    session_factory: SessionFactory,
) -> Iterator[threading.Event]:
    canceled = threading.Event()
    stopped = threading.Event()

    def monitor() -> None:
        while not stopped.is_set():
            with session_factory() as session:
                run = session.get(PipelineRun, run_id)
                if run is None or run.status == PipelineStatus.CANCELED:
                    canceled.set()
                    return
            if stopped.wait(0.25):
                return

    thread = threading.Thread(
        target=monitor,
        daemon=True,
        name=f"pipeline-cancel-{run_id[:8]}",
    )
    thread.start()
    try:
        yield canceled
    finally:
        stopped.set()
        thread.join(timeout=1)
