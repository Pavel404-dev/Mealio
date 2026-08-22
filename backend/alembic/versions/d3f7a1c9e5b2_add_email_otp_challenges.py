"""add email otp challenges

Revision ID: d3f7a1c9e5b2
Revises: a4d8c2e7f1b6
Create Date: 2026-08-22 00:10:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "d3f7a1c9e5b2"
down_revision: Union[str, None] = "a4d8c2e7f1b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "email_otp_challenges",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column(
            "purpose",
            sa.Enum(
                "email_verification",
                "password_reset",
                name="email_otp_purpose",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("target_email", sa.String(length=255), nullable=False),
        sa.Column("code_digest", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "failed_attempts",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "send_count",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
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
            "failed_attempts >= 0",
            name="ck_email_otp_challenges_failed_attempts_nonnegative",
        ),
        sa.CheckConstraint(
            "send_count >= 1",
            name="ck_email_otp_challenges_send_count_positive",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_email_otp_challenges_expires_at"),
        "email_otp_challenges",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_email_otp_challenges_user_purpose_email_created_at",
        "email_otp_challenges",
        ["user_id", "purpose", "target_email", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_email_otp_challenges_user_purpose_email_created_at",
        table_name="email_otp_challenges",
    )
    op.drop_index(
        op.f("ix_email_otp_challenges_expires_at"),
        table_name="email_otp_challenges",
    )
    op.drop_table("email_otp_challenges")
