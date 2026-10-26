"""Frozen UCD reference vectors against the actual metadata-installed SQL."""

import gzip
import hashlib
import json
import random
import re
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db.ddl import ingredient_identity_v1 as v1

DATA = Path(__file__).parent / "data/ingredient_identity_v1"
CORPUS_SHA = "97ede630ec9c6324f866a731cd311d693dcf437ac5ac42a1cffa66560a1013b9"


def vectors():
    raw = gzip.decompress((DATA / "corpus.jsonl.gz").read_bytes())
    assert hashlib.sha256(raw).hexdigest() == CORPUS_SHA
    rows = [json.loads(line) for line in raw.splitlines()]
    assert len(rows) == 45078
    return rows


def test_frozen_payload_and_official_sources():
    sources = json.loads((DATA / "sources.json").read_text())
    decoded = {}
    for name, source in sources.items():
        raw = gzip.decompress((DATA / (name + ".txt.gz")).read_bytes())
        assert len(raw) == source["bytes"]
        assert hashlib.sha256(raw).hexdigest() == source["sha256"]
        decoded[name] = raw.decode()
    frozen = json.loads(
        Path(v1.__file__).with_name("ingredient_identity_v1_data.json").read_text()
    )
    mappings = {}
    for line in decoded["CaseFolding15"].splitlines():
        fields = line.split("#")[0].strip().split(";")
        if len(fields) > 2 and fields[1].strip() in ("C", "F"):
            mappings[fields[0].strip()] = fields[2].strip()
    assert {int(k, 16): v for k, v in mappings.items()} == {
        int(k, 16): v for k, v in frozen["fold_C_F"].items()
    }
    assert len(mappings) == 1530
    assert len(frozen["barrier_Cn_Co_intervals"]) == 706
    barriers = bytearray([1]) * 0x110000
    start = None
    for line in decoded["UnicodeData15"].splitlines():
        fields = line.split(";")
        cp = int(fields[0], 16)
        if fields[1].endswith(", First>"):
            start = cp
        elif fields[1].endswith(", Last>"):
            barriers[start : cp + 1] = bytes([int(fields[2] in ("Cn", "Co"))]) * (
                cp - start + 1
            )
            start = None
        else:
            barriers[cp] = int(fields[2] in ("Cn", "Co"))
    intervals = []
    start = None
    for cp, barrier in enumerate([*barriers, 0]):
        if barrier and start is None:
            start = cp
        elif not barrier and start is not None:
            intervals.append([start, cp - 1])
            start = None
    assert intervals == frozen["barrier_Cn_Co_intervals"]
    lows, highs = [
        json.loads(
            "["
            + re.search(
                rf"{name} CONSTANT integer\[\] := ARRAY\[([^]]+)\]", v1.SNAPSHOT
            )[1]
            + "]"
        )
        for name in ("lows", "highs")
    ]
    assert list(map(list, zip(lows, highs, strict=True))) == intervals
    sql_mappings = json.loads(re.search(r"\$map\$(.*?)\$map\$", v1.SNAPSHOT, re.S)[1])
    assert sql_mappings == {
        chr(int(cp, 16)): "".join(chr(int(c, 16)) for c in output.split())
        for cp, output in mappings.items()
    }
    assert list(map(ord, v1.WHITESPACE)) == frozen["whitespace"]
    assert len(v1.WHITESPACE) == 29
    corpus_inputs = {r["s"] for r in vectors()}
    for cp, output in mappings.items():
        assert chr(int(cp, 16)) in corpus_inputs
        assert "".join(chr(int(c, 16)) for c in output.split()) in corpus_inputs
    for name in ("NormalizationTest15", "NormalizationTest16"):
        for line in decoded[name].splitlines():
            line = line.split("#")[0].strip()
            if not line or line.startswith("@"):
                continue
            for column in line.split(";")[:5]:
                assert "".join(chr(int(c, 16)) for c in column.split()) in corpus_inputs


