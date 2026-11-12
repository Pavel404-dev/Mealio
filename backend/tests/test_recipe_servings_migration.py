"""Recipe servings on a genuine parent schema; requires authorized mealio_test."""

import asyncio
import json
from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError

from tests import test_ingredient_portion_migration as portion_migration

migration_db = portion_migration.migration_db
PARENT = "c213a7e94b02"
REVISION = "d124b6e83a01"
CHECK = "ck_recipes_servings_range"


def test_servings_offline_upgrade_does_not_connect():
    def refuse_connection(*args):
        pytest.fail("Offline migration must not connect to a database")

    event.listen(Engine, "do_connect", refuse_connection)
    try:
        sql = portion_migration.offline_upgrade_sql(f"{PARENT}:{REVISION}")
    finally:
        event.remove(Engine, "do_connect", refuse_connection)
    assert sql.startswith("BEGIN;") and sql.rstrip().endswith("COMMIT;")
    assert "ADD COLUMN servings INTEGER DEFAULT '1' NOT NULL" in sql
    assert f"ADD CONSTRAINT {CHECK} CHECK (servings BETWEEN 1 AND 12)" in sql


@pytest.mark.parametrize("populated", [False, True])
async def test_servings_upgrade_preserves_legacy_data_and_roundtrips(
    migration_db, populated
):
    db = migration_db
    await db.migrate("upgrade", PARENT)
    if populated:
        await db.seed(["50", "125.50"])
        # Existing totals may be stale; this migration must not recalculate them.
        await db.execute(
            "UPDATE recipes SET description='Legacy description', diet_type='custom', "
            "total_calories=17.23, total_protein_g=2.34, "
            "total_carbs_g=3.45, total_fat_g=4.56, "
            "created_at='2026-01-02T03:04:05Z', updated_at='2026-02-03T04:05:06Z'"
        )
        await db.execute("UPDATE recipe_ingredients SET quantity_g=123.45")
    before = await db.state()
    await db.migrate("upgrade", REVISION)
    after = await db.state()
    assert after["revision"] == [REVISION]
    for key in before:
        if key == "recipes":
            assert [json.loads(row) for row in after[key]] == [
                {**json.loads(row), "servings": 1} for row in before[key]
            ]
        elif key == "columns":
            assert [
                row
                for row in after[key]
                if not (row[0] == "recipes" and row[1] == "servings")
            ] == before[key]
        elif key == "constraints":
            assert [row for row in after[key] if row[1] != CHECK] == before[key]
            assert len([row for row in after[key] if row[1] == CHECK]) == 1
        elif key != "revision":
            assert after[key] == before[key]
    assert (
        await db.execute(
            "SELECT data_type,is_nullable,column_default FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='recipes' AND column_name='servings'"
        )
    ).one() == ("integer", "NO", "1")
    # Current metadata includes later recipe metadata; parity is head-only.
    await db.migrate("upgrade", "head")
    await asyncio.to_thread(command.check, db.config)
    await db.migrate("downgrade", REVISION)
    # Downgrade loses only servings; all legacy fields and related rows survive.
    if populated:
        await db.execute("UPDATE recipes SET servings=12")
    await db.migrate("downgrade", PARENT)
    assert await db.state() == before
    await db.migrate("upgrade", REVISION)
    assert await db.state() == after
    await db.migrate("upgrade", "head")
    await asyncio.to_thread(command.check, db.config)


async def test_servings_sql_default_bounds_and_nullability(migration_db):
    db = migration_db
    await db.migrate("upgrade", REVISION)
    recipe = uuid4()
    await db.execute(
        "INSERT INTO recipes(id,title,instructions) VALUES (:id,'Old writer','Mix.')",
        {"id": recipe},
    )
    assert (
        await db.execute("SELECT servings FROM recipes WHERE id=:id", {"id": recipe})
    ).scalar_one() == 1
    for servings, sqlstate in [(0, "23514"), (13, "23514"), (None, "23502")]:
        before = await db.state()
        with pytest.raises(DBAPIError) as error:
            await db.execute(
                "UPDATE recipes SET servings=:servings WHERE id=:id",
                {"id": recipe, "servings": servings},
            )
        assert error.value.orig.sqlstate == sqlstate
        if servings is not None:
            assert error.value.orig.__cause__.constraint_name == CHECK
        assert await db.state() == before
    await db.execute("UPDATE recipes SET servings=12 WHERE id=:id", {"id": recipe})
    await db.engine.dispose()
    assert (
        await db.execute("SELECT servings FROM recipes WHERE id=:id", {"id": recipe})
    ).scalar_one() == 12
