"""Immutable W8 v1 DDL: shared by metadata and its historical Alembic revision.

Do not edit this policy/snapshot after release. Add a v2 and migrate explicitly.
No application settings, mutable business logic, tables or network inputs.
"""

import hashlib
import re
from pathlib import Path

SNAPSHOT_SHA256 = "b98afed2fd91e57beb8df750fd3f5a6875b60499698f08d9ddc68b8cd22db0d4"
SNAPSHOT = Path(__file__).with_suffix(".sql").read_text(encoding="utf-8")
if hashlib.sha256(SNAPSHOT.encode()).hexdigest() != SNAPSHOT_SHA256:
    raise RuntimeError("Ingredient identity v1 snapshot digest mismatch")

DEFINITIONS = tuple(
    part.strip() for part in SNAPSHOT.split("-- mealio:statement\n")[1:]
)
FUNCTIONS = (
    ("mealio_nfc15_v1", "text", "nfc"),
    ("mealio_ingredient_key_v1", "text", "key"),
    ("mealio_ingredient_bits_v1", "varbit", "bits"),
)
INDEX = "ux_ingredients_identity_v1"
CHECK = "ck_ingredients_identity_v1_valid"
CHECK_EXPRESSION = (
    "pg_catalog.char_length(public.mealio_ingredient_key_v1(name)) BETWEEN 1 AND 1020"
)
WHITESPACE = "".join(
    chr(c)
    for c in (
        *range(0x09, 0x0E),
        *range(0x1C, 0x20),
        0x20,
        0x85,
        0xA0,
        0x1680,
        *range(0x2000, 0x200B),
        0x2028,
        0x2029,
        0x202F,
        0x205F,
        0x3000,
    )
)

COMPATIBILITY_SQL = """DO $compatibility$
BEGIN
 IF pg_catalog.current_setting('server_encoding') <> 'UTF8'
 OR pg_catalog.current_setting('server_version_num')::integer / 10000 NOT IN (17,18)
 OR pg_catalog.current_setting('block_size')::integer <> 8192
 OR pg_catalog.strpos(pg_catalog.version(), '64-bit') = 0
 THEN RAISE EXCEPTION 'Ingredient identity v1 requires verified PostgreSQL 17/18, UTF8, 8KiB blocks and 64-bit build; see docs/ingredient-identity.md';
 END IF;
END $compatibility$"""

PREFLIGHT_SQL = """DO $preflight$
DECLARE invalid_count bigint; collision_groups bigint; excess_rows bigint;
BEGIN
 SELECT pg_catalog.count(*) INTO invalid_count FROM public.ingredients
 WHERE name IS NULL OR pg_catalog.char_length(public.mealio_ingredient_key_v1(name)) NOT BETWEEN 1 AND 1020;
 SELECT pg_catalog.count(*),COALESCE(pg_catalog.sum(n-1),0) INTO collision_groups,excess_rows
 FROM (SELECT pg_catalog.count(*) n FROM public.ingredients
 GROUP BY public.mealio_ingredient_bits_v1(name) HAVING pg_catalog.count(*)>1) q;
 IF invalid_count>0 OR collision_groups>0 THEN
  RAISE EXCEPTION USING ERRCODE='P0001', MESSAGE=pg_catalog.format(
   'Ingredient identity preflight: invalid=%s collision_groups=%s excess=%s; owner-authorized adjudication required; see docs/ingredient-identity.md',
   invalid_count,collision_groups,excess_rows);
 END IF;
END $preflight$"""


def function_statements(*, create: bool) -> tuple[str, ...]:
    """One statement per function, safe for asyncpg and executable offline SQL.

    Never silently replace an existing function, even during checkfirst calls.
    Exact source and essential attributes are verified before trusting v1.
    """
    statements = []
    for definition, (name, result_type, tag) in zip(
        DEFINITIONS, FUNCTIONS, strict=True
    ):
        body = definition.split(f"${tag}$", 2)[1]
        missing = (
            f"EXECUTE $definition${definition}$definition$;"
            if create
            else f"RAISE EXCEPTION 'Ingredient identity v1 missing function: {name}';"
        )
        statements.append(f"""DO $install$
DECLARE function_id oid := pg_catalog.to_regprocedure('public.{name}(text)');
BEGIN
 IF function_id IS NULL THEN
  {missing}
 ELSIF NOT EXISTS (
  SELECT 1 FROM pg_catalog.pg_proc p
  JOIN pg_catalog.pg_language l ON l.oid=p.prolang
  WHERE p.oid=function_id AND p.prosrc=$expected${body}$expected$
  AND l.lanname='plpgsql' AND p.provolatile='i' AND p.proisstrict
  AND NOT p.prosecdef AND NOT p.proleakproof AND NOT p.proretset
  AND p.prokind='f' AND p.proparallel='u' AND p.pronargs=1
  AND p.proargnames=ARRAY['s']::text[] AND p.proargmodes IS NULL
  AND p.pronargdefaults=0 AND p.provariadic=0 AND p.prosupport=0
  AND p.prorettype='pg_catalog.{result_type}'::pg_catalog.regtype
  AND p.proconfig=ARRAY['search_path=pg_catalog']::text[]
 ) THEN
  RAISE EXCEPTION 'Ingredient identity v1 function drift: {name}; restore the reviewed snapshot or introduce a new version';
 END IF;
END $install$""")
    return tuple(statements)


def upgrade_statements() -> tuple[str, ...]:
    return (
        "SET LOCAL lock_timeout='5s'",
        "SET LOCAL statement_timeout='60s'",
        COMPATIBILITY_SQL,
        "LOCK TABLE public.ingredients IN ACCESS EXCLUSIVE MODE",
        *function_statements(create=True),
        PREFLIGHT_SQL,
        f"ALTER TABLE public.ingredients ADD CONSTRAINT {CHECK} CHECK ({CHECK_EXPRESSION})",
        f"CREATE UNIQUE INDEX {INDEX} ON public.ingredients (public.mealio_ingredient_bits_v1(name))",
    )


def drop_function_statements() -> tuple[str, ...]:
    return tuple(
        f"DROP FUNCTION public.{name}(text) RESTRICT"
        for name, _, _ in reversed(FUNCTIONS)
    )


def downgrade_statements() -> tuple[str, ...]:
    return (
        "SET LOCAL lock_timeout='5s'",
        "SET LOCAL statement_timeout='60s'",
        "LOCK TABLE public.ingredients IN ACCESS EXCLUSIVE MODE",
        *function_statements(create=False),
        f"DROP INDEX public.{INDEX}",
        f"ALTER TABLE public.ingredients DROP CONSTRAINT {CHECK}",
        *drop_function_statements(),
    )


def canonical_expression(value: str) -> str:
    """Ignore only PostgreSQL's qualification/cast/parentheses presentation."""
    return re.sub(r"\s+|[()\"]|::text|public\.|pg_catalog\.", "", value)
