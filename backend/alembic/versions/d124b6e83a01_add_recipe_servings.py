"""Persist recipe servings; downgrade loses only the serving count."""

from alembic import op
import sqlalchemy as sa

revision = "d124b6e83a01"
down_revision = "c213a7e94b02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # One is a compatibility convention, not an inferred historical count.
    op.add_column(
        "recipes",
        sa.Column("servings", sa.Integer(), server_default="1", nullable=False),
    )
    op.create_check_constraint(
        "ck_recipes_servings_range", "recipes", "servings BETWEEN 1 AND 12"
    )


def downgrade() -> None:
    op.drop_constraint("ck_recipes_servings_range", "recipes", type_="check")
    op.drop_column("recipes", "servings")
