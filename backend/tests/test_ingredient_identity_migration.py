"""Genuine parent schema, executable offline SQL and independent metadata parity."""

import asyncio
import threading
from uuid import uuid4

import asyncpg
import pytest
from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError

from app.db.base import Base
from app.db.ddl import ingredient_identity_v1 as v1
from app.db.ingredient_identity import validate_identity_ddl
from app.models.ingredient import Ingredient
from tests import test_ingredient_portion_migration as portion_migration
from tests.db_target import verify_asyncpg, verify_connection
from tests.test_ingredient_portion_migration import (
    offline_upgrade_sql,
    wait_for_blocked_query,
)

migration_db = portion_migration.migration_db

PARENT = "a7203c91d602"
REVISION = "b205c8d15a01"


async def upgrade(db, mode):
    if mode == "online":
        await db.migrate("upgrade", REVISION)
    else:
        sql = offline_upgrade_sql(f"{PARENT}:{REVISION}")
        assert sql.startswith("BEGIN;") and sql.rstrip().endswith("COMMIT;")
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
            await verify_asyncpg(connection)
            try:
                await connection.execute(sql)
            except BaseException:
                await connection.execute("ROLLBACK")
                raise
        finally:
            await connection.close()


async def functions(db):
    return (
        await db.execute("""
        SELECT p.proname,p.prosrc,l.lanname,p.provolatile,p.proisstrict,p.prosecdef,
               p.proleakproof,p.proretset,p.proparallel,p.proconfig,p.prorettype::regtype::text
        FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
        JOIN pg_language l ON l.oid=p.prolang WHERE n.nspname='public'
        AND p.proname LIKE 'mealio_%' ORDER BY p.proname
    """)
    ).all()


async def identity_schema(db):
    return {
        "functions": await functions(db),
        "check": (
            await db.execute(
                "SELECT conname,pg_get_constraintdef(oid),convalidated FROM pg_constraint WHERE conrelid='ingredients'::regclass AND conname=:name",
                {"name": v1.CHECK},
            )
        ).all(),
        "index": (
            await db.execute(
                "SELECT indexname,indexdef FROM pg_indexes WHERE schemaname='public' AND indexname IN (:name,'ix_ingredients_name') ORDER BY indexname",
                {"name": v1.INDEX},
            )
        ).all(),
        "index_catalog": (
            await db.execute("""
            SELECT pg_get_expr(i.indexprs,i.indrelid),i.indisunique,i.indisvalid,
                   i.indisready,o.opcname,i.indcollation::text
            FROM pg_index i JOIN pg_opclass o ON o.oid=i.indclass[0]
            WHERE i.indexrelid='ux_ingredients_identity_v1'::regclass
        """)
        ).all(),
    }


@pytest.mark.parametrize("mode", ["online", "offline"])
@pytest.mark.parametrize("populated", [False, True])
async def test_genuine_parent_roundtrip_old_writer_and_offline(
    migration_db, mode, populated
):
    db = migration_db
    await db.migrate("upgrade", PARENT)
    if populated:
        await db.seed(["50", "125.50"])
    before = await db.state()
    assert await functions(db) == []
    await upgrade(db, mode)
    assert ScriptDirectory.from_config(db.config).get_heads() == [REVISION]
    after = await db.state()
    assert after["revision"] == [REVISION]
    for key in before:
        if key not in ("revision", "constraints", "indexes"):
            assert after[key] == before[key]
    assert [r for r in after["constraints"] if r[1] != v1.CHECK] == before[
        "constraints"
    ]
    assert [r for r in after["indexes"] if r[1] != v1.INDEX] == before["indexes"]
    schema = await identity_schema(db)
    await db.engine.dispose()
    await asyncio.to_thread(command.check, db.config)
    await asyncio.to_thread(command.current, db.config)
    await db.migrate("downgrade", PARENT)
    assert await db.state() == before and await functions(db) == []
    # Legacy writer supplies only old fields, no derived key. Re-upgrade preserves it.
    identifier = uuid4()
    await db.execute(
        "INSERT INTO ingredients(id,name) VALUES (:id,'Straße')", {"id": identifier}
    )
    await upgrade(db, mode)
    assert await identity_schema(db) == schema
    for sql in [
        "INSERT INTO ingredients(id,name) VALUES (:id,'STRASSE')",
        "UPDATE ingredients SET name='STRASSE' WHERE id=:id",
    ]:
        other = uuid4()
        await db.execute(
            "INSERT INTO ingredients(id,name) VALUES (:id,:name)",
            {"id": other, "name": str(other)},
        )
        with pytest.raises(DBAPIError) as error:
            await db.execute(
                sql, {"id": other if sql.startswith("UPDATE") else uuid4()}
            )
        assert error.value.orig.sqlstate == "23505"
        assert error.value.orig.__cause__.constraint_name == v1.INDEX
    assert (
        await db.execute(
            "SELECT name FROM ingredients WHERE id=:id", {"id": identifier}
        )
    ).scalar_one() == "Straße"


