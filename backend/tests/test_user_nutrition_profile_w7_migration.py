"""Destructive fixture use is restricted to explicitly authorized mealio_test."""

import asyncio
from uuid import uuid4

import asyncpg
import pytest
from alembic import command
from sqlalchemy import event
from sqlalchemy.engine import Engine

from tests import test_ingredient_portion_migration as portion_migration

migration_db = portion_migration.migration_db

PARENT = "f3b197a01c02"
REVISION = "a7203c91d602"


def test_likes_offline_sql_without_database_connection():
    def refuse(*args):
        pytest.fail("Offline migration cannot connect")

    event.listen(Engine, "do_connect", refuse)
    try:
        sql = portion_migration.offline_upgrade_sql(f"{PARENT}:{REVISION}")
    finally:
        event.remove(Engine, "do_connect", refuse)
    assert "ADD COLUMN liked_ingredients JSONB DEFAULT '[]'::jsonb NOT NULL" in sql
    assert sql.startswith("BEGIN;") and sql.rstrip().endswith("COMMIT;")


async def upgrade_likes(db, mode):
    if mode == "online":
        await db.migrate("upgrade", REVISION)
        return
    sql = portion_migration.offline_upgrade_sql(f"{PARENT}:{REVISION}")
    url = db.engine.url
    connection = await asyncpg.connect(
        host=url.host,
        port=url.port,
        user=url.username,
        password=url.password,
        database=url.database,
        timeout=10,
    )
    try:
        assert await connection.fetchval("SELECT current_database()") == "mealio_test"
        await connection.execute("SET statement_timeout = '60s'")
        await connection.execute("SET lock_timeout = '10s'")
        try:
            await connection.execute(sql)
        except BaseException:
            await connection.execute("ROLLBACK")
            raise
    finally:
        await connection.close()


@pytest.mark.parametrize("mode", ["online", "offline"])
@pytest.mark.parametrize("existing", [False, True])
async def test_likes_additive_upgrade_lossy_downgrade_reupgrade(
    migration_db, existing, mode
):
    db = migration_db
    await db.migrate("upgrade", PARENT)
    if existing:
        owner, profile = uuid4(), uuid4()
        await db.execute(
            "INSERT INTO users (id, email) VALUES (:id, 'w7-migration@example.com')",
            {"id": owner},
        )
        await db.execute(
            "INSERT INTO user_nutrition_profiles "
            "(id,user_id,goal,diet_type,daily_calories_target,allergies,disliked_ingredients,"
            "height_cm,weight_kg,weekly_food_budget_amount,budget_currency) "
            "VALUES (:id,:owner,'maintain','custom',2400,'[\"peanuts\"]','[\"celery\"]',180.0,80.00,50.12,'ZZZ')",
            {"id": profile, "owner": owner},
        )
    before = (
        (
            await db.execute(
                "SELECT to_jsonb(p) FROM user_nutrition_profiles p ORDER BY id"
            )
        )
        .scalars()
        .all()
    )
    await upgrade_likes(db, mode)
    after = (
        (
            await db.execute(
                "SELECT to_jsonb(p) FROM user_nutrition_profiles p ORDER BY id"
            )
        )
        .scalars()
        .all()
    )
    assert after == [{**row, "liked_ingredients": []} for row in before]
    if existing:
        await db.execute(
            'UPDATE user_nutrition_profiles SET liked_ingredients = \'["peanuts","rice","rice"]\''
        )
        await db.engine.dispose()
        assert (
            await db.execute("SELECT liked_ingredients FROM user_nutrition_profiles")
        ).scalar_one() == ["peanuts", "rice", "rice"]
    # Explicitly lossy only for likes; every old field, identity and timestamp survives.
    await db.migrate("downgrade", PARENT)
    assert (
        await db.execute(
            "SELECT to_jsonb(p) FROM user_nutrition_profiles p ORDER BY id"
        )
    ).scalars().all() == before
    await upgrade_likes(db, mode)
    assert (
        await db.execute(
            "SELECT to_jsonb(p) FROM user_nutrition_profiles p ORDER BY id"
        )
    ).scalars().all() == after
    assert (
        await db.execute("SELECT version_num FROM alembic_version")
    ).scalar_one() == REVISION
    # Real migrated schema must agree with model metadata.
    await asyncio.to_thread(command.check, db.config)
