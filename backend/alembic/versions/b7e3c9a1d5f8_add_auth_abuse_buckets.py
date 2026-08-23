"""add auth abuse buckets

Revision ID: b7e3c9a1d5f8
Revises: d3f7a1c9e5b2
Create Date: 2026-08-22 22:55:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "b7e3c9a1d5f8"
down_revision: Union[str, None] = "d3f7a1c9e5b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "auth_abuse_buckets",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "action",
            sa.Enum(
                "login",
                "register",
                "password_reset_request",
                "password_reset_confirm",
                "email_verification_request",
                "email_verification_confirm",
                name="auth_abuse_action",
                native_enum=False,
                create_constraint=True,
                length=64,
            ),
            nullable=False,
        ),
        sa.Column(
            "dimension",
            sa.Enum(
                "ip",
                "email",
                "user",
                name="auth_abuse_dimension",
                native_enum=False,
                create_constraint=True,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("identifier_digest", sa.String(length=64), nullable=False),
        sa.Column(
            "request_count",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "request_count >= 1",
            name="ck_auth_abuse_buckets_request_count_positive",
        ),
        sa.CheckConstraint(
            "expires_at > window_started_at",
            name="ck_auth_abuse_buckets_window_positive",
        ),
        sa.CheckConstraint(
            "char_length(identifier_digest) = 64",
            name="ck_auth_abuse_buckets_identifier_digest_length",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "action",
            "dimension",
            "identifier_digest",
            name="uq_auth_abuse_buckets_identity",
        ),
    )
    op.create_index(
        "ix_auth_abuse_buckets_expires_at",
        "auth_abuse_buckets",
        ["expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_auth_abuse_buckets_expires_at",
        table_name="auth_abuse_buckets",
    )
    op.drop_table("auth_abuse_buckets")
