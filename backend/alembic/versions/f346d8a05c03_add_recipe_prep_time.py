"""Persist optional recipe preparation time; unknown historical values stay null."""

from alembic import op
import sqlalchemy as sa

revision = "f346d8a05c03"
down_revision = "e235c7f94b02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "recipes", sa.Column("prep_time_minutes", sa.Integer(), nullable=True)
    )
    # A CHECK permits NULL; no historical duration is inferred or defaulted.
    op.create_check_constraint(
        "ck_recipes_prep_time_minutes_range",
        "recipes",
        "prep_time_minutes BETWEEN 1 AND 480",
    )


def downgrade() -> None:
    op.drop_constraint("ck_recipes_prep_time_minutes_range", "recipes", type_="check")
    op.drop_column("recipes", "prep_time_minutes")
