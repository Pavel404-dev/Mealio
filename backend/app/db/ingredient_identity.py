"""PostgreSQL lifecycle and narrow drift checks for the frozen v1 snapshot."""

import re

from sqlalchemy import event, text

from app.db.ddl import ingredient_identity_v1 as v1

_alembic_validator_registered = False

# PostgreSQL SQL whitespace; Unicode whitespace may be part of an identifier.
_WS = r"[ \t\r\n\f\v]*"
_SEP = r"[ \t\r\n\f\v]+"


def _identifier(name):
    # Only these known identifiers may be quoted. Never erase arbitrary quotes,
    # separators or function-call boundaries to compare SQL strings.
    return rf'(?:{name}|"{name}")'


def _function(schema, name, *, qualified=False):
    prefix = rf"{_identifier(schema)}{_WS}\.{_WS}"
    return (prefix if qualified else rf"(?:{prefix})?") + _identifier(name)


_NAME = _identifier("name")
_TEXT = rf'(?:{_identifier("pg_catalog")}{_WS}\.{_WS})?{_identifier("text")}'
_ARGUMENT = rf"(?:{_NAME}|\({_WS}{_NAME}{_WS}\))(?:{_WS}::{_WS}{_TEXT})?"


def _index_expression(value, *, metadata=False):
    function = _function("public", "mealio_ingredient_bits_v1", qualified=metadata)
    return (
        value is not None
        and re.fullmatch(rf"{_WS}{function}{_WS}\({_WS}{_ARGUMENT}{_WS}\){_WS}", value)
        is not None
    )


def _check_expression(value):
    length = _function("pg_catalog", "char_length")
    key = _function("public", "mealio_ingredient_key_v1")
    call = rf"{length}{_WS}\({_WS}{key}{_WS}\({_WS}{_ARGUMENT}{_WS}\){_WS}\)"
    # pg_get_expr's reviewed PG17/18 BETWEEN expansion, not a general SQL
    # equivalence parser. Unknown shapes fail closed, including extra terms.
    return (
        value is not None
        and re.fullmatch(
            rf"{_WS}\({_WS}\({_WS}{call}{_WS}>={_WS}1{_WS}\){_SEP}AND{_SEP}"
            rf"\({_WS}{call}{_WS}<={_WS}1020{_WS}\){_WS}\){_WS}",
            value,
        )
        is not None
    )


def _references_function(connection, object_class, object_id, signature):
    # Unqualified deparser output is safe only when catalog dependencies prove
    # the actual public helper OID. Pinned pg_catalog builtins have no dependency
    # rows; a user-defined char_length shadow adds an OID and is rejected.
    # The allowed grammar also uses only pinned builtin operators/types/casts.
    # Reject custom dependencies even when search_path hides their qualification.
    return (
        connection.scalar(
            text("""
        SELECT array_agg(DISTINCT d.refobjid)
                 FILTER (WHERE d.refclassid='pg_catalog.pg_proc'::regclass) =
               ARRAY[pg_catalog.to_regprocedure(:signature)::oid]
          AND count(*) FILTER (WHERE d.refclassid IN (
            'pg_catalog.pg_operator'::regclass, 'pg_catalog.pg_type'::regclass,
            'pg_catalog.pg_cast'::regclass, 'pg_catalog.pg_collation'::regclass
          )) = 0
        FROM pg_catalog.pg_depend d
        WHERE d.classid=CAST(:object_class AS regclass) AND d.objid=:object_id
        """),
            {
                "object_class": object_class,
                "object_id": object_id,
                "signature": signature,
            },
        )
        is True
    )


