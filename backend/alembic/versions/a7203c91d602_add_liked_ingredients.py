"""Add canonical liked ingredients without changing existing profile values."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a7203c91d602"
down_revision = "f3b197a01c02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_nutrition_profiles",
        sa.Column(
            "liked_ingredients",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    # Destructive: application rollback should retain this additive column.
    op.drop_column("user_nutrition_profiles", "liked_ingredients")
