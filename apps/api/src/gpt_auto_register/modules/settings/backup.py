from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.inspection import inspect
from sqlalchemy.orm import Session

from gpt_auto_register.core.encryption import encrypt_text, protect_setting, reveal_setting
from gpt_auto_register.db.base import utc_now
from gpt_auto_register.db.models.accounts import AccountStatus, Credential, OutlookAccount
from gpt_auto_register.db.models.kakao import (
    KakaoCard,
    KakaoCardBatch,
    KakaoTask,
    PipelineCardAllocation,
)
from gpt_auto_register.db.models.settings import AppSetting
from gpt_auto_register.modules.settings.schemas import (
    BackupBundle,
    BackupImportRequest,
    BackupImportResponse,
    BackupPreviewRequest,
    BackupPreviewResponse,
    BackupSectionPreview,
)

MODELS = {
    "settings": (AppSetting, ("key",)),
    "accounts": (OutlookAccount, ("email",)),
    "credentials": (Credential, ("email",)),
    "card_batches": (KakaoCardBatch, ("id",)),
    "cards": (KakaoCard, ("id",)),
}
BACKUP_SECTIONS = tuple(MODELS)
EXCLUDED_SECTIONS = [
    "pipeline_runs",
    "pipeline_items",
    "registration_runs",
    "jobs",
    "job_events",
    "kakao_tasks",
    "pipeline_card_allocations",
]


def _json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _row_data(row: Any) -> dict[str, Any]:
    values = {
        column.key: _json_value(getattr(row, column.key)) for column in inspect(type(row)).columns
    }
    if isinstance(row, AppSetting) and row.sensitive:
        values["value"] = reveal_setting(row.value)
    return values


def _key(data: dict[str, Any], names: tuple[str, ...]) -> tuple[Any, ...]:
    return tuple(data.get(name) for name in names)


def _checksum_payload(bundle: dict[str, Any]) -> str:
    value = {key: item for key, item in bundle.items() if key != "checksum"}
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(encoded.encode()).hexdigest()


def validate_bundle(bundle: BackupBundle) -> None:
    if bundle.checksum != _checksum_payload(bundle.model_dump(mode="json")):
        raise ValueError("备份完整性校验失败，文件可能已损坏或被修改")


def export_bundle(session: Session) -> BackupBundle:
    sections = {
        name: [_row_data(row) for row in session.scalars(select(model))]
        for name, (model, _) in MODELS.items()
    }
    data: dict[str, Any] = {
        "format": "gpt-auto-register-backup",
        "version": 3,
        "exported_at": utc_now().isoformat(),
        "scope": {
            "included": list(BACKUP_SECTIONS),
            "excluded": EXCLUDED_SECTIONS,
            "description": "配置、账号凭据和卡密迁移；不包含运行中任务及历史日志",
        },
        "sections": sections,
    }
    data["checksum"] = _checksum_payload(data)
    return BackupBundle.model_validate(data)


def _write_recovery_snapshot(session: Session, directory: Path) -> str | None:
    database = getattr(getattr(session.get_bind(), "url", None), "database", None)
    if not database or database == ":memory:":
        return None
    directory.mkdir(parents=True, exist_ok=True)
    bundle = export_bundle(session)
    stamp = utc_now().strftime("%Y%m%dT%H%M%S%fZ")
    path = directory / f"recovery-{stamp}.json.enc"
    path.write_text(encrypt_text(bundle.model_dump_json()), encoding="utf-8")
    path.chmod(0o600)
    return path.name


def _protected_keys(session: Session, section: str) -> set[tuple[Any, ...]]:
    if section == "accounts":
        return {
            (email,)
            for email in session.scalars(
                select(OutlookAccount.email).where(OutlookAccount.status == AccountStatus.IN_USE)
            )
        }
    if section == "cards":
        ids = set(session.scalars(select(PipelineCardAllocation.card_id)))
        ids.update(session.scalars(select(KakaoTask.card_id)))
        return {(value,) for value in ids}
    if section == "card_batches":
        used = set(session.scalars(select(KakaoCard.batch_id)))
        return {(value,) for value in used}
    return set()


