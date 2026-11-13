"""Additive migration on a genuine servings schema; authorized mealio_test only."""

import asyncio
import json
from uuid import uuid4

import pytest
from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError

from tests import test_ingredient_portion_migration as portion_migration

migration_db = portion_migration.migration_db
PARENT = "d124b6e83a01"
REVISION = "e235c7f94b02"


def test_meal_type_offline_upgrade_and_parent():
    def refuse_connection(*args):
        pytest.fail("Offline migration must not connect to a database")

    event.listen(Engine, "do_connect", refuse_connection)
    try:
        sql = portion_migration.offline_upgrade_sql(f"{PARENT}:{REVISION}")
    finally:
        event.remove(Engine, "do_connect", refuse_connection)
    assert sql.startswith("BEGIN;") and sql.rstrip().endswith("COMMIT;")
    assert "ADD COLUMN meal_type VARCHAR(100)" in sql
    assert "NOT NULL" not in sql and "DEFAULT" not in sql
    config = portion_migration.Config(str(portion_migration.BACKEND / "alembic.ini"))
    config.set_main_option(
        "script_location", str(portion_migration.BACKEND / "alembic")
    )
    script = ScriptDirectory.from_config(config)
    assert script.get_revision(REVISION).down_revision == PARENT


@pytest.mark.parametrize("populated", [False, True])
async def test_meal_type_upgrade_preserves_legacy_fields_and_roundtrips(
    migration_db, populated
):
    db = migration_db
    await db.migrate("upgrade", PARENT)
    if populated:
        await db.seed(["50", "125.50"])
        await db.execute(
            "UPDATE recipes SET servings=7, description='Legacy', diet_type='custom', "
            "total_calories=17.23,total_protein_g=2.34,total_carbs_g=3.45,total_fat_g=4.56, "
            "created_at='2026-01-02T03:04:05Z',updated_at='2026-02-03T04:05:06Z'"
        )
        await db.execute("UPDATE recipe_ingredients SET quantity_g=123.45")
    before = await db.state()
    await db.migrate("upgrade", REVISION)
    after = await db.state()
    assert after["revision"] == [REVISION]
    for key in before:
        if key == "recipes":
            assert [json.loads(row) for row in after[key]] == [
                {**json.loads(row), "meal_type": None} for row in before[key]
            ]
        elif key == "columns":
            assert [
                row
                for row in after[key]
                if not (row[0] == "recipes" and row[1] == "meal_type")
            ] == before[key]
        elif key != "revision":
            assert after[key] == before[key]
    assert (
        await db.execute(
            "SELECT data_type,character_maximum_length,is_nullable,column_default "
            "FROM information_schema.columns WHERE table_schema='public' "
            "AND table_name='recipes' AND column_name='meal_type'"
        )
    ).one() == ("character varying", 100, "YES", None)
    # Model parity includes later recipe metadata and is checked only at head.
    await db.migrate("upgrade", "head")
    await asyncio.to_thread(command.check, db.config)
    await db.migrate("downgrade", REVISION)
    if populated:
        await db.execute("UPDATE recipes SET meal_type='dinner'")
    await db.migrate("downgrade", PARENT)
    assert await db.state() == before
    await db.migrate("upgrade", REVISION)
    assert await db.state() == after
    await db.migrate("upgrade", "head")
    await asyncio.to_thread(command.check, db.config)


async def test_sql_legacy_writer_unknown_null_and_length_limit(migration_db):
    db = migration_db
    await db.migrate("upgrade", REVISION)
    recipe = uuid4()
    await db.execute(
        "INSERT INTO recipes(id,title,instructions) VALUES (:id,'Old writer','Mix.')",
        {"id": recipe},
    )
    assert (await db.execute("SELECT meal_type FROM recipes")).scalar_one() is None
    await db.execute("UPDATE recipes SET meal_type=:value", {"value": "x" * 100})
    await db.engine.dispose()
    assert (await db.execute("SELECT meal_type FROM recipes")).scalar_one() == "x" * 100
    before = await db.state()
    with pytest.raises(DBAPIError) as error:
        await db.execute("UPDATE recipes SET meal_type=:value", {"value": "x" * 101})
    assert error.value.orig.sqlstate == "22001"
    assert await db.state() == before
    await db.execute("UPDATE recipes SET meal_type=NULL")
    assert (await db.execute("SELECT meal_type FROM recipes")).scalar_one() is None
