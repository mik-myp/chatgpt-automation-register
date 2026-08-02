"""align pipeline and Kakao claim enum types

Revision ID: 7b1d5e3f9a20
Revises: 2f8c7a91d4e6
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "7b1d5e3f9a20"
down_revision: str | None = "2f8c7a91d4e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

pipeline_run_kind = sa.Enum(
    "registration",
    "account_security",
    "kakao",
    name="pipeline_run_kind",
    native_enum=False,
)
kakao_claim_state = sa.Enum(
    "active",
    "completed",
    name="kakao_claim_state",
    native_enum=False,
)


def upgrade() -> None:
    with op.batch_alter_table("pipeline_runs") as batch_op:
        batch_op.alter_column(
            "kind",
            existing_type=sa.String(length=32),
            type_=pipeline_run_kind,
            existing_nullable=False,
            existing_server_default=sa.text("'registration'"),
        )
    with op.batch_alter_table("kakao_email_claims") as batch_op:
        batch_op.alter_column(
            "state",
            existing_type=sa.String(length=32),
            type_=kakao_claim_state,
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("kakao_email_claims") as batch_op:
        batch_op.alter_column(
            "state",
            existing_type=kakao_claim_state,
            type_=sa.String(length=32),
            existing_nullable=False,
        )
    with op.batch_alter_table("pipeline_runs") as batch_op:
        batch_op.alter_column(
            "kind",
            existing_type=pipeline_run_kind,
            type_=sa.String(length=32),
            existing_nullable=False,
            existing_server_default=sa.text("'registration'"),
        )
