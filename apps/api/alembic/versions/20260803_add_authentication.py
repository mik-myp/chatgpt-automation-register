"""add administrator authentication

Revision ID: 20260803_auth
Revises: 20260803_baseline
Create Date: 2026-08-03 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260803_auth"
down_revision: str | None = "20260803_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("username", sa.String(length=128), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column(
            "role",
            sa.Enum("admin", name="user_role", native_enum=False),
            nullable=False,
        ),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("username", name=op.f("uq_users_username")),
    )
    op.create_index(op.f("ix_users_username"), "users", ["username"], unique=True)
    op.create_table(
        "login_attempts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(length=128), nullable=False),
        sa.Column("client_address", sa.String(length=64), nullable=False),
        sa.Column("succeeded", sa.Boolean(), nullable=False),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_login_attempts")),
    )
    op.create_index(op.f("ix_login_attempts_username"), "login_attempts", ["username"])
    op.create_index(op.f("ix_login_attempts_client_address"), "login_attempts", ["client_address"])
    op.create_index(op.f("ix_login_attempts_attempted_at"), "login_attempts", ["attempted_at"])
    op.create_index(
        "ix_login_attempts_limit",
        "login_attempts",
        ["username", "client_address", "attempted_at"],
    )
    op.create_table(
        "setup_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("initialized", sa.Boolean(), nullable=False),
        sa.Column("initialized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("administrator_id", sa.String(length=36), nullable=True),
        sa.Column("master_key_verifier", sa.Text(), nullable=True),
        sa.CheckConstraint("id = 1", name=op.f("ck_setup_state_setup_state_singleton")),
        sa.ForeignKeyConstraint(
            ["administrator_id"],
            ["users.id"],
            name=op.f("fk_setup_state_administrator_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_setup_state")),
        sa.UniqueConstraint("administrator_id", name=op.f("uq_setup_state_administrator_id")),
    )
    setup_table = sa.table(
        "setup_state",
        sa.column("id", sa.Integer()),
        sa.column("initialized", sa.Boolean()),
    )
    op.bulk_insert(setup_table, [{"id": 1, "initialized": False}])
    op.create_table(
        "user_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("csrf_token_hash", sa.String(length=64), nullable=False),
        sa.Column("client_address", sa.String(length=64), nullable=False),
        sa.Column("user_agent", sa.String(length=512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idle_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_sessions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_sessions")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_user_sessions_token_hash")),
    )
    op.create_index(op.f("ix_user_sessions_user_id"), "user_sessions", ["user_id"])
    op.create_index(
        op.f("ix_user_sessions_token_hash"), "user_sessions", ["token_hash"], unique=True
    )
    op.create_index(
        "ix_user_sessions_expiry", "user_sessions", ["idle_expires_at", "absolute_expires_at"]
    )


def downgrade() -> None:
    op.drop_table("user_sessions")
    op.drop_table("setup_state")
    op.drop_table("login_attempts")
    op.drop_table("users")
