"""index jobs by pipeline run

Revision ID: a6f21c8d9e04
Revises: e8a4c6d2f901
Create Date: 2026-08-02
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a6f21c8d9e04"
down_revision: str | None = "e8a4c6d2f901"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("jobs") as batch_op:
        batch_op.add_column(sa.Column("pipeline_run_id", sa.String(length=36), nullable=True))
        batch_op.create_index("ix_jobs_pipeline_run_id", ["pipeline_run_id"], unique=False)
        batch_op.create_foreign_key(
            "fk_jobs_pipeline_run_id_pipeline_runs",
            "pipeline_runs",
            ["pipeline_run_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.execute(
        sa.text(
            "UPDATE jobs "
            "SET pipeline_run_id = json_extract(payload, '$.pipeline_run_id') "
            "WHERE json_valid(payload) AND json_extract(payload, '$.pipeline_run_id') IS NOT NULL"
        )
    )


def downgrade() -> None:
    with op.batch_alter_table("jobs") as batch_op:
        batch_op.drop_constraint("fk_jobs_pipeline_run_id_pipeline_runs", type_="foreignkey")
        batch_op.drop_index("ix_jobs_pipeline_run_id")
        batch_op.drop_column("pipeline_run_id")