@pytest.mark.parametrize("mode", ["online", "offline"])
@pytest.mark.parametrize(
    "names,counts",
    [
        (["Straße", "STRASSE"], "invalid=0 collision_groups=1 excess=1"),
        (["\t\x1c", "Valid"], "invalid=1 collision_groups=0 excess=0"),
    ],
)
async def test_collision_or_invalid_aborts_data_schema_revision_atomically(
    migration_db, mode, names, counts
):
    db = migration_db
    await db.migrate("upgrade", PARENT)
    ids = await db.seed(["50", "100"])
    for identifier, name in zip(ids, names, strict=True):
        await db.execute(
            "UPDATE ingredients SET name=:name WHERE id=:id",
            {"id": identifier, "name": name},
        )
    before = await db.state()
    with pytest.raises((DBAPIError, asyncpg.RaiseError)) as error:
        await upgrade(db, mode)
    server = getattr(error.value, "orig", error.value)
    assert server.sqlstate == "P0001"
    message = str(server)
    assert counts in message and "owner-authorized" in message
    assert all(name not in message for name in names)
    assert await db.state() == before and await functions(db) == []


async def test_metadata_parity_partial_checkfirst_drop_and_recreate(migration_db):
    db = migration_db
    await db.migrate("upgrade", REVISION)
    migrated = await identity_schema(db)
    await db.reset()
    async with db.engine.begin() as c:
        await verify_connection(c)
        await c.run_sync(
            lambda conn: Base.metadata.create_all(conn, tables=[Ingredient.__table__])
        )
    assert await identity_schema(db) == migrated
    async with db.engine.begin() as c:
        await c.run_sync(Base.metadata.create_all)
        await c.run_sync(Base.metadata.create_all)
        await c.run_sync(validate_identity_ddl)
        await c.run_sync(Base.metadata.drop_all)
    assert await functions(db) == []
    async with db.engine.begin() as c:
        await c.run_sync(Base.metadata.create_all)
    assert await identity_schema(db) == migrated


@pytest.mark.parametrize("drift", ["function", "check", "index"])
async def test_alembic_check_and_metadata_detect_real_drift(migration_db, drift):
    db = migration_db
    await db.migrate("upgrade", REVISION)
    await asyncio.to_thread(command.check, db.config)
    if drift == "function":
        await db.execute("ALTER FUNCTION public.mealio_nfc15_v1(text) STABLE")
    elif drift == "check":
        await db.execute(f"ALTER TABLE ingredients DROP CONSTRAINT {v1.CHECK}")
        await db.execute(
            f"ALTER TABLE ingredients ADD CONSTRAINT {v1.CHECK} CHECK (char_length(name)>0)"
        )
    else:
        await db.execute(f"DROP INDEX {v1.INDEX}")
        await db.execute(f"CREATE INDEX {v1.INDEX} ON ingredients(name)")
    with pytest.raises((RuntimeError, DBAPIError), match="drift"):
        await asyncio.to_thread(command.check, db.config)
    with pytest.raises((RuntimeError, DBAPIError), match="drift"):
        await db.migrate("upgrade", "head")
    with pytest.raises((RuntimeError, DBAPIError), match="drift"):
        async with db.engine.begin() as c:
            await c.run_sync(Base.metadata.create_all)


async def test_conflicting_preexisting_helper_not_replaced(migration_db):
    db = migration_db
    await db.migrate("upgrade", PARENT)
    await db.execute(
        "CREATE FUNCTION public.mealio_nfc15_v1(text) RETURNS text LANGUAGE sql IMMUTABLE STRICT AS 'SELECT $1'"
    )
    before = await functions(db)
    with pytest.raises(DBAPIError, match="function drift"):
        await db.migrate("upgrade", REVISION)
    assert await functions(db) == before
    assert (
        await db.execute("SELECT version_num FROM alembic_version")
    ).scalar_one() == PARENT


