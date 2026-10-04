"""extend nutrition profile for onboarding inputs

Revision ID: e9c4a7b2d610
Revises: b7e3c9a1d5f8

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e9c4a7b2d610"
down_revision: Union[str, None] = "b7e3c9a1d5f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user_nutrition_profiles", sa.Column("sex", sa.String(6), nullable=True)
    )
    op.add_column(
        "user_nutrition_profiles", sa.Column("birth_date", sa.Date, nullable=True)
    )
    op.add_column(
        "user_nutrition_profiles",
        sa.Column("height_cm", sa.Numeric(4, 1), nullable=True),
    )
    op.add_column(
        "user_nutrition_profiles",
        sa.Column("weight_kg", sa.Numeric(5, 2), nullable=True),
    )
    op.add_column(
        "user_nutrition_profiles",
        sa.Column("activity_level", sa.String(20), nullable=True),
    )
    op.add_column(
        "user_nutrition_profiles",
        sa.Column("max_cooking_time_minutes", sa.Integer, nullable=True),
    )
    op.add_column(
        "user_nutrition_profiles",
        sa.Column("weekly_food_budget_amount", sa.Numeric(9, 2), nullable=True),
    )
    op.add_column(
        "user_nutrition_profiles",
        sa.Column("budget_currency", sa.String(3), nullable=True),
    )
    op.create_check_constraint(
        "ck_nutrition_profile_sex",
        "user_nutrition_profiles",
        "sex IN ('male', 'female')",
    )
    op.create_check_constraint(
        "ck_nutrition_profile_birth_date",
        "user_nutrition_profiles",
        "birth_date >= DATE '1900-01-01' AND birth_date <= (clock_timestamp() AT TIME ZONE 'UTC')::date",
    )
    op.create_check_constraint(
        "ck_nutrition_profile_height_cm",
        "user_nutrition_profiles",
        "height_cm BETWEEN 50.0 AND 250.0",
    )
    op.create_check_constraint(
        "ck_nutrition_profile_weight_kg",
        "user_nutrition_profiles",
        "weight_kg BETWEEN 10.00 AND 500.00",
    )
    op.create_check_constraint(
        "ck_nutrition_profile_activity_level",
        "user_nutrition_profiles",
        "activity_level IN ('sedentary', 'lightly_active', 'moderately_active', 'very_active', 'extra_active')",
    )
    op.create_check_constraint(
        "ck_nutrition_profile_max_cooking_time_minutes",
        "user_nutrition_profiles",
        "max_cooking_time_minutes BETWEEN 1 AND 480",
    )
    op.create_check_constraint(
        "ck_nutrition_profile_weekly_food_budget_amount",
        "user_nutrition_profiles",
        "weekly_food_budget_amount BETWEEN 0.01 AND 1000000.00",
    )
    op.create_check_constraint(
        "ck_nutrition_profile_budget_currency",
        "user_nutrition_profiles",
        "char_length(budget_currency) = 3 AND budget_currency ~ '^[A-Z]{3}$'",
    )
    op.create_check_constraint(
        "ck_nutrition_profile_budget_pair",
        "user_nutrition_profiles",
        "(weekly_food_budget_amount IS NULL) = (budget_currency IS NULL)",
    )


def downgrade() -> None:
    # Original profile data survives; the eight added fields are lost.
    op.drop_constraint(
        "ck_nutrition_profile_budget_pair", "user_nutrition_profiles", type_="check"
    )
    op.drop_constraint(
        "ck_nutrition_profile_budget_currency", "user_nutrition_profiles", type_="check"
    )
    op.drop_constraint(
        "ck_nutrition_profile_weekly_food_budget_amount",
        "user_nutrition_profiles",
        type_="check",
    )
    op.drop_constraint(
        "ck_nutrition_profile_max_cooking_time_minutes",
        "user_nutrition_profiles",
        type_="check",
    )
    op.drop_constraint(
        "ck_nutrition_profile_activity_level", "user_nutrition_profiles", type_="check"
    )
    op.drop_constraint(
        "ck_nutrition_profile_weight_kg", "user_nutrition_profiles", type_="check"
    )
    op.drop_constraint(
        "ck_nutrition_profile_height_cm", "user_nutrition_profiles", type_="check"
    )
    op.drop_constraint(
        "ck_nutrition_profile_birth_date", "user_nutrition_profiles", type_="check"
    )
    op.drop_constraint(
        "ck_nutrition_profile_sex", "user_nutrition_profiles", type_="check"
    )
    op.drop_column("user_nutrition_profiles", "budget_currency")
    op.drop_column("user_nutrition_profiles", "weekly_food_budget_amount")
    op.drop_column("user_nutrition_profiles", "max_cooking_time_minutes")
    op.drop_column("user_nutrition_profiles", "activity_level")
    op.drop_column("user_nutrition_profiles", "weight_kg")
    op.drop_column("user_nutrition_profiles", "height_cm")
    op.drop_column("user_nutrition_profiles", "birth_date")
    op.drop_column("user_nutrition_profiles", "sex")