def validate_identity_ddl(connection, *, table=True):
    for statement in v1.function_statements(create=False):
        connection.execute(text(statement))
    if not table:
        return
    check = connection.execute(
        text("""
        SELECT pg_get_expr(conbin,conrelid),convalidated,oid FROM pg_constraint
        WHERE conrelid='public.ingredients'::regclass AND conname=:name AND contype='c'
    """),
        {"name": v1.CHECK},
    ).one_or_none()
    if (
        not check
        or not check[1]
        or not _check_expression(check[0])
        or not _references_function(
            connection,
            "pg_catalog.pg_constraint",
            check[2],
            "public.mealio_ingredient_key_v1(pg_catalog.text)",
        )
    ):
        raise RuntimeError("Ingredient identity v1 CHECK drift")
    index = connection.execute(
        text("""
        SELECT pg_get_expr(i.indexprs,i.indrelid),i.indisunique,i.indisvalid,
        i.indisready,i.indnkeyatts,i.indnatts,i.indpred IS NULL,o.opcname,n.nspname,
        i.indcollation[0],i.indexrelid FROM pg_index i JOIN pg_opclass o ON o.oid=i.indclass[0]
        JOIN pg_namespace n ON n.oid=o.opcnamespace
        WHERE i.indexrelid=to_regclass(:name) AND i.indrelid='public.ingredients'::regclass
    """),
        {"name": "public." + v1.INDEX},
    ).one_or_none()
    if (
        not index
        or not _index_expression(index[0])
        or tuple(index[1:-1])
        != (True, True, True, 1, 1, True, "varbit_ops", "pg_catalog", 0)
        or not _references_function(
            connection,
            "pg_catalog.pg_class",
            index[-1],
            "public.mealio_ingredient_bits_v1(pg_catalog.text)",
        )
    ):
        raise RuntimeError("Ingredient identity v1 index drift")


def register_identity_ddl(table):
    @event.listens_for(table.metadata, "before_create")
    def before_create(metadata, connection, tables, **kwargs):
        # SQLAlchemy's public event `tables` has already removed existing
        # tables for checkfirst. Preserve the caller's original partial scope.
        # This narrow SchemaGenerator hook is covered against the pinned version.
        requested = kwargs["_ddl_runner"].tables
        if requested is not None and table not in requested:
            return
        if table in tables:
            connection.execute(text(v1.COMPATIBILITY_SQL))
            for statement in v1.function_statements(create=True):
                connection.execute(text(statement))
        elif connection.dialect.has_table(connection, table.name, schema="public"):
            # create_all(checkfirst=True) must not silently accept drift.
            validate_identity_ddl(connection)

    @event.listens_for(table, "before_create")
    def before_table_create(target, connection, **kwargs):
        # Also support Ingredient.__table__.create(), without metadata events.
        connection.execute(text(v1.COMPATIBILITY_SQL))
        for statement in v1.function_statements(create=True):
            connection.execute(text(statement))

    @event.listens_for(table, "after_drop")
    def after_table_drop(target, connection, **kwargs):
        existing = connection.scalar(
            text(
                "SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
                "WHERE n.nspname='public' AND p.proname=ANY(:names) AND p.proargtypes='25'::oidvector"
            ),
            {"names": [name for name, _, _ in v1.FUNCTIONS]},
        )
        if existing:
            validate_identity_ddl(connection, table=False)
            for statement in v1.drop_function_statements():
                connection.execute(text(statement))


def register_alembic_validator():
    global _alembic_validator_registered
    if _alembic_validator_registered:
        return
    from alembic.autogenerate import comparators
    from alembic.operations import ops

    @comparators.dispatch_for("schema")
    def compare_identity(autogen_context, upgrade_ops, schemas):
        # Complements, never suppresses, Alembic's normal table/index comparison.
        if "ingredients" in autogen_context.metadata.tables:
            validate_identity_ddl(autogen_context.connection)
            model = autogen_context.metadata.tables["ingredients"]
            index = next((i for i in model.indexes if i.name == v1.INDEX), None)
            if (
                index is None
                or not index.unique
                or len(index.expressions) != 1
                or index.dialect_kwargs
                or not _index_expression(
                    str(
                        index.expressions[0].compile(
                            dialect=autogen_context.dialect,
                            compile_kwargs={"include_table": False},
                        )
                    ),
                    metadata=True,
                )
            ):
                raise RuntimeError("Ingredient identity v1 metadata index drift")
            # PostgreSQL deparses public.fn(VARCHAR) as fn(name::text). Only
            # reconcile this known index after checking its complete invariant.
            # All other Alembic operations remain visible.
            for operation in upgrade_ops.ops:
                if (
                    isinstance(operation, ops.ModifyTableOps)
                    and operation.table_name == "ingredients"
                    and operation.schema in (None, "public")
                ):
                    operation.ops[:] = [
                        item
                        for item in operation.ops
                        if not (
                            isinstance(item, (ops.CreateIndexOp, ops.DropIndexOp))
                            and item.index_name == v1.INDEX
                        )
                    ]

    _alembic_validator_registered = True