def preview_bundle(session: Session, request: BackupPreviewRequest) -> BackupPreviewResponse:
    validate_bundle(request.bundle)
    previews: dict[str, BackupSectionPreview] = {}
    for section in request.sections:
        model, key_names = MODELS[section]
        incoming_rows = request.bundle.sections.get(section, [])
        incoming = {_key(row, key_names): row for row in incoming_rows}
        local = {
            _key(_row_data(row), key_names): _row_data(row)
            for row in session.scalars(select(model))
        }
        protected_keys = _protected_keys(session, section)
        common = incoming.keys() & local.keys()
        removable_keys = local.keys() - incoming.keys() if request.mode == "overwrite" else set()
        previews[section] = BackupSectionPreview(
            incoming=len(incoming),
            added=len(incoming.keys() - local.keys()),
            updated=sum(incoming[key] != local[key] for key in common),
            unchanged=sum(incoming[key] == local[key] for key in common),
            removable=len(removable_keys - protected_keys),
            protected=len(removable_keys & protected_keys),
        )
    return BackupPreviewResponse(sections=previews)


def _coerce(model: type[Any], data: dict[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    mapper = inspect(model)
    for column in mapper.columns:
        if column.key not in data:
            continue
        value = data[column.key]
        if value is not None and isinstance(column.type.python_type, type):
            python_type = column.type.python_type
            if python_type is datetime and isinstance(value, str):
                value = datetime.fromisoformat(value.replace("Z", "+00:00"))
            elif isinstance(python_type, type) and issubclass(python_type, Enum):
                value = python_type(value)
        if model is AppSetting and column.key == "value" and data.get("sensitive") is True:
            value = protect_setting(value)
        values[column.key] = value
    return values


def import_bundle(
    session: Session,
    request: BackupImportRequest,
    *,
    recovery_directory: Path | None = None,
) -> BackupImportResponse:
    validate_bundle(request.bundle)
    preview = preview_bundle(session, request)
    recovery_snapshot = (
        _write_recovery_snapshot(session, recovery_directory) if recovery_directory else None
    )
    added = updated = unchanged = removed = protected = 0
    # Parent rows must be present before cards; cards must be removed before batches.
    all_sections = ("settings", "accounts", "credentials", "card_batches", "cards")
    ordered = [name for name in all_sections if name in request.sections]
    for section in ordered:
        model, key_names = MODELS[section]
        incoming_rows = request.bundle.sections.get(section, [])
        incoming = {_key(row, key_names): row for row in incoming_rows}
        local_rows = list(session.scalars(select(model)))
        local = {_key(_row_data(row), key_names): row for row in local_rows}
        for key, data in incoming.items():
            row = local.get(key)
            values = _coerce(model, data)
            if row is None:
                session.add(model(**values))
                added += 1
            elif _row_data(row) == data or request.conflict_policy == "local":
                unchanged += 1
            else:
                for name, value in values.items():
                    setattr(row, name, value)
                updated += 1
        session.flush()

    if request.mode == "overwrite":
        for section in reversed(ordered):
            model, key_names = MODELS[section]
            incoming_keys = {
                _key(row, key_names) for row in request.bundle.sections.get(section, [])
            }
            protected_keys = _protected_keys(session, section)
            for row in list(session.scalars(select(model))):
                key = _key(_row_data(row), key_names)
                if key in incoming_keys:
                    continue
                if key in protected_keys:
                    protected += 1
                    continue
                session.delete(row)
                removed += 1
    session.commit()
    # Include protected counts from preview even when an FK added protection indirectly.
    protected = max(protected, sum(value.protected for value in preview.sections.values()))
    return BackupImportResponse(
        added=added,
        updated=updated,
        unchanged=unchanged,
        removed=removed,
        protected=protected,
        recovery_snapshot=recovery_snapshot,
    )
