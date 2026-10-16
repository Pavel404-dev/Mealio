# F3 — portion storage bounds / issue #197

Status: **owner approved the entire DB workflow on 2026-10-16**, exclusively for
disposable localhost:5432/mealio_test, including necessary reruns. This document
records the approved plan; actual results are in the evidence INDEX.md.
PostgreSQL/HTTP baseline was obtained and analyzed before the production fix.

- Issue: https://github.com/Pavel404-dev/Mealio/issues/197
- Confirmed branch: `fix/197-ingredients-portion-storage-bounds`
- Confirmed tracked HEAD: `92be81277650a79c2ce4c6e3e7e910cc96260879`
- Current migration graph ends at `e9c4a7b2d610`; verify with `alembic heads`.
- Only permitted future destructive target: **localhost:5432 / mealio_test**.
- Evidence directory: `/tmp/mealio-f3-197-1dEPgurO` (outside the working patch).
- Interpreter: `/home/pavel/WebstormProjects/Mealio/backend/.venv/bin/python`.

## Audit and intended patch

`NutritionValueBase.portion_g` currently has only `gt=0`; the initial migration
and runtime model use `Numeric(8,2)` with no portion CHECK. Runtime writers are
the create, attach-nutrition and update-nutrition branches of
`IngredientsRepository`. Commit precedes response serialization. The test client
uses `ASGITransport` with the default `raise_app_exceptions=True` and sessions
with `expire_on_commit=False`. Fresh sessions are necessary to observe rounding.
`PantryItemRead` embeds `IngredientRead`; recipe/pantry calculators skip
nonpositive portions. This is not evidence of division by zero.

The intended API contract is finite, exact scale <= 2 after ignoring redundant
trailing zeros, inclusive range 0.01..999999.99, default 100. No rounding into
validity, no unrelated nutrient limits. Preserve Decimal response strings,
public ingredient reads/authenticated mutations, and current omitted/null
nutrition semantics (PATCH null does not clear existing nutrition).

Use a named CHECK on the stored range in model metadata and a new revision,
keeping `Numeric(8,2)`, IDs, defaults and relationships. PostgreSQL treats numeric
NaN as greater than finite values; test the upper bound explicitly. Infinity is
already excluded by constrained numeric precision, and tests distinguish the
CHECK error from numeric overflow. A CHECK sees the value **after** numeric type
coercion: rejecting raw 0.005/1.234 without rounding belongs to API validation.
Reference: https://www.postgresql.org/docs/17/datatype-numeric.html

The migration will acquire a table lock excluding concurrent writers before
preflight and hold it through CHECK installation in the same transaction. This
can briefly block reads/writes. The local harness uses bounded lock/statement
timeouts. Invalid legacy rows must abort upgrade with a safe count and remediation
instruction, without row IDs/contents in the diagnostic and without any automatic
data changes. Tests must prove rollback of schema, data and revision as well as
concurrent-writer behavior. Downgrade removes only the new CHECK.

## Prepared identical baseline/fix regressions

- `backend/tests/test_ingredient_portion_schema.py`: POST/PATCH/read schemas,
  omitted default, min/max, integer and JSON numeric forms, trailing zeros,
  scientific notation, sub-cent and significant extra precision, zero/negative,
  overflow, bool, nonfinite, malformed and null. Includes a far fractional digit
  that must not disappear through Decimal context rounding.
- `backend/tests/test_ingredient_portion_api.py`: invalid POST cannot persist a
  row or break subsequent catalog/detail reads; invalid simultaneous name,
  category and nutrition PATCH preserves all ingredient/nutrition/recipe/link/
  pantry fields in a new session, including another user's pantry. Collect
  outcome and state before assertions, catching only relevant response-validation
  and numeric-data exceptions; connection/setup exceptions remain errors.
  Valid POST/PATCH, fresh reload, list/detail/nested pantry and moderate nutrition
  calculations; omitted/null nutrition behavior.
- `backend/tests/test_ingredient_portion_storage.py`: direct SQL and ORM INSERT
  and UPDATE, zero/negative/underflow/NaN CHECK violations and overflow/infinities,
  plus valid controls and new-connection reads. Invalid attempts always roll back,
  even on the vulnerable baseline. These use metadata-created schemas, **not**
  Alembic; they do not establish migration correctness.

These files import no future production symbols. Freeze their SHA256 before the
first baseline DB run; copy byte-identically into baseline and fixed snapshots.
If a test needs correction, keep prior logs, explain why, and run the corrected
version on both snapshots. Do not predict baseline failure counts or weaken
assertions to accept vulnerable results.

## Isolated snapshots, configuration and evidence