async def test_lock_timeout_has_no_partial_ddl(migration_db):
    db = migration_db
    await db.migrate("upgrade", PARENT)
    await db.seed(["100"])
    before = await db.state()
    async with db.engine.connect() as holder:
        await holder.execute(text("LOCK TABLE ingredients IN ROW EXCLUSIVE MODE"))
        with pytest.raises(DBAPIError) as error:
            await db.migrate("upgrade", REVISION)
        assert error.value.orig.sqlstate == "55P03"
        await holder.rollback()
    assert await db.state() == before and await functions(db) == []
    await db.migrate("upgrade", REVISION)


async def test_writer_before_lock_visible_to_preflight(migration_db):
    db = migration_db
    await db.migrate("upgrade", PARENT)
    ids = await db.seed(["100", "100"])
    await db.execute(
        "UPDATE ingredients SET name='Straße' WHERE id=:id", {"id": ids[0]}
    )
    async with db.engine.connect() as writer:
        await writer.execute(
            text("UPDATE ingredients SET name='STRASSE' WHERE id=:id"), {"id": ids[1]}
        )
        task = asyncio.create_task(db.migrate("upgrade", REVISION))
        try:
            await wait_for_blocked_query(db, "LOCK TABLE public.ingredients")
            await writer.commit()
            with pytest.raises(DBAPIError, match="collision_groups=1"):
                await task
        finally:
            await writer.rollback()
            await asyncio.gather(task, return_exceptions=True)
    assert await functions(db) == []
    assert (
        await db.execute("SELECT version_num FROM alembic_version")
    ).scalar_one() == PARENT


