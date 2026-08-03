"""encrypt sensitive data at rest

Revision ID: 20260803_encryption
Revises: 20260803_auth
Create Date: 2026-08-03 13:00:00
"""

import json
from collections.abc import Sequence
from contextlib import suppress
from typing import Any

import sqlalchemy as sa

from alembic import op
from gpt_auto_register.core.encryption import (
    KEY_VERIFIER,
    PREFIX,
    decrypt_text,
    encrypt_text,
    protect_setting,
    reveal_setting,
    secret_fingerprint,
)

revision: str = "20260803_encryption"
down_revision: str | None = "20260803_auth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _encrypt_columns(table_name: str, primary_key: str, columns: list[str]) -> None:
    connection = op.get_bind()
    table = sa.table(
        table_name,
        sa.column(primary_key),
        *(sa.column(name) for name in columns),
    )
    for row in connection.execute(sa.select(table)).mappings():
        values = {
            name: encrypt_text(str(row[name]))
            if row[name] and not str(row[name]).startswith(PREFIX)
            else row[name]
            for name in columns
        }
        connection.execute(
            table.update().where(table.c[primary_key] == row[primary_key]).values(**values)
        )


def _encrypt_json_column(table_name: str, primary_key: str, column: str) -> None:
    connection = op.get_bind()
    table = sa.table(table_name, sa.column(primary_key), sa.column(column))
    for row in connection.execute(sa.select(table)).mappings():
        value = row[column]
        if value is None or str(value).startswith(PREFIX):
            continue
        if isinstance(value, str):
            with suppress(json.JSONDecodeError):
                value = json.loads(value)
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        connection.execute(
            table.update()
            .where(table.c[primary_key] == row[primary_key])
            .values({column: encrypt_text(encoded)})
        )


def upgrade() -> None:
    with op.batch_alter_table("outlook_accounts") as batch:
        batch.alter_column("client_id", existing_type=sa.String(length=255), type_=sa.Text())
    with op.batch_alter_table("credentials") as batch:
        batch.alter_column("device_id", existing_type=sa.String(length=255), type_=sa.Text())
    with op.batch_alter_table("registration_runs") as batch:
        batch.alter_column("config_snapshot", existing_type=sa.JSON(), type_=sa.Text())
    with op.batch_alter_table("pipeline_runs") as batch:
        batch.alter_column("config_snapshot", existing_type=sa.JSON(), type_=sa.Text())
    with op.batch_alter_table("kakao_cards") as batch:
        batch.add_column(sa.Column("code_fingerprint", sa.String(length=64), nullable=True))
        batch.drop_constraint("uq_kakao_cards_code", type_="unique")

    _encrypt_columns(
        "outlook_accounts",
        "email",
        ["password", "client_id", "refresh_token", "mail_url"],
    )
    _encrypt_columns(
        "credentials",
        "email",
        [
            "password",
            "access_token",
            "session_token",
            "refresh_token",
            "id_token",
            "device_id",
            "cookie_header",
            "totp_secret",
        ],
    )
    _encrypt_columns("pipeline_items", "id", ["card_code_snapshot"])
    _encrypt_columns("kakao_tasks", "id", ["card_code_snapshot"])
    _encrypt_json_column("registration_runs", "id", "config_snapshot")
    _encrypt_json_column("pipeline_runs", "id", "config_snapshot")

    connection = op.get_bind()
    cards = sa.table(
        "kakao_cards",
        sa.column("id"),
        sa.column("code"),
        sa.column("code_fingerprint"),
    )
    for row in connection.execute(sa.select(cards)).mappings():
        plain = str(row["code"])
        connection.execute(
            cards.update()
            .where(cards.c.id == row["id"])
            .values(code=encrypt_text(plain), code_fingerprint=secret_fingerprint(plain))
        )

    settings = sa.table(
        "app_settings",
        sa.column("key"),
        sa.column("value", sa.JSON()),
        sa.column("sensitive", sa.Boolean()),
    )
    for row in connection.execute(
        sa.select(settings).where(settings.c.sensitive.is_(True))
    ).mappings():
        value: Any = row["value"]
        if isinstance(value, dict) and "__encrypted_v1__" not in value:
            connection.execute(
                settings.update()
                .where(settings.c.key == row["key"])
                .values(value=protect_setting(value))
            )

    setup = sa.table("setup_state", sa.column("id"), sa.column("master_key_verifier"))
    connection.execute(
        setup.update().where(setup.c.id == 1).values(master_key_verifier=encrypt_text(KEY_VERIFIER))
    )

    with op.batch_alter_table("kakao_cards") as batch:
        batch.alter_column("code_fingerprint", existing_type=sa.String(length=64), nullable=False)
        batch.create_index("ix_kakao_cards_code_fingerprint", ["code_fingerprint"], unique=True)


