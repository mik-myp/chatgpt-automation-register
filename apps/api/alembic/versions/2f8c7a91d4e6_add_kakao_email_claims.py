"""add Kakao email claims

Revision ID: 2f8c7a91d4e6
Revises: a6f21c8d9e04
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "2f8c7a91d4e6"
down_revision: str | None = "a6f21c8d9e04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "kakao_email_claims",
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("pipeline_run_id", sa.String(length=36), nullable=True),
        sa.Column("pipeline_item_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["pipeline_item_id"], ["pipeline_items.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["pipeline_run_id"], ["pipeline_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("email"),
    )
    op.create_index(
        op.f("ix_kakao_email_claims_state"),
        "kakao_email_claims",
        ["state"],
        unique=False,
    )
    op.create_index(
        op.f("ix_kakao_email_claims_pipeline_run_id"),
        "kakao_email_claims",
        ["pipeline_run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_kakao_email_claims_pipeline_item_id"),
        "kakao_email_claims",
        ["pipeline_item_id"],
        unique=False,
    )
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            INSERT OR IGNORE INTO kakao_email_claims (
                email, state, pipeline_run_id, pipeline_item_id, created_at, updated_at
            )
            SELECT lower(trim(email)), 'completed', pipeline_run_id, pipeline_item_id,
                   created_at, updated_at
            FROM kakao_tasks
            WHERE coalesce(trim(payment_url), '') != ''
            """
        )
    )
    connection.execute(
        sa.text(
            """
            INSERT OR IGNORE INTO kakao_email_claims (
                email, state, pipeline_run_id, pipeline_item_id, created_at, updated_at
            )
            SELECT lower(trim(email)), 'active', pipeline_run_id, pipeline_item_id,
                   created_at, updated_at
            FROM kakao_tasks
            WHERE status IN ('queued', 'extracting')
            """
        )
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_kakao_email_claims_pipeline_item_id"),
        table_name="kakao_email_claims",
    )
    op.drop_index(
        op.f("ix_kakao_email_claims_pipeline_run_id"),
        table_name="kakao_email_claims",
    )
    op.drop_index(op.f("ix_kakao_email_claims_state"), table_name="kakao_email_claims")
    op.drop_table("kakao_email_claims")