The baseline was extracted using `git archive` of the exact HEAD above, not a
copy of the working directory. It is at `/tmp/mealio-f3-197-1dEPgurO/baseline`.
Only the three regression files are overlaid before baseline execution. No
private `.env`, credentials, untracked user configuration or old evidence is
copied. The fixed snapshot will be extracted from the same archive into `fixed`,
then overlaid with an explicit manifest of the F3 patch, including new files.

`run.py` in the evidence directory creates an exclusive timestamp/UUID directory
for every attempt: `stdout.log`, `stderr.log`, and `metadata.json` containing exact
argv, cwd, UTC start/end and exit code. It uses a clean environment with synthetic
DB/JWT/abuse/OTP settings and no provider credentials. The shared fixtures use
no-op mailers; existing AI/provider tests use their own fakes/mocks. No external
email/AI calls are needed. There is a 30-minute process bound; inspect progress
logs while long tests run. Timeouts are environment failures, never F3 witnesses.

`f3_guard.py` is an external pytest plugin. It checks both database URLs against
the exact local target and runs `SELECT current_database()` on **every physical
SQLAlchemy connection**, before fixture DDL, then sets statement timeout 60 s
and lock timeout 10 s. `guarded_alembic.py` installs the same guard before invoking
Alembic. Import/collection does not establish connections. Failure of the target
check stops the run; it never authorizes a fallback database.

Command shorthand in this plan (shell variables are task-specific):

```bash
F3_EVIDENCE=/tmp/mealio-f3-197-1dEPgurO
F3_PYTHON=/home/pavel/WebstormProjects/Mealio/backend/.venv/bin/python
F3_REPO=/home/pavel/WebstormProjects/Mealio
```

Commands are executed separately, checking each exit code. The runner does not
itself grant DB permission; owner authorization is recorded above. Do not use
inherited production environment settings.

Before approval, allowed commands are Ruff, `alembic heads` (no env.py/DB
connection), collection, and the schema-only module (no DB fixtures), in the snapshot:

```bash
"$F3_PYTHON" "$F3_EVIDENCE/run.py" lint "$F3_EVIDENCE/baseline" "$F3_PYTHON" -m ruff check backend
"$F3_PYTHON" "$F3_EVIDENCE/run.py" format-check "$F3_EVIDENCE/baseline" "$F3_PYTHON" -m ruff format --check backend
"$F3_PYTHON" "$F3_EVIDENCE/run.py" parent-heads "$F3_EVIDENCE/baseline/backend" "$F3_PYTHON" -m alembic heads
"$F3_PYTHON" "$F3_EVIDENCE/run.py" collect "$F3_EVIDENCE/baseline" "$F3_PYTHON" -m pytest -p f3_guard --collect-only -q backend/tests/test_ingredient_portion_schema.py backend/tests/test_ingredient_portion_api.py backend/tests/test_ingredient_portion_storage.py
```

## DB approval scope and service ownership

Requested permission includes repeated recreation of **only mealio_test**, the
existing `backend/tests/conftest.py:test_engine` setup/teardown
`Base.metadata.drop_all/create_all`, synthetic fixtures, direct invalid writes
inside rolled-back transactions, and migration upgrade/downgrade/schema resets
inside that same disposable DB. Run serially; never parallel pytest workers or
baseline/fixed runs sharing the database.

Before startup record `docker compose --env-file /dev/null --project-name mealio
-f "$F3_REPO/docker-compose.yml" ps --all` and container/project identity. Do not
print environment/secret-bearing docker config or inspect output. If postgres
is already running and healthy, reuse it and leave it running. If this workflow
must start it, use only:

```bash
docker compose --env-file /dev/null --project-name mealio -f "$F3_REPO/docker-compose.yml" up -d --wait --wait-timeout 60 postgres
```

Use the clean runner environment for Docker commands too. Do not start backend
or change services/volumes. Record whether postgres existed and was running.
Keep evidence of the startup and perform cleanup even when checks fail.

Before each recreation, use a bounded command and require successful output
**exactly** `mealio_test`:

```bash
timeout 15 docker compose --env-file /dev/null --project-name mealio -f "$F3_REPO/docker-compose.yml" exec -T postgres psql -X -v ON_ERROR_STOP=1 -U mealio_user -d mealio_test -Atc 'SELECT current_database()'
```

Also confirm the host connection target through the guarded SQLAlchemy engine.
Only after both succeed, run sequentially with a 30-second bound each:

```bash
timeout 30 docker compose --env-file /dev/null --project-name mealio -f "$F3_REPO/docker-compose.yml" exec -T postgres dropdb --if-exists --force -U mealio_user mealio_test
timeout 30 docker compose --env-file /dev/null --project-name mealio -f "$F3_REPO/docker-compose.yml" exec -T postgres createdb -U mealio_user -O mealio_user mealio_test
```

