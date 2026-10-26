# Ingredient identity: W8 core

Ingredient UUID is the only reference identity. `name` is a human-readable base
label, independent of locale; historical labels are not assumed to be English.
Renaming preserves UUID, Pantry/recipe links, quantities and ownership. Category
remains optional free text. Translation storage/API, taxonomy, aliases, semantic
merging and W9/W10 are separate work. W7 preferences and generated-recipe provider
payloads retain their existing rules.

## Frozen equivalence

Runtime equivalence lives in PostgreSQL, including exact batch validation and
matching. Python only validates representability and trims the explicit W set
for create/update/exact inputs, before length/blank checks.

```
K(NULL) = NULL
K(s) = N15(F15(collapse_W(trim_W(N15(s)))))
E(s) = concatenate(each scalar of K(s) encoded in exactly 21 bits)
```

F15 is Unicode 15.0 default full C+F case folding, without S/T. Mappings are
concatenated per input scalar, never applied as sequential replacements.
W is U+0009–000D, U+001C–001F, U+0020, U+0085, U+00A0, U+1680,
U+2000–200A, U+2028, U+2029, U+202F, U+205F, U+3000 (29 scalars).
Interior whitespace runs become one ASCII space. This includes U+001C–001F,
which Pydantic's default whitespace trimming does not treat like Python.

N15 splits at frozen Unicode15 Cn/Co scalars; each intervening run uses native
NFC, and barriers are copied unchanged. Never NFC-normalize the concatenated
result: newly assigned combining marks/composites in a newer Unicode database
could otherwise change order or composition across a Unicode15 barrier.
U+105D2 U+0307 and U+0061 U+10D69 U+0323 distinguish native Unicode16 from this
policy. Unicode normalization stability applies to the frozen assigned repertoire,
not arbitrary future assignments. No alphabet restriction is introduced.

Diacritics and punctuation remain significant: Cafe/Café and Chicken Breast/
Chicken Thigh stay distinct; Straße/STRASSE and composed/decomposed Café conflict.
No NFKC, transliteration, fuzzy lookup or automatic merge occurs. K is idempotent.
NUL and surrogate code points cannot be PostgreSQL UTF8 text and are rejected
before binding for affected API inputs. Private-use, unassigned and noncharacters
remain valid. Helpers accept arbitrary text; only the DB name column has a
255-character bound. Display names retain case/internal spacing and are not
rewritten by the migration.

`E` returns unbounded varbit: no typmod, hash or truncation. Fixed-width scalar
encoding plus bit length distinguishes prefixes and trailing zero bits and is
injective. The conservative name255 bound is 1020 output scalars / 21420 bits /
2678 payload bytes; on the verified 8KiB, 64-bit PostgreSQL layout a single
non-null index item is at most 2696 bytes (limit 2704). The attainable musical
symbol U+1D160 ×255 produces 765 scalars /3060 UTF8 bytes. The larger varbit storage
boundary is tested separately; it is not claimed attainable from that witness.

## Storage and application behavior

`ux_ingredients_identity_v1` is UNIQUE over complete E(name), using varbit_ops
(binary, no collation dependency). `ck_ingredients_identity_v1_valid` requires
1..1020 key scalars; name itself remains NOT NULL VARCHAR(255). The old raw unique
`ix_ingredients_name` remains. Old SQL/ORM writers need only supply name.

Advisory lookup improves feedback but cannot enforce uniqueness. Structured
SQLSTATE 23505 plus one of these two index names maps to the existing 409.
Other integrity failures propagate after rollback. Rejected PATCH rolls back
name/category/nutrition together and does not recalculate recipes. Successful
nutrition changes retain the existing commit-then-recalculation flow; this work
does not redesign all transactions. Decimal/null/omitted semantics are retained.
Nutrients describe `portion_g` (default 100), not necessarily 100 grams.

Search uses literal `strpos(K(name) COLLATE "C", K(query) COLLATE "C")`; %, _ and
backslash are ordinary characters. Query K is materialized once, including for
generic prepared plans. Raw empty search remains 422; nonempty W-only search
has no filter. Ordering is name COLLATE "C", then UUID; pagination is unchanged.
Substring search still scans/normalizes catalog rows and is not indexed search.
Measure catalog/long-query costs for the deployment workload; synthetic timings
are not a production capacity guarantee. No new search length cap is imposed.

The authenticated exact helper retains 1–50 inputs, trimmed generated_name,
ordinal order, unmatched null and the existing duplicate 422 location/message.
SQL E determines duplicates and exact joins; Python keys do not associate results.
It performs no writes or provider calls. Similar foods do not count as exact.

## Immutable DDL and reproducibility

`backend/app/db/ddl/ingredient_identity_v1.{py,sql}` is an immutable historical
snapshot shared by metadata and revision `b205c8d15a01` (parent `a7203c91d602`).
The SQL file contains source/license/hash attribution; Unicode data and license
are adjacent. Do not edit released v1 bodies or replace functions under an index.
A future semantic change needs v2, collision audit and explicit index rebuild.
There are no network downloads or mutable lookup tables at migration/runtime.

