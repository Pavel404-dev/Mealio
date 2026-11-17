"""Optional planned portions; existing assignments keep whole-recipe semantics."""

from alembic import op
import sqlalchemy as sa

revision = "a457b0d32c04"
down_revision = "f346d8a05c03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # No typmod: reject extra precision rather than silently rounding on storage.
    op.add_column(
        "meal_plan_items", sa.Column("planned_servings", sa.Numeric(), nullable=True)
    )
    op.create_check_constraint(
        "ck_meal_plan_items_planned_servings",
        "meal_plan_items",
        "planned_servings BETWEEN 0.01 AND 12 "
        "AND planned_servings = trunc(planned_servings, 2)",
    )


def downgrade() -> None:
    # A downgrade must not silently reinterpret portions as whole recipes.
    # Hold the lock until DROP so a concurrent writer cannot bypass the check.
    op.execute("LOCK TABLE meal_plan_items IN ACCESS EXCLUSIVE MODE")
    op.execute(
        """DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM meal_plan_items WHERE planned_servings IS NOT NULL) THEN
            RAISE EXCEPTION 'Cannot drop planned_servings while explicit portions exist';
        END IF;
        END $$"""
    )
    op.drop_constraint(
        "ck_meal_plan_items_planned_servings", "meal_plan_items", type_="check"
    )
    op.drop_column("meal_plan_items", "planned_servings")
