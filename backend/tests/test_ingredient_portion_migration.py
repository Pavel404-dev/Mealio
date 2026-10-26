"""Real Alembic upgrades on disposable mealio_test, never metadata.create_all.

These after-fix tests are separate from the byte-identical baseline regressions.
Each case owns the public schema/revision state and validates its target first.
"""

import asyncio
import os
import threading
from io import StringIO
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import event, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from tests.db_target import target_url, verify_connection, verify_asyncpg

PARENT = "e9c4a7b2d610"
REVISION = "f3b197a01c02"
CHECK = "ck_nutrition_values_portion_g_bounds"
BACKEND = Path(__file__).resolve().parents[1]


def offline_upgrade_sql(revision):
    output = StringIO()
    config = Config(str(BACKEND / "alembic.ini"), output_buffer=output)
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    command.upgrade(config, revision, sql=True)
    return output.getvalue()


@pytest.mark.parametrize("revision", [f"{PARENT}:{REVISION}", "head"])
def test_offline_upgrade_generates_transactional_preflight_without_connection(revision):
    def refuse_connection(*args):
        pytest.fail("Offline generation must not connect to a database")

    event.listen(Engine, "do_connect", refuse_connection)
    try:
        sql = offline_upgrade_sql(revision)
    finally:
        event.remove(Engine, "do_connect", refuse_connection)
    assert sql.startswith("BEGIN;")
    assert sql.rstrip().endswith("COMMIT;")
    assert sql.index("LOCK TABLE nutrition_values") < sql.index("SELECT count(*)")
    assert sql.index("SELECT count(*)") < sql.index(f"ADD CONSTRAINT {CHECK}")
    assert "owner-authorized" in sql
    assert "docs/ingredient-portion-storage.md" in sql
    assert "RAISE EXCEPTION" in sql


class MigrationDatabase:
    def __init__(self, url):
        self.engine = create_async_engine(url, poolclass=NullPool)
        self.config = Config(str(BACKEND / "alembic.ini"))
        self.config.set_main_option("script_location", str(BACKEND / "alembic"))

    async def execute(self, sql, params=None):
        async with self.engine.begin() as connection:
            await verify_connection(connection)
            return await connection.execute(text(sql), params or {})

    async def reset(self):
        async with self.engine.begin() as connection:
            await verify_connection(connection)
            await connection.execute(text("DROP SCHEMA public CASCADE"))
            await connection.execute(text("CREATE SCHEMA public"))

    async def migrate(self, direction, revision):
        await self.execute("SELECT 1")
        await asyncio.to_thread(getattr(command, direction), self.config, revision)

    async def upgrade(self, mode):
        if mode == "online":
            await self.migrate("upgrade", REVISION)
            return
        sql = offline_upgrade_sql(f"{PARENT}:{REVISION}")
        url = self.engine.url
        connection = await asyncpg.connect(
            host=url.host,
            port=url.port,
            user=url.username,
            password=url.password,
            database=url.database,
            timeout=10,
        )
        try:
            await verify_asyncpg(connection)
            await connection.execute("SET statement_timeout = '60s'")
            await connection.execute("SET lock_timeout = '10s'")
            # Submit the complete, unmodified output, including BEGIN/COMMIT.
            # Do not split at semicolons inside the PostgreSQL DO block.
            try:
                await connection.execute(sql)
            except BaseException:
                await connection.execute("ROLLBACK")
                raise
        finally:
            await connection.close()

    async def state(self):
        result = {}
        for table in (
            "ingredients",
            "nutrition_values",
            "users",
            "recipes",
            "recipe_ingredients",
            "user_ingredients",
        ):
            result[table] = (
                (
                    await self.execute(
                        f"SELECT to_jsonb(t)::text FROM {table} t ORDER BY id"
                    )
                )
                .scalars()
                .all()
            )
        result["revision"] = (
            (await self.execute("SELECT version_num FROM alembic_version"))
            .scalars()
            .all()
        )
        result["constraints"] = (
            await self.execute(
                "SELECT c.relname, con.conname, pg_get_constraintdef(con.oid) "
                "FROM pg_constraint con JOIN pg_class c ON c.oid = con.conrelid "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' ORDER BY c.relname, con.conname"
            )
        ).all()
        result["columns"] = (
            await self.execute(
                "SELECT table_name, column_name, data_type, numeric_precision, "
                "numeric_scale, is_nullable, column_default FROM information_schema.columns "
                "WHERE table_schema = 'public' ORDER BY table_name, ordinal_position"
            )
        ).all()
        result["indexes"] = (
            await self.execute(
                "SELECT tablename, indexname, indexdef FROM pg_indexes "
                "WHERE schemaname = 'public' ORDER BY tablename, indexname"
            )
        ).all()
        return result

    async def seed(self, portions):
        user, recipe = uuid4(), uuid4()
        await self.execute(
            "INSERT INTO users (id, email) VALUES (:id, 'f3-migration@example.com')",
            {"id": user},
        )
        await self.execute(
            "INSERT INTO recipes (id, created_by_user_id, title, instructions) "
            "VALUES (:id, :user, 'F3 migration', 'Mix.')",
            {"id": recipe, "user": user},
        )
        ids = []
        for index, portion in enumerate(portions):
            ingredient = uuid4()
            ids.append(ingredient)
            await self.execute(
                "INSERT INTO ingredients (id, name) VALUES (:id, :name)",
                {"id": ingredient, "name": f"F3 migration {index}"},
            )
            await self.execute(
                "INSERT INTO nutrition_values (id, ingredient_id, calories, portion_g) "
                "VALUES (:id, :ingredient, 1, CAST(:portion AS numeric))",
                {"id": uuid4(), "ingredient": ingredient, "portion": portion},
            )
            await self.execute(
                "INSERT INTO recipe_ingredients (id, recipe_id, ingredient_id, quantity_g) "
                "VALUES (:id, :recipe, :ingredient, 1)",
                {"id": uuid4(), "recipe": recipe, "ingredient": ingredient},
            )
            await self.execute(
                "INSERT INTO user_ingredients (id, user_id, ingredient_id, quantity_g) "
                "VALUES (:id, :user, :ingredient, 1)",
                {"id": uuid4(), "user": user, "ingredient": ingredient},
            )
        return ids


