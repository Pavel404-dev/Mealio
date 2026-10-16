# Ingredient portion numeric contract and rollout

Ingredient POST/PATCH nutrition uses `calories`, `protein_g`, `carbs_g` and
`fat_g` **for the specified `portion_g`**, not invariably per 100 g.
Omitting `portion_g` still defaults to 100 g. Decimal response fields remain
JSON strings. Authentication, shared-catalog access and response shapes do not
change. Omitted/null `nutrition_value` on create means no nutrition; on PATCH,
omitted/null nutrition leaves existing nutrition unchanged.

This fix deliberately tightens the numeric input contract: a portion must be
finite, from **0.01 through 999999.99 g inclusive**, and exactly representable
with two decimal places. `100`, `100.00`, `100.000`, `0.0100`, `1e-2` and `1E+2`
are accepted. Redundant trailing zeros are not significant fractional precision.
`0.001`, `0.004`, `0.005`, `1.234`, zero, negative values, overflow, booleans,
nonfinite values and malformed inputs are rejected by validation with HTTP 422
before ingredient/nutrition mutation. No rounding into validity occurs.

For example, a PATCH combining a name change with `portion_g=0.005` changes
neither name nor nutrition nor dependent recipe totals. Valid boundary portions
round-trip through independent DB sessions and ingredient/pantry reads.

## Stored invariant

`nutrition_values.portion_g` stays `NUMERIC(8,2) NOT NULL DEFAULT 100`. Model
metadata and migration `f3b197a01c02` (parent `e9c4a7b2d610`) add the named CHECK
`ck_nutrition_values_portion_g_bounds`: `portion_g BETWEEN 0.01 AND 999999.99`.
The upper bound also rejects PostgreSQL numeric NaN, which sorts above finite
values. Constrained numeric precision rejects infinities and overflow.
See [PostgreSQL numeric semantics](https://www.postgresql.org/docs/17/datatype-numeric.html).

A database CHECK observes the value after numeric scale coercion. It protects
stored values, including SQL/ORM writers, but cannot reject every raw excess-scale
input: direct SQL `0.005` can become stored `0.01`. API validation rejects that
input before SQL. Other writers must enforce exact input precision themselves.

## Upgrade and damaged-data runbook

This patch **does not repair existing rows**. Old small positive inputs may have
become zero after storage; the original portion cannot be recovered from zero.
Do not replace zero with 100/0.01, clamp values, delete rows or clear nutrition.

1. The owner selects and verifies the deployment database and takes the normal
   backup. Schedule a maintenance window or pause ingredient nutrition writers.
   Deploy the stricter API validation before or together with the constraint.
   Keep writers paused until the migration succeeds. Do not deploy a stricter
   read contract over damaged rows and assume this will restore reads.
2. A read-only preflight can count affected rows:

   ```sql
   SELECT count(*) AS invalid_portion_rows
   FROM nutrition_values
   WHERE NOT (portion_g BETWEEN 0.01 AND 999999.99);
   ```

   This advisory query is not race protection. The actual upgrade obtains an
   `ACCESS EXCLUSIVE` lock on `nutrition_values`, checks again, and installs
   the CHECK in one transaction. It temporarily blocks reads/writes on that
   table. Use deployment-appropriate bounded lock/statement timeouts; retry a
   timed-out migration in a suitable maintenance window.
   The count and diagnostic run in a PostgreSQL `DO` block in both online
   upgrades and offline-generated SQL. For SQL delivery from the parent revision,
   generate `alembic upgrade e9c4a7b2d610:f3b197a01c02 --sql`. Execute the complete
   output with a fail-fast SQL client (for example, `psql -X -v ON_ERROR_STOP=1`)
   against the owner-verified target, preserving its `BEGIN`/`COMMIT` wrapper.
   Generation alone does not validate existing rows; the preflight runs when the
   script is executed. Never remove the lock, preflight or transaction wrapper.
3. Run `alembic upgrade head` against the owner-selected target. If invalid rows
   exist, the error reports only a count and this runbook. The transaction aborts;
   data, schema and Alembic revision are unchanged. Do not stamp the revision,
   bypass preflight or consider a failed upgrade deployed.
4. Arrange a **separate owner-authorized data correction**. Establish each
   original portion and nutrient basis from a trustworthy source (original
   import, verified label or authoritative backup). Review exact records and
   units, dependent recipes and user pantry implications before changing data.
   Existing recipe totals may also be stale; review/recalculate those through an
   explicitly authorized process. A guessed portion is not remediation. If no
   trustworthy source exists, leave rollout blocked for an owner decision.
5. After that separate correction, repeat the read-only count and retry upgrade.
   Check `alembic current`, `alembic heads` (one head) and `alembic check`. Verify
   the named CHECK from a new connection and check ingredient detail/list,
   affected users' nested pantry reads, and moderate recipe/pantry nutrition
   calculations. Resume writers only after successful verification.

Downgrade to `e9c4a7b2d610` removes only this CHECK, preserving values and links.
It reopens the stored-value vulnerability; retain API validation and control
writers. Re-upgrade repeats preflight and may block if invalid rows appeared.

Only disposable `localhost:5432/mealio_test` was authorized for local F3
verification. This runbook does not authorize modifications to `mealio`, staging
or production. Metadata-created test schemas and genuine parent-revision Alembic
tests are separate evidence; coverage alone cannot prove migration correctness.
