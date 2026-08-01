from typing import Any

from sqlalchemy.engine import CursorResult
from sqlalchemy.engine.result import Result


def affected_rows(result: Result[Any]) -> int:
    """Return a stable row count for SQLAlchemy DML results."""
    if not isinstance(result, CursorResult):
        return 0
    return max(0, result.rowcount or 0)