@pytest.fixture
async def migration_db():
    # Never fall back to DATABASE_URL, a developer .env or an arbitrary target.
    raw_url = os.environ["TEST_DATABASE_URL"]
    url, _ = target_url()
    assert make_url(get_settings().database_url) == url

    database = MigrationDatabase(raw_url)
    try:
        await database.reset()
        await database.migrate("upgrade", PARENT)
        yield database
    finally:
        try:
            await database.reset()
        finally:
            await database.engine.dispose()


@pytest.mark.parametrize("portions", [[], ["0.01", "100.000", "999999.99"]])
@pytest.mark.parametrize("mode", ["online", "offline"])
async def test_upgrade_downgrade_reupgrade_preserves_data_and_schema(
    migration_db, portions, mode
):
    db = migration_db
    if portions:
        await db.seed(portions)
    before = await db.state()
    await db.upgrade(mode)
    after = await db.state()
    assert after["revision"] == [REVISION]
    added = [row for row in after["constraints"] if row[1] == CHECK]
    assert len(added) == 1
    for key in before:
        if key not in ("revision", "constraints"):
            assert after[key] == before[key]
    assert [row for row in after["constraints"] if row[1] != CHECK] == before[
        "constraints"
    ]
    await db.migrate("downgrade", PARENT)
    assert await db.state() == before
    await db.upgrade(mode)
    assert await db.state() == after


@pytest.mark.parametrize("invalid", [["0"], ["-1"], ["NaN"], ["0", "-1", "NaN"]])
@pytest.mark.parametrize("mode", ["online", "offline"])
async def test_legacy_invalid_rows_block_upgrade_atomically(
    migration_db, invalid, mode
):
    db = migration_db
    await db.seed(["100", *invalid])
    before = await db.state()
    with pytest.raises(
        (DBAPIError, asyncpg.RaiseError),
        match=rf"{len(invalid)} invalid nutrition portion row",
    ) as error:
        await db.upgrade(mode)
    diagnostic = getattr(error.value, "orig", error.value)
    assert diagnostic.sqlstate == "P0001"
    assert "owner-authorized" in str(diagnostic)
    assert "docs/ingredient-portion-storage.md" in str(diagnostic)
    assert await db.state() == before


