"""Enforce Unicode15 base-name identity without rewriting ingredient rows."""

from alembic import op

# This versioned module and its digest-pinned payload are immutable history.
from app.db.ddl.ingredient_identity_v1 import downgrade_statements, upgrade_statements

revision = "b205c8d15a01"
down_revision = "a7203c91d602"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in upgrade_statements():
        op.execute(statement)


def downgrade() -> None:
    for statement in downgrade_statements():
        op.execute(statement)
