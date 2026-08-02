"""preserve Kakao card history

Revision ID: b7e2c4d6f810
Revises: 9d5e7a1c3b2f
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7e2c4d6f810"
down_revision: str | None = "9d5e7a1c3b2f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("kakao_tasks") as batch_op:
        batch_op.add_column(sa.Column("card_code_snapshot", sa.Text(), nullable=True))
        batch_op.drop_constraint(
            batch_op.f("fk_kakao_tasks_card_id_kakao_cards"),
            type_="foreignkey",
        )
        batch_op.alter_column(
            "card_id",
            existing_type=sa.String(length=36),
            nullable=True,
        )
        batch_op.create_foreign_key(
            batch_op.f("fk_kakao_tasks_card_id_kakao_cards"),
            "kakao_cards",
            ["card_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.execute(
        sa.text(
            """
            UPDATE kakao_tasks
            SET card_code_snapshot = (
                SELECT kakao_cards.code
                FROM kakao_cards
                WHERE kakao_cards.id = kakao_tasks.card_id
            )
            WHERE card_code_snapshot IS NULL
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM kakao_tasks WHERE card_id IS NULL"))
    with op.batch_alter_table("kakao_tasks") as batch_op:
        batch_op.drop_constraint(
            batch_op.f("fk_kakao_tasks_card_id_kakao_cards"),
            type_="foreignkey",
        )
        batch_op.alter_column(
            "card_id",
            existing_type=sa.String(length=36),
            nullable=False,
        )
        batch_op.create_foreign_key(
            batch_op.f("fk_kakao_tasks_card_id_kakao_cards"),
            "kakao_cards",
            ["card_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.drop_column("card_code_snapshot")
