"""snapshot pipeline mail URL

Revision ID: 9d5e7a1c3b2f
Revises: f4c61d852e93
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "9d5e7a1c3b2f"
down_revision: str | None = "f4c61d852e93"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("pipeline_items") as batch_op:
        batch_op.add_column(sa.Column("mail_url_snapshot", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("pipeline_items") as batch_op:
        batch_op.drop_column("mail_url_snapshot")