@pytest.mark.parametrize("mode", ["online", "offline"])
async def test_migrated_constraint_rejects_invalid_writes_after_reconnect(
    migration_db, mode
):
    db = migration_db
    ingredient = (await db.seed(["100"]))[0]
    await db.upgrade(mode)
    await db.engine.dispose()
    before = await db.state()
    for portion, state in [
        ("0", "23514"),
        ("-1", "23514"),
        ("NaN", "23514"),
        ("0.001", "23514"),
        ("Infinity", "22003"),
        ("1000000", "22003"),
    ]:
        with pytest.raises(DBAPIError) as error:
            await db.execute(
                "UPDATE nutrition_values SET portion_g = CAST(:portion AS numeric) "
                "WHERE ingredient_id = :id",
                {"id": ingredient, "portion": portion},
            )
        assert error.value.orig.sqlstate == state
    assert await db.state() == before


async def wait_for_blocked_query(db, prefix):
    async with asyncio.timeout(5):
        while True:
            blocked = (
                await db.execute(
                    "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
                    "AND pid <> pg_backend_pid() AND wait_event_type = 'Lock' "
                    "AND query LIKE :prefix",
                    {"prefix": prefix + "%"},
                )
            ).scalar_one()
            if blocked:
                return
            await asyncio.sleep(0.02)


async def test_writer_committed_before_upgrade_lock_is_seen_by_preflight(migration_db):
    db = migration_db
    ingredient = (await db.seed(["100"]))[0]
    async with db.engine.connect() as writer:
        await writer.execute(
            text("UPDATE nutrition_values SET portion_g = 0 WHERE ingredient_id = :id"),
            {"id": ingredient},
        )
        upgrade = asyncio.create_task(db.migrate("upgrade", REVISION))
        try:
            await wait_for_blocked_query(db, "LOCK TABLE nutrition_values")
            await writer.commit()
            with pytest.raises(DBAPIError, match="1 invalid nutrition portion row"):
                await upgrade
        finally:
            await writer.rollback()
            await asyncio.gather(upgrade, return_exceptions=True)
    assert (
        await db.execute("SELECT version_num FROM alembic_version")
    ).scalar_one() == PARENT
    assert (
        await db.execute("SELECT portion_g FROM nutrition_values")
    ).scalar_one() == 0
    assert not any(row[1] == CHECK for row in (await db.state())["constraints"])


async def test_writer_waiting_behind_upgrade_cannot_commit_invalid_portion(
    migration_db,
):
    db = migration_db
    ingredient = (await db.seed(["100"]))[0]
    lock_acquired, release = threading.Event(), threading.Event()

    def pause_after_lock(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("LOCK TABLE nutrition_values"):
            lock_acquired.set()
            if not release.wait(timeout=8):
                raise RuntimeError("Test synchronization timed out")

    event.listen(Engine, "after_cursor_execute", pause_after_lock)
    upgrade = asyncio.create_task(db.migrate("upgrade", REVISION))
    writer = None
    try:
        async with asyncio.timeout(5):
            while not lock_acquired.is_set():
                if upgrade.done():
                    await upgrade
                    pytest.fail("Migration never acquired the expected table lock")
                await asyncio.sleep(0.02)
        writer = asyncio.create_task(
            db.execute(
                "UPDATE nutrition_values SET portion_g = 0 WHERE ingredient_id = :id",
                {"id": ingredient},
            )
        )
        await wait_for_blocked_query(db, "UPDATE nutrition_values")
        release.set()
        await upgrade
        with pytest.raises(DBAPIError) as error:
            await writer
        assert error.value.orig.sqlstate == "23514"
    finally:
        release.set()
        await asyncio.gather(
            upgrade, *([writer] if writer else []), return_exceptions=True
        )
        event.remove(Engine, "after_cursor_execute", pause_after_lock)
    assert (
        await db.execute("SELECT version_num FROM alembic_version")
    ).scalar_one() == REVISION
    assert (
        await db.execute("SELECT portion_g FROM nutrition_values")
    ).scalar_one() == 100
