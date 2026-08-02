"""add account security pipelines

Revision ID: d4f8a1c2e630
Revises: b7e2c4d6f810
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d4f8a1c2e630"
down_revision: str | None = "b7e2c4d6f810"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("pipeline_runs") as batch_op:
        batch_op.add_column(
            sa.Column(
                "kind",
                sa.String(length=32),
                nullable=False,
                server_default="registration",
            )
        )
        batch_op.add_column(
            sa.Column("source_pipeline_run_id", sa.String(length=36), nullable=True)
        )
        batch_op.create_index(batch_op.f("ix_pipeline_runs_kind"), ["kind"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_pipeline_runs_source_pipeline_run_id"),
            ["source_pipeline_run_id"],
            unique=False,
        )
        batch_op.create_foreign_key(
            batch_op.f("fk_pipeline_runs_source_pipeline_run_id_pipeline_runs"),
            "pipeline_runs",
            ["source_pipeline_run_id"],
            ["id"],
            ondelete="SET NULL",
        )
    with op.batch_alter_table("pipeline_items") as batch_op:
        batch_op.add_column(sa.Column("password_status", sa.String(length=32)))
        batch_op.add_column(sa.Column("mfa_status", sa.String(length=32)))
        batch_op.add_column(sa.Column("security_error", sa.Text()))


def downgrade() -> None:
    with op.batch_alter_table("pipeline_items") as batch_op:
        batch_op.drop_column("security_error")
        batch_op.drop_column("mfa_status")
        batch_op.drop_column("password_status")
    with op.batch_alter_table("pipeline_runs") as batch_op:
        batch_op.drop_constraint(
            batch_op.f("fk_pipeline_runs_source_pipeline_run_id_pipeline_runs"),
            type_="foreignkey",
        )
        batch_op.drop_index(batch_op.f("ix_pipeline_runs_source_pipeline_run_id"))
        batch_op.drop_index(batch_op.f("ix_pipeline_runs_kind"))
        batch_op.drop_column("source_pipeline_run_id")
        batch_op.drop_column("kind")
