"""add totp secret

Revision ID: e8f6a4b2197c
Revises: c3a91e6f512d
Create Date: 2026-08-02
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e8f6a4b2197c"
down_revision: str | None = "c3a91e6f512d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("credentials") as batch_op:
        batch_op.add_column(sa.Column("totp_secret", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("credentials") as batch_op:
        batch_op.drop_column("totp_secret")