async def test_writer_after_lock_waits_for_enforcement(migration_db):
    db = migration_db
    await db.migrate("upgrade", PARENT)
    ids = await db.seed(["100", "100"])
    await db.execute(
        "UPDATE ingredients SET name='Straße' WHERE id=:id", {"id": ids[0]}
    )
    acquired, release = threading.Event(), threading.Event()

    def pause(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("LOCK TABLE public.ingredients"):
            acquired.set()
            if not release.wait(8):
                raise RuntimeError("Synchronization timeout")

    event.listen(Engine, "after_cursor_execute", pause)
    task = asyncio.create_task(db.migrate("upgrade", REVISION))
    writer = None
    try:
        async with asyncio.timeout(5):
            while not acquired.is_set():
                if task.done():
                    await task
                    pytest.fail("Migration did not acquire lock")
                await asyncio.sleep(0.02)
        writer = asyncio.create_task(
            db.execute(
                "UPDATE ingredients SET name='STRASSE' WHERE id=:id", {"id": ids[1]}
            )
        )
        await wait_for_blocked_query(db, "UPDATE ingredients")
        release.set()
        await task
        with pytest.raises(DBAPIError) as error:
            await writer
        assert error.value.orig.sqlstate == "23505"
        assert error.value.orig.__cause__.constraint_name == v1.INDEX
    finally:
        release.set()
        await asyncio.gather(
            task, *([writer] if writer else []), return_exceptions=True
        )
        event.remove(Engine, "after_cursor_execute", pause)


async def test_nonowner_runtime_grants_and_deploy_role(migration_db):
    db = migration_db
    await db.migrate("upgrade", PARENT)
    # Roles are confined to this disposable cluster and explicitly cleaned up.
    deploy, runtime = "w8_deploy_" + uuid4().hex, "w8_runtime_" + uuid4().hex
    await db.execute(f'CREATE ROLE "{deploy}" NOLOGIN')
    await db.execute(f'CREATE ROLE "{runtime}" NOLOGIN')
    try:
        await db.execute(f'GRANT USAGE,CREATE ON SCHEMA public TO "{deploy}"')
        await db.execute(f'ALTER TABLE ingredients OWNER TO "{deploy}"')
        async with db.engine.begin() as c:
            await c.execute(text(f'SET LOCAL ROLE "{deploy}"'))
            for statement in v1.upgrade_statements():
                await c.execute(text(statement))
        await db.execute(f'GRANT USAGE ON SCHEMA public TO "{runtime}"')
        await db.execute(f'GRANT SELECT,INSERT,UPDATE ON ingredients TO "{runtime}"')
        for name, _, _ in v1.FUNCTIONS:
            await db.execute(
                f"REVOKE EXECUTE ON FUNCTION public.{name}(text) FROM PUBLIC"
            )
            await db.execute(
                f'GRANT EXECUTE ON FUNCTION public.{name}(text) TO "{runtime}"'
            )
        async with db.engine.begin() as c:
            await c.execute(text(f'SET LOCAL ROLE "{runtime}"'))
            assert not await c.scalar(
                text("SELECT has_schema_privilege(current_user,'public','CREATE')")
            )
            await c.execute(
                text("INSERT INTO ingredients(id,name) VALUES (:id,'Straße')"),
                {"id": uuid4()},
            )
            assert (
                await c.scalar(
                    text(
                        "SELECT count(*) FROM ingredients WHERE public.mealio_ingredient_bits_v1(name)=public.mealio_ingredient_bits_v1('STRASSE')"
                    )
                )
                == 1
            )
        with pytest.raises(DBAPIError) as error:
            async with db.engine.begin() as c:
                await c.execute(text(f'SET LOCAL ROLE "{runtime}"'))
                await c.execute(
                    text("INSERT INTO ingredients(id,name) VALUES (:id,'STRASSE')"),
                    {"id": uuid4()},
                )
        assert error.value.orig.sqlstate == "23505"
    finally:
        await db.reset()
        for role in (runtime, deploy):
            await db.execute(f'DROP OWNED BY "{role}"')
            await db.execute(f'DROP ROLE "{role}"')


@pytest.mark.parametrize("object_kind", ["column", "index"])
async def test_alembic_still_reports_unrelated_schema_drift(migration_db, object_kind):
    from alembic.util.exc import AutogenerateDiffsDetected

    db = migration_db
    await db.migrate("upgrade", REVISION)
    name = "unexpected_w8_" + object_kind
    if object_kind == "column":
        await db.execute(f"ALTER TABLE ingredients ADD COLUMN {name} integer")
    else:
        await db.execute(f"CREATE INDEX {name} ON ingredients(category)")
    with pytest.raises(AutogenerateDiffsDetected, match=name):
        await asyncio.to_thread(command.check, db.config)


async def test_unrelated_partial_metadata_does_not_install_or_validate_identity(
    migration_db,
):
    from app.models.user import User

    db = migration_db
    await db.migrate("upgrade", PARENT)
    before = await db.state()
    async with db.engine.begin() as c:
        await c.run_sync(
            lambda conn: Base.metadata.create_all(conn, tables=[User.__table__])
        )
    assert await db.state() == before
    assert await functions(db) == []


@pytest.mark.parametrize("object_kind", ["index", "check"])
@pytest.mark.parametrize(
    "entry_point", ["validator", "metadata", "alembic_check", "upgrade_head"]
)
async def test_expression_identity_collision_is_rejected(
    migration_db, object_kind, entry_point
):
    """Different call trees must not collapse to the same drift-check string."""
    import json

    db = migration_db
    await db.migrate("upgrade", PARENT)
    await db.migrate("upgrade", REVISION)
    expected_names = {name for name, _, _ in v1.FUNCTIONS}
    original_helpers = await functions(db)
    if object_kind == "index":
        await db.execute(
            "CREATE FUNCTION public.mealio_ingredient_bits_v1name() RETURNS bit varying LANGUAGE sql IMMUTABLE AS 'SELECT NULL::bit varying'"
        )
        await db.execute(f"DROP INDEX public.{v1.INDEX}")
        await db.execute(
            f"CREATE UNIQUE INDEX {v1.INDEX} ON public.ingredients (public.mealio_ingredient_bits_v1name())"
        )
        catalog = (
            await db.execute("""
            SELECT pg_get_expr(i.indexprs,i.indrelid),pg_get_indexdef(i.indexrelid),
                   i.indisunique,i.indisvalid,i.indisready,o.opcname,i.indcollation::text
            FROM pg_index i JOIN pg_opclass o ON o.oid=i.indclass[0]
            WHERE i.indexrelid='public.ux_ingredients_identity_v1'::regclass
        """)
        ).one()
        # Concrete loss of protection: the unchanged CHECK/raw-name index allow
        # two different labels; this wrong index returns NULL for both.
        for name in ("Straße", "STRASSE"):
            await db.execute(
                "INSERT INTO public.ingredients(id,name) VALUES (:id,:name)",
                {"id": uuid4(), "name": name},
            )
        assert (
            await db.execute(
                "SELECT count(*),count(DISTINCT public.mealio_ingredient_bits_v1(name)) FROM public.ingredients"
            )
        ).one() == (2, 1)
    else:
        await db.execute(
            "CREATE FUNCTION public.char_lengthmealio_ingredient_key_v1(text) RETURNS integer LANGUAGE sql IMMUTABLE STRICT AS 'SELECT 1'"
        )
        await db.execute(f"ALTER TABLE public.ingredients DROP CONSTRAINT {v1.CHECK}")
        await db.execute(
            f"ALTER TABLE public.ingredients ADD CONSTRAINT {v1.CHECK} CHECK (public.char_lengthmealio_ingredient_key_v1(name) BETWEEN 1 AND 1020)"
        )
        catalog = (
            await db.execute(
                "SELECT pg_get_expr(conbin,conrelid),pg_get_constraintdef(oid),convalidated FROM pg_constraint WHERE conrelid='public.ingredients'::regclass AND conname=:name",
                {"name": v1.CHECK},
            )
        ).one()
        await db.execute(
            "INSERT INTO public.ingredients(id,name) VALUES (:id,:name)",
            {"id": uuid4(), "name": " \t"},
        )
        assert (
            await db.execute(
                "SELECT count(*) FROM public.ingredients WHERE public.mealio_ingredient_key_v1(name)='' "
            )
        ).scalar_one() == 1
    assert [
        row for row in await functions(db) if row[0] in expected_names
    ] == original_helpers
    print(
        "DRIFT_EVIDENCE "
        + json.dumps(
            {
                "kind": object_kind,
                "entry": entry_point,
                "catalog": list(catalog),
                "unchanged_helpers": True,
                "consequence_verified": True,
            },
            ensure_ascii=True,
        )
    )
    with pytest.raises((RuntimeError, DBAPIError), match="drift"):
        if entry_point == "validator":
            async with db.engine.begin() as c:
                await c.run_sync(validate_identity_ddl)
        elif entry_point == "metadata":
            async with db.engine.begin() as c:
                await c.run_sync(Base.metadata.create_all)
        elif entry_point == "alembic_check":
            await asyncio.to_thread(command.check, db.config)
        else:
            await db.migrate("upgrade", "head")


@pytest.mark.parametrize("style", ["unqualified", "qualified", "quoted_cast"])
async def test_reviewed_expression_presentations_are_accepted(migration_db, style):
    import json

    db = migration_db
    await db.migrate("upgrade", REVISION)
    expressions = {
        "unqualified": (
            "mealio_ingredient_bits_v1(name)",
            "char_length(mealio_ingredient_key_v1(name))",
        ),
        "qualified": (
            "public.mealio_ingredient_bits_v1((name)::pg_catalog.text)",
            "pg_catalog.char_length(public.mealio_ingredient_key_v1((name)::pg_catalog.text))",
        ),
        "quoted_cast": (
            '"public"."mealio_ingredient_bits_v1"(CAST("name" AS pg_catalog.text))',
            '"pg_catalog"."char_length"("public"."mealio_ingredient_key_v1"(CAST("name" AS pg_catalog.text)))',
        ),
    }
    index, length = expressions[style]
    await db.execute(f"DROP INDEX public.{v1.INDEX}")
    await db.execute(f"CREATE UNIQUE INDEX {v1.INDEX} ON public.ingredients ({index})")
    await db.execute(f"ALTER TABLE public.ingredients DROP CONSTRAINT {v1.CHECK}")
    await db.execute(
        f"ALTER TABLE public.ingredients ADD CONSTRAINT {v1.CHECK} CHECK ({length} BETWEEN 1 AND 1020)"
    )
    for qualified in (False, True):
        async with db.engine.begin() as c:
            if qualified:
                await c.execute(text("SET LOCAL search_path=pg_catalog"))
            actual = (
                await c.execute(
                    text(
                        "SELECT pg_get_expr(i.indexprs,i.indrelid),pg_get_indexdef(i.indexrelid),pg_get_expr(c.conbin,c.conrelid) FROM pg_catalog.pg_index i CROSS JOIN pg_catalog.pg_constraint c WHERE i.indexrelid='public.ux_ingredients_identity_v1'::regclass AND c.conrelid='public.ingredients'::regclass AND c.conname='ck_ingredients_identity_v1_valid'"
                    )
                )
            ).one()
            print(
                "SAFE_EVIDENCE "
                + json.dumps(
                    {
                        "style": style,
                        "qualified_deparse": qualified,
                        "catalog": list(actual),
                    }
                )
            )
            await c.run_sync(validate_identity_ddl)
    async with db.engine.begin() as c:
        await c.run_sync(Base.metadata.create_all)
    await asyncio.to_thread(command.check, db.config)
    await db.migrate("upgrade", "head")
    await db.execute(
        "INSERT INTO public.ingredients(id,name) VALUES (:id,'Straße')", {"id": uuid4()}
    )
    for name, state in [("STRASSE", "23505"), (" \t", "23514")]:
        with pytest.raises(DBAPIError) as error:
            await db.execute(
                "INSERT INTO public.ingredients(id,name) VALUES (:id,:name)",
                {"id": uuid4(), "name": name},
            )
        assert error.value.orig.sqlstate == state


@pytest.mark.parametrize("object_kind", ["index", "check"])
async def test_unqualified_deparse_requires_real_function_identity(
    migration_db, object_kind
):
    """Same spelling from another schema must fail even if deparsed unqualified."""
    import json

    db = migration_db
    await db.migrate("upgrade", REVISION)
    schema = "w8_drift_" + uuid4().hex
    await db.execute(f'CREATE SCHEMA "{schema}"')
    try:
        if object_kind == "index":
            await db.execute(
                f"CREATE FUNCTION \"{schema}\".mealio_ingredient_bits_v1(text) RETURNS varbit LANGUAGE sql IMMUTABLE AS 'SELECT NULL::varbit'"
            )
            await db.execute(f"DROP INDEX public.{v1.INDEX}")
            await db.execute(
                f'CREATE UNIQUE INDEX {v1.INDEX} ON public.ingredients ("{schema}".mealio_ingredient_bits_v1(name))'
            )
        else:
            await db.execute(
                f"CREATE FUNCTION \"{schema}\".char_length(text) RETURNS integer LANGUAGE sql IMMUTABLE STRICT AS 'SELECT 1'"
            )
            await db.execute(
                f"ALTER TABLE public.ingredients DROP CONSTRAINT {v1.CHECK}"
            )
            await db.execute(
                f'ALTER TABLE public.ingredients ADD CONSTRAINT {v1.CHECK} CHECK ("{schema}".char_length(public.mealio_ingredient_key_v1(name)) BETWEEN 1 AND 1020)'
            )
        with pytest.raises(RuntimeError, match="drift"):
            async with db.engine.begin() as c:
                await c.execute(
                    text(f'SET LOCAL search_path="{schema}",public,pg_catalog')
                )
                actual = (
                    await c.execute(
                        text(
                            "SELECT pg_get_expr(i.indexprs,i.indrelid),pg_get_expr(c.conbin,c.conrelid) FROM pg_catalog.pg_index i CROSS JOIN pg_catalog.pg_constraint c WHERE i.indexrelid='public.ux_ingredients_identity_v1'::regclass AND c.conrelid='public.ingredients'::regclass AND c.conname='ck_ingredients_identity_v1_valid'"
                        )
                    )
                ).one()
                print(
                    "SCHEMA_EVIDENCE "
                    + json.dumps({"kind": object_kind, "catalog": list(actual)})
                )
                await c.run_sync(validate_identity_ddl)
    finally:
        # Only the fresh schema created by this test in the guarded disposable DB.
        await db.execute(f'DROP SCHEMA "{schema}" CASCADE')


@pytest.mark.parametrize(
    "object_kind,expression",
    [
        ("index", "public.mealio_ingredient_bits_v1(category)"),
        ("index", "(public.mealio_ingredient_bits_v1(name) || B'0')"),
        ("index", "public.mealio_ingredient_bits_v1(name), id"),
        ("index", "public.mealio_ingredient_bits_v1(name, name)"),
        (
            "check",
            "char_length(public.mealio_ingredient_key_v1(name)) BETWEEN 0 AND 1020",
        ),
        (
            "check",
            "char_length(public.mealio_ingredient_key_v1(name)) BETWEEN 1 AND 1020 OR name=''",
        ),
    ],
)
async def test_other_expression_structures_fail_closed(
    migration_db, object_kind, expression
):
    db = migration_db
    await db.migrate("upgrade", REVISION)
    if object_kind == "index":
        if expression.endswith("(name, name)"):
            await db.execute(
                "CREATE FUNCTION public.mealio_ingredient_bits_v1(text,text) RETURNS varbit LANGUAGE sql IMMUTABLE AS 'SELECT NULL::varbit'"
            )
        await db.execute(f"DROP INDEX public.{v1.INDEX}")
        await db.execute(
            f"CREATE UNIQUE INDEX {v1.INDEX} ON public.ingredients ({expression})"
        )
    else:
        await db.execute(f"ALTER TABLE public.ingredients DROP CONSTRAINT {v1.CHECK}")
        await db.execute(
            f"ALTER TABLE public.ingredients ADD CONSTRAINT {v1.CHECK} CHECK ({expression})"
        )
    with pytest.raises(RuntimeError, match="drift"):
        async with db.engine.begin() as c:
            await c.run_sync(validate_identity_ddl)
    with pytest.raises(RuntimeError, match="drift"):
        await asyncio.to_thread(command.check, db.config)


async def test_unqualified_operator_shadow_is_not_a_builtin_comparison(migration_db):
    import json

    db = migration_db
    await db.migrate("upgrade", REVISION)
    schema = "w8_operator_" + uuid4().hex
    await db.execute(f'CREATE SCHEMA "{schema}"')
    try:
        await db.execute(
            f"CREATE FUNCTION \"{schema}\".always_true(integer,integer) RETURNS boolean LANGUAGE sql IMMUTABLE AS 'SELECT true'"
        )
        await db.execute(
            f'CREATE OPERATOR "{schema}".>= (LEFTARG=integer,RIGHTARG=integer,FUNCTION="{schema}".always_true)'
        )
        await db.execute(f"ALTER TABLE public.ingredients DROP CONSTRAINT {v1.CHECK}")
        length = "pg_catalog.char_length(public.mealio_ingredient_key_v1(name))"
        await db.execute(
            f'ALTER TABLE public.ingredients ADD CONSTRAINT {v1.CHECK} CHECK ({length} OPERATOR("{schema}".>=) 1 AND {length} <= 1020)'
        )
        with pytest.raises(RuntimeError, match="drift"):
            async with db.engine.begin() as c:
                await c.execute(
                    text(f'SET LOCAL search_path="{schema}",public,pg_catalog')
                )
                actual = await c.scalar(
                    text(
                        "SELECT pg_get_expr(conbin,conrelid) FROM pg_catalog.pg_constraint WHERE conrelid='public.ingredients'::regclass AND conname='ck_ingredients_identity_v1_valid'"
                    )
                )
                print("OPERATOR_EVIDENCE " + json.dumps({"expression": actual}))
                await c.run_sync(validate_identity_ddl)
    finally:
        await db.execute(f'DROP SCHEMA "{schema}" CASCADE')


@pytest.mark.parametrize(
    "replacement",
    ["other_function", "wrong_argument", "unqualified_model", "unicode_identifier"],
)
async def test_model_index_drift_is_not_reconciled(
    migration_db, monkeypatch, replacement
):
    from sqlalchemy import func

    db = migration_db
    await db.migrate("upgrade", REVISION)
    index = next(i for i in Ingredient.__table__.indexes if i.name == v1.INDEX)
    expressions = {
        "other_function": func.public.mealio_ingredient_bits_v1name(),
        "wrong_argument": func.public.mealio_ingredient_bits_v1(Ingredient.category),
        "unqualified_model": func.mealio_ingredient_bits_v1(Ingredient.name),
        "unicode_identifier": text("public\u00a0.mealio_ingredient_bits_v1(name)"),
    }
    monkeypatch.setattr(index, "expressions", [expressions[replacement]])
    with pytest.raises(RuntimeError, match="metadata index drift"):
        await asyncio.to_thread(command.check, db.config)
