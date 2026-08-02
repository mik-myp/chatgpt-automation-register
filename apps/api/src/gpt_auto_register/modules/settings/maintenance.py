from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from gpt_auto_register.db.base import utc_now
from gpt_auto_register.db.models.jobs import Job, JobEvent, JobStatus
from gpt_auto_register.modules.settings.schemas import (
    StorageCleanupResponse,
    StorageStatsResponse,
)


def _backup_files(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    return [path for path in directory.glob("recovery-*.json") if path.is_file()]


def storage_stats(
    session: Session,
    *,
    retention_days: int,
    database_path: Path | None,
    backup_directory: Path,
) -> StorageStatsResponse:
    cutoff = utc_now() - timedelta(days=retention_days)
    backups = _backup_files(backup_directory)
    return StorageStatsResponse(
        database_bytes=(
            database_path.stat().st_size if database_path and database_path.exists() else 0
        ),
        job_events=int(session.scalar(select(func.count(JobEvent.id))) or 0),
        expired_job_events=int(
            session.scalar(select(func.count(JobEvent.id)).where(JobEvent.created_at < cutoff)) or 0
        ),
        backup_files=len(backups),
        backup_bytes=sum(path.stat().st_size for path in backups),
    )


def cleanup_storage(
    session: Session,
    *,
    retention_days: int,
    backup_directory: Path,
) -> StorageCleanupResponse:
    cutoff = utc_now() - timedelta(days=retention_days)
    terminal_jobs = select(Job.id).where(
        Job.status.in_([JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELED])
    )
    result = session.execute(
        delete(JobEvent).where(
            JobEvent.created_at < cutoff,
            JobEvent.job_id.in_(terminal_jobs),
        )
    )
    session.commit()
    removed_backups = 0
    for path in _backup_files(backup_directory):
        modified = path.stat().st_mtime
        if modified < cutoff.timestamp():
            path.unlink()
            removed_backups += 1
    return StorageCleanupResponse(
        removed_job_events=int(getattr(result, "rowcount", 0) or 0),
        removed_backup_files=removed_backups,
    )
