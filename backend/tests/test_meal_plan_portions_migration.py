"""Additive portion DDL and guarded rollback on approved mealio_test only."""

import asyncio
import json
from decimal import Decimal
from io import StringIO
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError

from tests import test_ingredient_portion_migration as migrations
from tests.db_target import verify_connection

migration_db = migrations.migration_db
PARENT = "f346d8a05c03"
REVISION = "a457b0d32c04"
CHECK = "ck_meal_plan_items_planned_servings"


def test_portions_offline_ddl_and_single_head():
    def refuse(*args):
        pytest.fail("Offline migration must not connect")

    output = StringIO()
    config = Config(str(migrations.BACKEND / "alembic.ini"), output_buffer=output)
    config.set_main_option("script_location", str(migrations.BACKEND / "alembic"))
    event.listen(Engine, "do_connect", refuse)
    try:
        sql = migrations.offline_upgrade_sql(f"{PARENT}:{REVISION}")
        command.downgrade(config, f"{REVISION}:{PARENT}", sql=True)
    finally:
        event.remove(Engine, "do_connect", refuse)
    assert sql.startswith("BEGIN;") and sql.rstrip().endswith("COMMIT;")
    assert "ADD COLUMN planned_servings NUMERIC" in sql
    assert (
        "NOT NULL" not in sql
        and "DEFAULT" not in sql
        and "UPDATE meal_plan_items" not in sql
    )
    assert "planned_servings BETWEEN 0.01 AND 12" in sql
    assert "planned_servings = trunc(planned_servings, 2)" in sql
    down = output.getvalue()
    assert down.index(
        "LOCK TABLE meal_plan_items IN ACCESS EXCLUSIVE MODE"
    ) < down.index("IF EXISTS")
    assert (
        down.index("RAISE EXCEPTION")
        < down.index("DROP CONSTRAINT")
        < down.index("DROP COLUMN")
    )
    script = ScriptDirectory.from_config(config)
    assert len(script.get_heads()) == 1
    assert REVISION in {
        revision.revision for revision in script.iterate_revisions("head", "base")
    }
    assert script.get_revision(REVISION).down_revision == PARENT


async def state(db):
    result = await db.state()
    for table in ("meal_plans", "meal_plan_items"):
        result[table] = (
            (await db.execute(f"SELECT to_jsonb(t)::text FROM {table} t ORDER BY id"))
            .scalars()
            .all()
        )
    return result


async def seed_plan(db):
    await db.seed(["100"])
    await db.execute(
        "UPDATE recipes SET servings=7, prep_time_minutes=45, meal_type='brunch'"
    )
    plan = uuid4()
    await db.execute(
        "INSERT INTO meal_plans(id,user_id,title,start_date,end_date) "
        "SELECT :plan,id,'Legacy','2026-11-17','2026-11-18' FROM users",
        {"plan": plan},
    )
    await db.execute(
        "INSERT INTO meal_plan_items(id,meal_plan_id,recipe_id,planned_date,meal_type) "
        "SELECT :item,:plan,id,'2026-11-17','brunch' FROM recipes",
        {"item": uuid4(), "plan": plan},
    )


@pytest.mark.parametrize("populated", [False, True])
async def test_portions_additive_upgrade_preserves_data_and_null_roundtrip(
    migration_db, populated
):
    db = migration_db
    await db.migrate("upgrade", PARENT)
    if populated:
        await seed_plan(db)
    before = await state(db)
    await db.migrate("upgrade", REVISION)
    after = await state(db)
    for key in before:
        if key == "meal_plan_items":
            assert [json.loads(row) for row in after[key]] == [
                {**json.loads(row), "planned_servings": None} for row in before[key]
            ]
        elif key == "columns":
            assert [
                row
                for row in after[key]
                if row[:2] != ("meal_plan_items", "planned_servings")
            ] == before[key]
        elif key == "constraints":
            assert [row for row in after[key] if row[1] != CHECK] == before[key]
            assert len([row for row in after[key] if row[1] == CHECK]) == 1
        elif key != "revision":
            assert after[key] == before[key]
    assert after["revision"] == [REVISION]
    assert (
        await db.execute(
            "SELECT numeric_precision,numeric_scale,is_nullable,column_default "
            "FROM information_schema.columns WHERE table_schema='public' "
            "AND table_name='meal_plan_items' AND column_name='planned_servings'"
        )
    ).one() == (None, None, "YES", None)
    await db.migrate("downgrade", PARENT)
    assert await state(db) == before
    await db.migrate("upgrade", REVISION)
    assert await state(db) == after
    # Alembic compares the head schema with the current model metadata.
    await db.migrate("upgrade", "head")
    await asyncio.to_thread(command.check, db.config)


async def test_sql_precision_old_writer_and_lossy_downgrade_rejection(migration_db):
    db = migration_db
    await db.migrate("upgrade", REVISION)
    await seed_plan(db)  # Old writer omits the new field.
    assert (
        await db.execute("SELECT planned_servings FROM meal_plan_items")
    ).scalar_one() is None
    for value in ["0.01", "0.5", "1.2500", "12", None]:
        await db.execute(
            "UPDATE meal_plan_items SET planned_servings=CAST(:value AS numeric)",
            {"value": value},
        )
        await db.engine.dispose()
        assert (
            await db.execute("SELECT planned_servings FROM meal_plan_items")
        ).scalar_one() == (None if value is None else Decimal(value))
    await db.execute("UPDATE meal_plan_items SET planned_servings=0.5")
    await db.execute("UPDATE meal_plan_items SET meal_type='legacy-rename'")
    before = await state(db)
    for value in [
        "0",
        "-1",
        "12.01",
        "12.001",
        "1.005",
        "0.001",
        "NaN",
        "Infinity",
        "-Infinity",
    ]:
        with pytest.raises(DBAPIError) as error:
            await db.execute(
                "UPDATE meal_plan_items SET planned_servings=CAST(:value AS numeric)",
                {"value": value},
            )
        assert error.value.orig.sqlstate == "23514"
        assert error.value.orig.__cause__.constraint_name == CHECK
        assert await state(db) == before
    with pytest.raises(DBAPIError, match="Cannot drop planned_servings"):
        await db.migrate("downgrade", PARENT)
    assert await state(db) == before
    await db.execute("UPDATE meal_plan_items SET planned_servings=NULL")
    await db.migrate("downgrade", PARENT)
    assert (
        await db.execute("SELECT version_num FROM alembic_version")
    ).scalar_one() == PARENT


async def test_concurrent_portion_commit_blocks_lossy_downgrade(migration_db):
    db = migration_db
    await db.migrate("upgrade", REVISION)
    await seed_plan(db)
    async with db.engine.connect() as writer:
        await verify_connection(writer)
        await writer.execute(text("UPDATE meal_plan_items SET planned_servings=0.5"))
        downgrade = asyncio.create_task(db.migrate("downgrade", PARENT))
        try:
            await migrations.wait_for_blocked_query(db, "LOCK TABLE meal_plan_items")
            await writer.commit()
            with pytest.raises(DBAPIError, match="Cannot drop planned_servings"):
                await asyncio.wait_for(downgrade, timeout=10)
        finally:
            await writer.rollback()
            await asyncio.gather(downgrade, return_exceptions=True)
    assert (
        await db.execute("SELECT planned_servings FROM meal_plan_items")
    ).scalar_one() == Decimal("0.5")
    assert (
        await db.execute("SELECT version_num FROM alembic_version")
    ).scalar_one() == REVISION
