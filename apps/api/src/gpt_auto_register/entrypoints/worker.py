import signal
import threading

from gpt_auto_register.core.encryption import ensure_master_key
from gpt_auto_register.db.session import SessionLocal
from gpt_auto_register.worker import WorkerManager


def main() -> None:
    with SessionLocal() as session:
        ensure_master_key(session)
    manager = WorkerManager()
    stopped = threading.Event()

    def stop(_signum: int, _frame: object) -> None:
        stopped.set()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    manager.start()
    try:
        while not stopped.wait(1):
            if not manager.is_alive():
                raise RuntimeError("worker thread stopped unexpectedly")
    finally:
        manager.stop()


if __name__ == "__main__":
    main()
