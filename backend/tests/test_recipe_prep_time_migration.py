"""Optional duration on genuine meal-type parent DDL; authorized mealio_test only."""

import asyncio
import json
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError

from tests import test_ingredient_portion_migration as portion_migration

migration_db = portion_migration.migration_db
PARENT = "e235c7f94b02"
REVISION = "f346d8a05c03"
CHECK = "ck_recipes_prep_time_minutes_range"


def test_duration_offline_upgrade_and_single_head():
    def refuse_connection(*args):
        pytest.fail("Offline migration must not connect to a database")

    event.listen(Engine, "do_connect", refuse_connection)
    try:
        sql = portion_migration.offline_upgrade_sql(f"{PARENT}:{REVISION}")
    finally:
        event.remove(Engine, "do_connect", refuse_connection)
    assert sql.startswith("BEGIN;") and sql.rstrip().endswith("COMMIT;")
    assert "ADD COLUMN prep_time_minutes INTEGER" in sql
    assert "NOT NULL" not in sql and "DEFAULT" not in sql
    assert f"ADD CONSTRAINT {CHECK} CHECK (prep_time_minutes BETWEEN 1 AND 480)" in sql
    config = Config(str(portion_migration.BACKEND / "alembic.ini"))
    config.set_main_option(
        "script_location", str(portion_migration.BACKEND / "alembic")
    )
    script = ScriptDirectory.from_config(config)
    assert script.get_heads() == [REVISION]
    assert script.get_revision(REVISION).down_revision == PARENT


@pytest.mark.parametrize("populated", [False, True])
async def test_duration_additive_upgrade_and_lossy_roundtrip(migration_db, populated):
    db = migration_db
    await db.migrate("upgrade", PARENT)
    if populated:
        await db.seed(["50", "125.50"])
        await db.execute(
            "UPDATE recipes SET servings=7,meal_type='brunch',description='Legacy',diet_type='custom', "
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
                {**json.loads(row), "prep_time_minutes": None} for row in before[key]
            ]
        elif key == "columns":
            assert [
                row
                for row in after[key]
                if not (row[0] == "recipes" and row[1] == "prep_time_minutes")
            ] == before[key]
        elif key == "constraints":
            assert [row for row in after[key] if row[1] != CHECK] == before[key]
            assert len([row for row in after[key] if row[1] == CHECK]) == 1
        elif key != "revision":
            assert after[key] == before[key]
    assert (
        await db.execute(
            "SELECT data_type,is_nullable,column_default FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='recipes' AND column_name='prep_time_minutes'"
        )
    ).one() == ("integer", "YES", None)
    await asyncio.to_thread(command.check, db.config)
    if populated:
        await db.execute("UPDATE recipes SET prep_time_minutes=480")
    await db.migrate("downgrade", PARENT)
    assert await db.state() == before
    await db.migrate("upgrade", REVISION)
    assert await db.state() == after
    await asyncio.to_thread(command.check, db.config)


async def test_sql_unknown_default_bounds_and_old_writer_preservation(migration_db):
    db = migration_db
    await db.migrate("upgrade", REVISION)
    await db.execute(
        "INSERT INTO recipes(id,title,instructions) VALUES (:id,'Old writer','Mix.')",
        {"id": uuid4()},
    )
    assert (
        await db.execute("SELECT prep_time_minutes FROM recipes")
    ).scalar_one() is None
    for minutes in [1, 480, None]:
        await db.execute(
            "UPDATE recipes SET prep_time_minutes=:value", {"value": minutes}
        )
        await db.engine.dispose()
        assert (
            await db.execute("SELECT prep_time_minutes FROM recipes")
        ).scalar_one() == minutes
    await db.execute("UPDATE recipes SET prep_time_minutes=45")
    await db.execute("UPDATE recipes SET title='Old writer rename'")
    assert (
        await db.execute("SELECT prep_time_minutes FROM recipes")
    ).scalar_one() == 45
    before = await db.state()
    for minutes in [0, -1, 481]:
        with pytest.raises(DBAPIError) as error:
            await db.execute(
                "UPDATE recipes SET prep_time_minutes=:value", {"value": minutes}
            )
        assert error.value.orig.sqlstate == "23514"
        assert error.value.orig.__cause__.constraint_name == CHECK
        assert await db.state() == before
