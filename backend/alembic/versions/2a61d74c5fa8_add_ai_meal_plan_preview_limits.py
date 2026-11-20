"""Store the active AI meal plan preview quota window per account."""

from alembic import op
import sqlalchemy as sa

revision = "2a61d74c5fa8"
down_revision = "a457b0d32c04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_meal_plan_preview_limits",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("user_id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.CheckConstraint("attempts > 0", name="ck_ai_meal_plan_preview_attempts"),
    )


def downgrade() -> None:
    op.drop_table("ai_meal_plan_preview_limits")
