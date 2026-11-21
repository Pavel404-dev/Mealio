"""Store evidence for reviewed ingredient allergen statuses."""

from alembic import op
import sqlalchemy as sa

from app.db.ddl import ingredient_allergen_verification_v1 as verification

revision = "8e42c91b73a6"
down_revision = "3b72e85d61c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ingredient_allergen_verifications",
        sa.Column("ingredient_id", sa.UUID(), nullable=False),
        sa.Column("allergen_key", sa.String(255, collation="C"), nullable=False),
        sa.Column("status", sa.String(8), nullable=False),
        sa.Column("source_name", sa.String(255), nullable=False),
        sa.Column("source_reference", sa.String(1000), nullable=False),
        sa.Column(
            "verified_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("ingredient_id", "allergen_key"),
        sa.ForeignKeyConstraint(
            ["ingredient_id"], ["ingredients.id"], ondelete="CASCADE"
        ),
        sa.CheckConstraint(
            "status IN ('absent', 'present', 'possible')",
            name="ck_ingredient_allergen_verifications_status",
        ),
        sa.CheckConstraint(
            "btrim(allergen_key) <> '' AND btrim(source_name) <> '' "
            "AND btrim(source_reference) <> ''",
            name="ck_ingredient_allergen_verifications_evidence",
        ),
    )
    op.execute(verification.REVOKE_FUNCTION)
    op.execute(verification.REVOKE_TRIGGER)


def downgrade() -> None:
    op.execute(verification.DROP_REVOKE_TRIGGER)
    op.execute(verification.DROP_REVOKE_FUNCTION)
    op.drop_table("ingredient_allergen_verifications")
