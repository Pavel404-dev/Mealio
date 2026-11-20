"""Store account-scoped preview reservations and replayable results."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "3b72e85d61c9"
down_revision = "2a61d74c5fa8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_meal_plan_preview_idempotency",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("reservation_id", sa.UUID(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("preview", JSONB(none_as_null=True), nullable=True),
        sa.PrimaryKeyConstraint("user_id", "key_hash"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_ai_meal_plan_preview_idempotency_user_expiry",
        "ai_meal_plan_preview_idempotency",
        ["user_id", "expires_at"],
    )


def downgrade() -> None:
    op.drop_table("ai_meal_plan_preview_idempotency")