Recheck `current_database()` after creation. A timeout or failed connection stops
destructive work. If mealio_test does not exist initially, confirm absence via a
read-only catalog query before an approved create-only step; then verify the
new target before any destructive operation. Never interpret failed connection
as proof of absence. Do not read/modify data in `mealio`.

## Execution after approval

1. Freeze regression-file hashes, verify snapshot imports resolve under baseline,
   record Python/dependency versions, confirm service ownership and DB identity.
2. Schema regressions were run before approval: 25 assertion failures, 61 passes,
   no setup/import errors; see the evidence INDEX. Do not repeat the unchanged
   schema run. Run HTTP/storage regressions on baseline after approval. Each attempt
   gets new logs. The same commands later run on fixed with a different label/cwd:

   ```bash
   "$F3_PYTHON" "$F3_EVIDENCE/run.py" baseline-schema "$F3_EVIDENCE/baseline" "$F3_PYTHON" -m pytest -p f3_guard -v -s --tb=short backend/tests/test_ingredient_portion_schema.py
   "$F3_PYTHON" "$F3_EVIDENCE/run.py" baseline-db "$F3_EVIDENCE/baseline" "$F3_PYTHON" -m pytest -p f3_guard -v -s --tb=short backend/tests/test_ingredient_portion_api.py backend/tests/test_ingredient_portion_storage.py
   ```

3. Analyze every baseline failure, separating assertion evidence from setup,
   import, environment and connection errors. Record actual POST/PATCH outcomes,
   fresh stored values and later reads; do not claim a predetermined HTTP result.
   If the premise is refuted, stop the unnecessary production fix.
4. Implement the bounded production fix and related docs only after witness
   analysis. Create fixed snapshot and prove regression files are byte-identical.
   Run fixed schema and DB regressions first.
5. Add/run **after-fix-only** `test_ingredient_portion_migration.py`. This suite
   must not request `test_engine`/`client` or run metadata.create_all. It must
   validate URL/current_database before DDL and build the real parent revision
   with Alembic in mealio_test, controlling its own revision/reset state. Planned
   cases: empty upgrade; valid populated upgrade with references unchanged;
   dirty zero, negative and NaN rows separately and together; failed upgrade
   preserves rows/references/catalog schema/revision; downgrade/re-upgrade;
   new-connection invalid-write enforcement; controlled concurrent writer versus
   preflight/constraint transaction. Synchronize locks with bounded waits, not
   timing assumptions. Infinities cannot be seeded in Numeric(8,2); verify their
   rejection separately instead of misrepresenting them as valid legacy seeds.
6. Run all affected existing suites once after focused checks pass. The exact
   file manifest is every existing `test_*` matching ingredients, pantry, recipe,
   meal_plan, shopping_list, plus `test_user_nutrition_profile_consumers.py`.
   Resolve it with `rg --files backend/tests`, record explicit argv (no shell
   wildcard uncertainty), and execute `pytest -p f3_guard -v <manifest>`.
7. Run full backend Ruff lint/format and require one Alembic head. Recreate
   mealio_test again with the target guards above; run real migration gates:

   ```bash
   "$F3_PYTHON" "$F3_EVIDENCE/run.py" fixed-heads "$F3_EVIDENCE/fixed/backend" "$F3_PYTHON" -m alembic heads
   "$F3_PYTHON" "$F3_EVIDENCE/run.py" fixed-upgrade "$F3_EVIDENCE/fixed/backend" "$F3_PYTHON" "$F3_EVIDENCE/guarded_alembic.py" upgrade head
   "$F3_PYTHON" "$F3_EVIDENCE/run.py" fixed-current "$F3_EVIDENCE/fixed/backend" "$F3_PYTHON" "$F3_EVIDENCE/guarded_alembic.py" current
   "$F3_PYTHON" "$F3_EVIDENCE/run.py" fixed-check "$F3_EVIDENCE/fixed/backend" "$F3_PYTHON" "$F3_EVIDENCE/guarded_alembic.py" check
   "$F3_PYTHON" "$F3_EVIDENCE/run.py" fixed-downgrade "$F3_EVIDENCE/fixed/backend" "$F3_PYTHON" "$F3_EVIDENCE/guarded_alembic.py" downgrade e9c4a7b2d610
   "$F3_PYTHON" "$F3_EVIDENCE/run.py" fixed-reupgrade "$F3_EVIDENCE/fixed/backend" "$F3_PYTHON" "$F3_EVIDENCE/guarded_alembic.py" upgrade head
   "$F3_PYTHON" "$F3_EVIDENCE/run.py" fixed-full "$F3_EVIDENCE/fixed" "$F3_PYTHON" -m pytest -p f3_guard -v --cov=app --cov-report=term-missing backend/tests
   ```

   Recheck current/check after re-upgrade. Pytest metadata fixtures are
   destructive and do not preserve Alembic state; migration tests must reset
   their own schema/revision. Coverage is not migration evidence. Preserve
   failed attempt logs, record corrections, and rerun only justified checks.
