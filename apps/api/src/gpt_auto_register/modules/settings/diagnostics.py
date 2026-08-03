from __future__ import annotations

import io
import json
import platform
import sys
import zipfile
from collections import Counter
from datetime import datetime
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from gpt_auto_register.core.config import Settings
from gpt_auto_register.db.base import utc_now
from gpt_auto_register.db.models.jobs import Job, JobEvent
from gpt_auto_register.db.models.pipeline import PipelineRun
from gpt_auto_register.modules.settings.service import SettingsService

MAX_JOBS = 200
MAX_JOB_EVENTS = 20_000
MAX_PIPELINES = 100


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _package_versions() -> dict[str, str]:
    values: dict[str, str] = {}
    for package in ("fastapi", "sqlalchemy", "pydantic", "httpx", "curl-cffi"):
        try:
            values[package] = version(package)
        except PackageNotFoundError:
            values[package] = "not-installed"
    return values


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")


def _json_lines(values: list[dict[str, Any]]) -> bytes:
    content = "\n".join(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for value in values
    )
    return (content + ("\n" if content else "")).encode("utf-8")


def build_diagnostic_bundle(session: Session, settings: Settings) -> bytes:
    jobs = list(session.scalars(select(Job).order_by(Job.created_at.desc()).limit(MAX_JOBS)))
    job_ids = [job.id for job in jobs]
    events = (
        list(
            session.scalars(
                select(JobEvent)
                .where(JobEvent.job_id.in_(job_ids))
                .order_by(JobEvent.id.desc())
                .limit(MAX_JOB_EVENTS)
            )
        )
        if job_ids
        else []
    )
    events.reverse()
    pipelines = list(
        session.scalars(
            select(PipelineRun).order_by(PipelineRun.created_at.desc()).limit(MAX_PIPELINES)
        )
    )
    maintenance = SettingsService(session).maintenance_internal()
    exported_at = utc_now()

    job_values = [
        {
            "id": job.id,
            "pipeline_run_id": job.pipeline_run_id,
            "kind": job.kind,
            "status": str(job.status),
            "attempts": job.attempts,
            "max_attempts": job.max_attempts,
            "error": job.error,
            "created_at": _iso(job.created_at),
            "updated_at": _iso(job.updated_at),
            "finished_at": _iso(job.finished_at),
        }
        for job in jobs
    ]
    event_values = [
        {
            "job_id": event.job_id,
            "sequence": event.sequence,
            "level": event.level,
            "event_type": event.event_type,
            "message": event.message,
            "data": event.data,
            "created_at": _iso(event.created_at),
        }
        for event in events
    ]
    pipeline_values = [
        {
            "id": pipeline.id,
            "kind": str(pipeline.kind),
            "status": str(pipeline.status),
            "mode": pipeline.mode,
            "target_count": pipeline.target_count,
            "scheduled_count": pipeline.scheduled_count,
            "registered_count": pipeline.registered_count,
            "failed_count": pipeline.failed_count,
            "kakao_task_count": pipeline.kakao_task_count,
            "created_at": _iso(pipeline.created_at),
            "updated_at": _iso(pipeline.updated_at),
            "started_at": _iso(pipeline.started_at),
            "finished_at": _iso(pipeline.finished_at),
        }
        for pipeline in pipelines
    ]
    manifest = {
        "format": "gpt-auto-register-diagnostics",
        "version": 1,
        "exported_at": exported_at.isoformat(),
        "application": {
            "name": settings.app_name,
            "version": settings.app_version,
            "log_level": settings.log_level,
        },
        "environment": {
            "python": sys.version.split()[0],
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "packages": _package_versions(),
        },
        "maintenance": maintenance.model_dump(mode="json"),
        "scope": {
            "jobs_limit": MAX_JOBS,
            "job_events_limit": MAX_JOB_EVENTS,
            "pipelines_limit": MAX_PIPELINES,
            "exported_jobs": len(job_values),
            "exported_job_events": len(event_values),
            "exported_pipelines": len(pipeline_values),
        },
        "summary": {
            "job_statuses": dict(Counter(value["status"] for value in job_values)),
            "event_levels": dict(Counter(value["level"] for value in event_values)),
            "pipeline_statuses": dict(Counter(value["status"] for value in pipeline_values)),
        },
        "security": {
            "encrypted": False,
            "redacted": False,
            "warning": "诊断包包含原始运行日志，只能交给可信的排查人员。",
            "excluded": [
                "数据库文件",
                "数据备份",
                "账号与注册凭据",
                "卡密",
                "完整系统配置",
                "任务输入与任务结果原文",
            ],
        },
    }
    readme = """GPT Auto Register 诊断日志包

该文件用于排查运行故障，可以发送给项目维护者或交给代码分析工具。

包含：
- manifest.json：应用版本、运行环境、导出范围与统计摘要
- jobs.jsonl：最近任务的状态和原始错误
- job-events.jsonl：最近任务事件与运行日志
- pipelines.jsonl：最近流水线的状态与数量摘要

不包含数据库、完整备份、账号凭据、卡密或完整系统配置。
诊断包不加密且不做脱敏，运行日志中的邮箱、手机号、验证码、代理凭据、
Cookie、密码和 Token 会按原文保留。请只交给可信的排查人员。
"""

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("README.txt", readme.encode("utf-8"))
        archive.writestr("manifest.json", _json_bytes(manifest))
        archive.writestr("jobs.jsonl", _json_lines(job_values))
        archive.writestr("job-events.jsonl", _json_lines(event_values))
        archive.writestr("pipelines.jsonl", _json_lines(pipeline_values))
    return output.getvalue()