Helpers are IMMUTABLE, STRICT, SECURITY INVOKER, with search_path=pg_catalog and
qualified helper calls. Metadata creates helpers before CHECK/index; repeated
metadata create_all verifies exact bodies/attributes instead of replacing them.
Partial metadata creation is scoped to the requested tables, including checkfirst.
The event uses SQLAlchemy 2.0.36 SchemaGenerator original-table scope because the
event list excludes existing tables; revalidate this hook before upgrading SQLAlchemy.
Drop removes helpers in reverse order,
RESTRICT, only after dropping ingredients. Catalog-tracked external dependencies stop
the transaction; inventory external callers before removing helpers. Direct table.create(checkfirst=True) skips SQLAlchemy events if
the table exists; use metadata.create_all or validate_identity_ddl to verify drift.

Alembic's ordinary comparator is supplemented with a narrow validator for exact
helper bodies/attributes, CHECK and expression index/opclass. It does not ignore
other model/schema drift. `alembic check` must pass on the current revision.
Online migration completion (including a no-op upgrade head) validates v1 while
its revision remains in the installed history; database drift fails closed.
Test fixtures verify their endpoint/cluster before destructive DDL. The existing
CI localhost:5432/mealio_test/mealio_user path remains; alternate integration runs
require a matching Docker ID/run label/pinned image/loopback port/cluster attestation.

The committed compressed test corpus contains 45078 vectors, all C+F inputs and
outputs, Unicode15/16 normalization cases, mixed boundaries, whitespace and
seeded random cases. `backend/.venv/bin/python
backend/tests/data/ingredient_identity_v1/reproduce.py` (one command) reconstructs
it byte-for-byte with UCD15. Tests compare actual SQL N15/K/E and idempotency with
that independently generated reference. Attribution/checksums accompany inputs.

## Rollout, failure and recovery

Supported assumptions are PostgreSQL17/18, UTF8, 8KiB blocks, a 64-bit build.
Compatibility fails closed elsewhere. An actual staging version/role/collation
and capacity check is still required before deployment; historical checkpoints
are not current evidence. Cross-major upgrades require checking frozen-v1
conformance and REINDEX on the selected target before admitting writers.

1. Owner selects target, takes/verifies backup and controls writers/maintenance
   window. Deploy role needs schema CREATE and table ownership; runtime needs
   schema USAGE, normal DML privileges and EXECUTE on all three helpers, without
   schema CREATE. Deployment-specific grants must be audited, not inferred from
   a superuser test. SECURITY DEFINER is not used.
2. Run genuine-parent tests and metadata/Alembic parity first. For offline delivery,
   generate `alembic upgrade a7203c91d602:b205c8d15a01 --sql` without connecting,
   then execute the complete unmodified script using an error-stopping runner.
   Generation does not inspect target data. Never split dollar-quoted blocks at
   semicolons. Alembic owns BEGIN/COMMIT; no CONCURRENTLY/autocommit is used.
3. Upgrade sets local lock_timeout=5s and statement_timeout=60s, takes ACCESS
   EXCLUSIVE on ingredients before creating helpers or examining data, computes
   invalid/collision-group/excess counts, then adds CHECK and UNIQUE index in
   the same transaction. Lock excludes the preflight/enforcement writer race.
   It blocks readers/writers during the bounded build; schedule accordingly.
4. Legacy invalid keys/collisions fail with counts and this runbook only. The
   transaction rolls back schema, helper creation and Alembic revision. Original
   names/UUID/FK/nutrition are never UPDATEd; building derived index tuples is
   separate from rewriting source rows. Timeouts also abort atomically. Retry
   only after the contention/data problem is resolved.
5. Stop on bad legacy data. Owner-authorized adjudication is a separate task:
   inspect privately, decide intended records, review reference effects and
   repair explicitly under backup/writer control. This migration never renames,
   merges, deletes or remaps records and does not print names or keys.
6. Schema downgrade locks ingredients, drops only the new index/CHECK, then the
   three helpers in reverse order RESTRICT. It preserves rows/references but
   loses normalized uniqueness and blank-key protection. Control old writers;
   re-upgrade audits any intervening writes again and may legitimately fail.

Application rollback is separate. Checked-in `.railway/railway.ts` and `docs/staging.md` specify Railway
pre-deploy `alembic upgrade head`; an old image lacking b205c8d15a01 cannot safely
traverse the new database revision. Prefer a reviewed forward-revert image that
restores selected application behavior while retaining migration history, frozen
DDL and the compatible schema. Verify startup/pre-deploy on a disposable clone
before deployment. Simple Redeploy of an old image is not an assured recovery.
If schema downgrade is required, use an image that knows both revisions, control
writers, execute/verify downgrade, then coordinate application recovery. Existing
bases, Railway and deployment are not touched by local integration tests.
