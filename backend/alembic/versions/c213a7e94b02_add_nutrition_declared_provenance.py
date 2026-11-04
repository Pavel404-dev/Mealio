"""Add optional declared provenance; downgrade irreversibly drops metadata."""

from alembic import op
import sqlalchemy as sa

revision = "c213a7e94b02"
down_revision = "b205c8d15a01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "nutrition_values", sa.Column("source_name", sa.String(255), nullable=True)
    )
    op.add_column(
        "nutrition_values",
        sa.Column("source_reference", sa.String(1000), nullable=True),
    )
    op.create_check_constraint(
        "ck_nutrition_values_source_pair",
        "nutrition_values",
        "source_reference IS NULL OR source_name IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_nutrition_values_source_pair", "nutrition_values", type_="check"
    )
    op.drop_column("nutrition_values", "source_reference")
    op.drop_column("nutrition_values", "source_name")
