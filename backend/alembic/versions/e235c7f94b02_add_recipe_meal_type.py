"""Persist optional recipe meal type; historical classifications stay unknown."""

from alembic import op
import sqlalchemy as sa

revision = "e235c7f94b02"
down_revision = "d124b6e83a01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("recipes", sa.Column("meal_type", sa.String(100), nullable=True))


def downgrade() -> None:
    # Drops only classification metadata, never planner slots or recipe totals.
    op.drop_column("recipes", "meal_type")
