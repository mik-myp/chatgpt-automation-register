"""merge legacy Kakao tasks into pipeline

Revision ID: e8a4c6d2f901
Revises: d4f8a1c2e630
"""

from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision: str = "e8a4c6d2f901"
down_revision: str | None = "d4f8a1c2e630"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    tasks = (
        connection.execute(
            sa.text(
                """
            SELECT id, email, card_id, card_code_snapshot, created_at, updated_at
            FROM kakao_tasks
            WHERE pipeline_run_id IS NULL
            ORDER BY created_at, id
            """
            )
        )
        .mappings()
        .all()
    )
    if not tasks:
        return

    run_id = str(uuid4())
    now = datetime.now(UTC)
    created_at = tasks[0]["created_at"] or now
    updated_at = tasks[-1]["updated_at"] or now
    connection.execute(
        sa.text(
            """
            INSERT INTO pipeline_runs (
                id, kind, source_pipeline_run_id, status, mode, target_count,
                kakao_enabled, config_snapshot, scheduled_count, registered_count,
                failed_count, kakao_task_count, started_at, finished_at,
                created_at, updated_at
            ) VALUES (
                :id, 'kakao', NULL, 'completed', 'kakao_legacy', :target_count,
                1, :config_snapshot, :target_count, :target_count,
                0, :target_count, :created_at, :updated_at,
                :created_at, :updated_at
            )
            """
        ),
        {
            "id": run_id,
            "target_count": len(tasks),
            "config_snapshot": '{"migrated_legacy_kakao_tasks": true}',
            "created_at": created_at,
            "updated_at": updated_at,
        },
    )

    card_counts: Counter[str] = Counter()
    for position, task in enumerate(tasks):
        item_id = str(uuid4())
        connection.execute(
            sa.text(
                """
                INSERT INTO pipeline_items (
                    id, pipeline_run_id, position, account_email,
                    mail_url_snapshot, registration_run_id, card_code_snapshot,
                    status, eligibility_state, password_status, mfa_status,
                    security_error, error, created_at, updated_at
                ) VALUES (
                    :id, :run_id, :position, :email,
                    NULL, NULL, :card_code_snapshot,
                    'completed', NULL, NULL, NULL,
                    NULL, NULL, :created_at, :updated_at
                )
                """
            ),
            {
                "id": item_id,
                "run_id": run_id,
                "position": position,
                "email": task["email"],
                "card_code_snapshot": task["card_code_snapshot"],
                "created_at": task["created_at"] or now,
                "updated_at": task["updated_at"] or now,
            },
        )
        connection.execute(
            sa.text(
                """
                UPDATE kakao_tasks
                SET pipeline_run_id = :run_id, pipeline_item_id = :item_id
                WHERE id = :task_id
                """
            ),
            {"run_id": run_id, "item_id": item_id, "task_id": task["id"]},
        )
        if task["card_id"]:
            card_counts[str(task["card_id"])] += 1

    for card_id, count in card_counts.items():
        connection.execute(
            sa.text(
                """
                INSERT INTO pipeline_card_allocations (
                    pipeline_run_id, card_id, allocated_count,
                    created_count, duplicate_count, failed_count
                ) VALUES (:run_id, :card_id, :count, :count, 0, 0)
                """
            ),
            {"run_id": run_id, "card_id": card_id, "count": count},
        )


def downgrade() -> None:
    connection = op.get_bind()
    run_ids = list(
        connection.scalars(
            sa.text(
                """
                SELECT id
                FROM pipeline_runs
                WHERE mode = 'kakao_legacy'
                  AND config_snapshot LIKE '%migrated_legacy_kakao_tasks%'
                """
            )
        )
    )
    if not run_ids:
        return
    for run_id in run_ids:
        connection.execute(
            sa.text(
                """
                UPDATE kakao_tasks
                SET pipeline_run_id = NULL, pipeline_item_id = NULL
                WHERE pipeline_run_id = :run_id
                """
            ),
            {"run_id": run_id},
        )
        connection.execute(
            sa.text("DELETE FROM pipeline_runs WHERE id = :run_id"),
            {"run_id": run_id},
        )
