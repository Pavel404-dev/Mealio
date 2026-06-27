"""add user nutrition profiles

Revision ID: b4f2a8d6c913
Revises: 619f1b83b519
Create Date: 2026-06-27 19:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b4f2a8d6c913"
down_revision: Union[str, None] = "619f1b83b519"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_nutrition_profiles",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column(
            "goal",
            sa.String(length=50),
            server_default="maintain",
            nullable=False,
        ),
        sa.Column(
            "diet_type",
            sa.String(length=100),
            nullable=True,
        ),
        sa.Column("daily_calories_target", sa.Integer(), nullable=True),
        sa.Column("daily_protein_target_g", sa.Integer(), nullable=True),
        sa.Column("daily_carbs_target_g", sa.Integer(), nullable=True),
        sa.Column("daily_fat_target_g", sa.Integer(), nullable=True),
        sa.Column(
            "allergies",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "disliked_ingredients",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "preferred_meals_per_day",
            sa.Integer(),
            nullable=True,
        ),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )


def downgrade() -> None:
    op.drop_table("user_nutrition_profiles")
