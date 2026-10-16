"""Enforce finite stored nutrition portions without repairing historical data.

Revision ID: f3b197a01c02
Revises: e9c4a7b2d610
"""

from alembic import op

revision = "f3b197a01c02"
down_revision = "e9c4a7b2d610"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Hold this lock through preflight and CHECK installation in Alembic's
    # transaction. A concurrent writer cannot slip between those operations.
    op.execute("LOCK TABLE nutrition_values IN ACCESS EXCLUSIVE MODE")
    # Execute the same preflight on the server online and in generated SQL.
    # Offline generation has no result rows for Python to inspect.
    op.execute(
        """
        DO $portion_preflight$
        DECLARE invalid_count bigint;
        BEGIN
            SELECT count(*) INTO invalid_count FROM nutrition_values
            WHERE NOT (portion_g BETWEEN 0.01 AND 999999.99);
            IF invalid_count > 0 THEN
                RAISE EXCEPTION USING MESSAGE = invalid_count::text
                    || ' invalid nutrition portion row(s); upgrade aborted. '
                    || 'A separate owner-authorized correction from a trustworthy source is required. '
                    || 'See docs/ingredient-portion-storage.md, then retry upgrade. '
                    || 'No data was repaired automatically.';
            END IF;
        END
        $portion_preflight$;
        """
    )
    # In PostgreSQL numeric NaN sorts above finite numbers, so the upper bound
    # rejects it. Positivity alone would not protect this invariant.
    op.create_check_constraint(
        "ck_nutrition_values_portion_g_bounds",
        "nutrition_values",
        "portion_g BETWEEN 0.01 AND 999999.99",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_nutrition_values_portion_g_bounds", "nutrition_values", type_="check"
    )