async def test_all_reference_vectors_sql_nfc_key_bits_idempotency(db_session):
    rows = vectors()
    for start in range(0, len(rows), 400):
        batch = rows[start : start + 400]
        actual = (
            await db_session.execute(
                text("""
            SELECT public.mealio_nfc15_v1(s), public.mealio_ingredient_key_v1(s),
                   public.mealio_ingredient_bits_v1(s)::text,
                   public.mealio_ingredient_key_v1(public.mealio_ingredient_key_v1(s))
            FROM unnest(CAST(:inputs AS text[])) WITH ORDINALITY AS t(s,ordinal)
            ORDER BY ordinal
        """),
                {"inputs": [r["s"] for r in batch]},
            )
        ).all()
        for expected, result in zip(batch, actual, strict=True):
            assert tuple(result) == (
                expected["n"],
                expected["k"],
                expected["e"],
                expected["k"],
            ), expected["i"]
            bits = result[2]
            if bits is not None:
                assert len(bits) == 21 * len(result[1])
                assert (
                    "".join(
                        chr(int(bits[i : i + 21], 2)) for i in range(0, len(bits), 21)
                    )
                    == result[1]
                )


async def test_native_version_boundary_and_unbounded_helpers(db_session):
    major = int(await db_session.scalar(text("SHOW server_version_num"))) // 10000
    for value in ["\U000105d2\u0307", "a\U00010d69\u0323"]:
        native, adapted = (
            await db_session.execute(
                text("SELECT normalize(:s,NFC), public.mealio_nfc15_v1(:s)"),
                {"s": value},
            )
        ).one()
        assert adapted == value
        assert (native != adapted) == (major == 18)
    long = "\U0001d160" * 600
    result = await db_session.scalar(
        text("SELECT char_length(public.mealio_ingredient_key_v1(:s))"), {"s": long}
    )
    assert result == 1800


async def test_real_index_storage_reindex_prefixes_and_check(test_engine):
    async with test_engine.begin() as c:
        names = [
            "\U0001d160" * 255,
            "\u0100",
            "\u0200",
            "\U00100000",
            "\U00100000\u0100",
            "A\u0100",
            "Cafe",
            "Café",
        ]
        for name in names:
            await c.execute(
                text("INSERT INTO ingredients(id,name) VALUES (:id,:name)"),
                {"id": uuid4(), "name": name},
            )
        before = (
            await c.execute(
                text(
                    "SELECT id,name,public.mealio_ingredient_bits_v1(name)::text FROM ingredients ORDER BY id"
                )
            )
        ).all()
        await c.execute(text("REINDEX INDEX ux_ingredients_identity_v1"))
        assert (
            await c.execute(
                text(
                    "SELECT id,name,public.mealio_ingredient_bits_v1(name)::text FROM ingredients ORDER BY id"
                )
            )
        ).all() == before
        await c.execute(text("SET LOCAL enable_seqscan=off"))
        plan = (
            (
                await c.execute(
                    text(
                        "EXPLAIN SELECT id FROM ingredients WHERE public.mealio_ingredient_bits_v1(name)=public.mealio_ingredient_bits_v1('cAFE')"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert "ux_ingredients_identity_v1" in "\n".join(plan)
        assert (
            await c.execute(
                text(
                    "SELECT char_length(public.mealio_ingredient_key_v1(:s)),octet_length(public.mealio_ingredient_key_v1(:s))"
                ),
                {"s": names[0]},
            )
        ).one() == (765, 3060)
        # Conservative bound, not a claim that 1020 scalars are attainable by name255.
        await c.execute(
            text(
                "CREATE TEMP TABLE identity_storage_bound(k varbit NOT NULL) ON COMMIT DROP"
            )
        )
        rng = random.Random(205)
        keys = ["".join(str(rng.randrange(2)) for _ in range(21420)) for _ in range(12)]
        for key in keys:
            await c.execute(
                text(
                    "INSERT INTO identity_storage_bound VALUES (CAST(CAST(:key AS text) AS varbit))"
                ),
                {"key": key},
            )
        await c.execute(
            text(
                "CREATE UNIQUE INDEX identity_storage_bound_idx ON identity_storage_bound(k)"
            )
        )
        assert (
            await c.scalar(
                text("SELECT min(bit_length(k)) FROM identity_storage_bound")
            )
            == 21420
        )
        size = await c.scalar(
            text("SELECT max(pg_column_size(k)) FROM identity_storage_bound")
        )
        assert size == 2686  # varlena+bit header+payload; NOT index tuple size.
        await c.execute(text("REINDEX INDEX identity_storage_bound_idx"))
    for name, state in [("cAFE", "23505"), ("\x1c \t", "23514"), ("x" * 256, "22001")]:
        with pytest.raises(DBAPIError) as error:
            async with test_engine.begin() as c:
                await c.execute(
                    text("INSERT INTO ingredients(id,name) VALUES (:id,:name)"),
                    {"id": uuid4(), "name": name},
                )
        assert error.value.orig.sqlstate == state
