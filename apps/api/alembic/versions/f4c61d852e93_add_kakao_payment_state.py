"""add kakao payment state

Revision ID: f4c61d852e93
Revises: e8f6a4b2197c
Create Date: 2026-08-02
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f4c61d852e93"
down_revision: str | None = "e8f6a4b2197c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("kakao_tasks") as batch_op:
        batch_op.add_column(sa.Column("payment_message", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column("payment_expires_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(sa.Column("payment_scanned", sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column("payment_successful", sa.Boolean(), nullable=True))
        batch_op.create_index("ix_kakao_tasks_payment_expires_at", ["payment_expires_at"])


def downgrade() -> None:
    with op.batch_alter_table("kakao_tasks") as batch_op:
        batch_op.drop_index("ix_kakao_tasks_payment_expires_at")
        batch_op.drop_column("payment_successful")
        batch_op.drop_column("payment_scanned")
        batch_op.drop_column("payment_expires_at")
        batch_op.drop_column("payment_message")