def downgrade() -> None:
    connection = op.get_bind()

    def decrypt_columns(table_name: str, primary_key: str, columns: list[str]) -> None:
        table = sa.table(
            table_name,
            sa.column(primary_key),
            *(sa.column(name) for name in columns),
        )
        for row in connection.execute(sa.select(table)).mappings():
            values = {
                name: decrypt_text(str(row[name]))
                if row[name] and str(row[name]).startswith(PREFIX)
                else row[name]
                for name in columns
            }
            connection.execute(
                table.update().where(table.c[primary_key] == row[primary_key]).values(**values)
            )

    decrypt_columns(
        "outlook_accounts", "email", ["password", "client_id", "refresh_token", "mail_url"]
    )
    decrypt_columns(
        "credentials",
        "email",
        [
            "password",
            "access_token",
            "session_token",
            "refresh_token",
            "id_token",
            "device_id",
            "cookie_header",
            "totp_secret",
        ],
    )
    decrypt_columns("pipeline_items", "id", ["card_code_snapshot"])
    decrypt_columns("kakao_tasks", "id", ["card_code_snapshot"])
    decrypt_columns("kakao_cards", "id", ["code"])
    decrypt_columns("registration_runs", "id", ["config_snapshot"])
    decrypt_columns("pipeline_runs", "id", ["config_snapshot"])

    settings = sa.table(
        "app_settings",
        sa.column("key"),
        sa.column("value", sa.JSON()),
        sa.column("sensitive", sa.Boolean()),
    )
    for row in connection.execute(
        sa.select(settings).where(settings.c.sensitive.is_(True))
    ).mappings():
        value = row["value"]
        if isinstance(value, dict) and "__encrypted_v1__" in value:
            connection.execute(
                settings.update()
                .where(settings.c.key == row["key"])
                .values(value=reveal_setting(value))
            )
    setup = sa.table("setup_state", sa.column("id"), sa.column("master_key_verifier"))
    connection.execute(setup.update().where(setup.c.id == 1).values(master_key_verifier=None))

    with op.batch_alter_table("kakao_cards") as batch:
        batch.drop_index("ix_kakao_cards_code_fingerprint")
        batch.create_unique_constraint("uq_kakao_cards_code", ["code"])
        batch.drop_column("code_fingerprint")
    with op.batch_alter_table("pipeline_runs") as batch:
        batch.alter_column(
            "config_snapshot",
            existing_type=sa.Text(),
            type_=sa.JSON(),
            postgresql_using="config_snapshot::json",
        )
    with op.batch_alter_table("registration_runs") as batch:
        batch.alter_column(
            "config_snapshot",
            existing_type=sa.Text(),
            type_=sa.JSON(),
            postgresql_using="config_snapshot::json",
        )
    with op.batch_alter_table("credentials") as batch:
        batch.alter_column("device_id", existing_type=sa.Text(), type_=sa.String(length=255))
    with op.batch_alter_table("outlook_accounts") as batch:
        batch.alter_column("client_id", existing_type=sa.Text(), type_=sa.String(length=255))