8. Cleanup within 30 seconds: leave pre-existing running postgres alone. If a
   pre-existing stopped postgres was started here, stop only postgres with
   `stop -t 10 postgres`. If a container was created here, stop then remove only
   that workflow-owned postgres container (`rm -f postgres`, no volume deletion).
   Use `down --timeout 10` only if the entire Compose project was newly created
   by this workflow and no user-owned services were present. Never use `-v`.

## Rollout and handoff requirements

Ship a focused data-remediation runbook: preflight damaged-row count, blocked
upgrade, separate owner-authorized correction from a trustworthy original source,
retry upgrade, then detail/list/pantry reads and recipe/pantry smoke. Zero cannot
recover its original portion. No defaulting to 100/0.01, deletion, clamping or
nutrition clearing is authorized. No staging/production operations here.

Before handoff compare fixed snapshot to the final working patch with cmp/SHA256
for every changed/new file. Include a full tracked+untracked diff and manifest,
`git diff --check`, new-file whitespace checks, final branch/HEAD/status. Link
actual counts/assertion fragments to immutable attempt logs in `INDEX.md`.
Update evidence if relevant code changes after a passing gate.

Provide a PR body matching `.github/pull_request_template.md` with `Closes #197`
and safe owner-only commit/push/PR commands. No agent GitHub writes or commits.
Frontend/container builds are not locally required without corresponding changes;
required Actions after owner delivery remain pending. Automated review is not
independent human approval. No deployment/device verification claimed.

## P2 review follow-up: offline SQL generation

The owner requested this follow-up under the existing F3 mealio_test approval.
Keep previous logs/snapshots/archive unchanged; use evidence subdirectory
`/tmp/mealio-f3-197-1dEPgurO/review-p2` and a new fixed snapshot from tracked HEAD
plus the explicit F3 overlay. No unchanged F3 schema/HTTP baseline rerun.

1. Before changing the migration, run the new no-connection offline-generation
   regression for both `head` and `e9c4a7b2d610:f3b197a01c02`; record the actual
   failure. Then use a server-side DO preflight under the same table lock.
2. Generate SQL again and execute the complete, unmodified parent-to-F3 output
   on real parent schemas in guarded mealio_test. Test empty/valid populated
   upgrades, preserved data/links, downgrade/re-upgrade and reconnect enforcement.
   For zero, negative and NaN (separate/mixed), require the safe count/remediation
   diagnostic and unchanged data/schema/revision after rollback. Retain online
   cases and both concurrent-writer tests. The asyncpg executor independently
   checks current_database() before executing the script and closes its connection.
3. Run the full migration test module, then portion storage tests. Repeat backend
   Ruff lint/format, one-head and guarded upgrade/current/check/downgrade/re-upgrade
   gates. Retain the earlier full backend and affected-suite results as pre-P2
   evidence; do not label them as rerun on the revised migration. No runtime
   schema/model/service/API or original three regression modules change here.
4. Use the same run.py command/cwd/time/exit logging and target guards described
   above. Start PostgreSQL only if needed, record resource identity, and clean up
   only resources created by this follow-up, preserving all volumes/user services.
5. Verify all patch hashes against the new snapshot, review tracked+untracked
   diff, and publish updated INDEX, manifest, report, PR body and a new archive.

Commands (using the shorthand above and review-p2 as F3_EVIDENCE):

```bash
"$F3_PYTHON" "$F3_EVIDENCE/run.py" before-offline "$F3_EVIDENCE/before" "$F3_PYTHON" -m pytest -p f3_guard -v --tb=short backend/tests/test_ingredient_portion_migration.py -k generates_transactional
"$F3_PYTHON" "$F3_EVIDENCE/run.py" fixed-offline "$F3_EVIDENCE/fixed" "$F3_PYTHON" -m pytest -p f3_guard -v backend/tests/test_ingredient_portion_migration.py -k generates_transactional
"$F3_PYTHON" "$F3_EVIDENCE/run.py" migration-tests "$F3_EVIDENCE/fixed" "$F3_PYTHON" -m pytest -p f3_guard -v backend/tests/test_ingredient_portion_migration.py
"$F3_PYTHON" "$F3_EVIDENCE/run.py" storage-tests "$F3_EVIDENCE/fixed" "$F3_PYTHON" -m pytest -p f3_guard -v backend/tests/test_ingredient_portion_storage.py
```
