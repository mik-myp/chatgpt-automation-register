"""cache card usage

Revision ID: c3a91e6f512d
Revises: ab57afc7b327
Create Date: 2026-08-02
"""

from collections.abc import Sequence

revision: str = "c3a91e6f512d"
down_revision: str | None = "ab57afc7b327"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Card usage cache is stored in app_settings for schema compatibility.
    pass


def downgrade() -> None:
    pass
