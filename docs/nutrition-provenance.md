# Optional declared nutrition provenance (#213)

`nutrition_value.source_name` and `source_reference` are public, user-declared,
unverified metadata for the **current nutrition record as a whole**. They do not
certify each nutrient, completeness, confidence, or external verification. Never
put credentials or private personal data in either field. Authentication does not
assign a source or verify the declaration. Catalog GET remains public; catalog
writes still require authentication and remain shared, without new ownership or
moderation rules. Ingredient UUID and frozen name identity remain unchanged.

Both fields default to null. `source_name` accepts a strict string trimmed to
1..255 Unicode characters; `source_reference` accepts a strict string trimmed to
1..1000 characters. Blank, oversized, non-string, NUL and surrogate input receives
422 before persistent mutation. Storage-text validation is shared with ingredient
inputs, but source text is not casefolded, normalized or used as an ingredient key.
A non-null reference requires a non-null name; a name alone is valid. A reference
is opaque text: record/revision IDs and public links are accepted without URL
verification, execution, fetching or importing.

## Nested write lifecycle

| Input | POST | PATCH |
| --- | --- | --- |
| Omitted/null nutrition | No nutrition row | Preserve nutrients, portion and metadata |
| Nutrition object without source | Numeric set with null source fields | Replace numeric set and clear both source fields |
| Nutrition object with source | Store supplied declaration with numeric set | Replace numeric set and declaration together |
| Invalid input or transaction failure | No partial mutation | Preserve previous fields, metadata and dependent recipe totals |

Calories remain required in every supplied object. Omitted macros default to zero
and portion to 100 g; a source-only object receives 422. A full replacement clears
omitted metadata even when numeric values are identical. To retain a declaration,
the client resends it. There is no partial nested PATCH or metadata-only endpoint.
Other extra ingredient input keeps its existing ignore policy.

Ingredient list/detail/create/update and nested Pantry responses return both
fields, including null for unknown provenance. They serialize the existing eager
nutrition row without source lookups, per-item queries or read mutations.
`nutrition_value: null` remains null. The existing parser ignores metadata; Flutter
production code/UI does not display or edit it in this slice.

The [stored portion basis](ingredient-portion-storage.md), numeric strings,
[per-100g projection](nutrition-per100g-read.md), and
[gram-based transactions/calculations](nutrition-storage-consistency.md) are
unchanged. Metadata is not copied into `per_100g`, aggregates, recipe/meal-plan
snapshots or trust-weighted suggestions. Missing nutrition still contributes zero;
legacy default-zero macros cannot be distinguished from explicitly supplied zeros.
A positive source value may project to `"0.00"`; neither that value nor a source
label establishes exact zero or per-nutrient completeness.

AI generated/save schemas and provider context gain no source or nutrient fields.
Root and ingredient-level source/nutrient injection remains forbidden. AI save uses
catalog UUIDs and the existing recipe service without resolving a provider.

## Migration and verification boundaries

Migration `c213a7e94b02`, parent `b205c8d15a01`, adds only nullable
`VARCHAR(255)`/`VARCHAR(1000)` metadata columns and
`ck_nutrition_values_source_pair` (`source_reference IS NULL OR source_name IS NOT
NULL`). There are no defaults, source guessing, backfills, repairs or new nutrition
rows. Numeric types/defaults, portions, UUID/FK links, identity DDL and historical
totals are untouched. API validation handles trimming/storage text; the DB enforces
column lengths and the nullable pair relationship.

Downgrade drops this CHECK and both columns, **irreversibly losing declarations**.
It preserves the older data/schema but is not an application rollback procedure.
Do not execute it automatically.

Prepared regression tests cover pure validation/defaults/AI separation; API fresh
reloads, replacement/preservation, public/authenticated boundaries, owner isolation,
query counts and mutation-free reads; calculation/overflow/partial-flush/commit
rollback and controlled writer waits; genuine previous-head legacy rows, lossy
roundtrip, current-head/model parity and unrelated/missing-column drift. Historical
W8 roundtrips continue checking their own revision; current metadata parity runs
only at current head. Test presence or generated SQL is not DB verification.

DB/API suites require fresh target-specific approval under `AGENTS.md`; fixtures
recreate schema and migration suites may create cluster roles. Backend CI uses
PG17. Any compatibility claim for the previously observed staging PG18 requires
a separately authorized disposable PG18 run, never pytest on staging. Full backend
coverage, final-SHA CI, review and owner synthetic API QA remain separate evidence.
Owner QA should verify the issue's four examples, persisted fresh reads and the
provider-free AI save/injection boundaries. Flutter tests do not establish device QA.

## Owner delivery runbook: supported writers and rollback

This is an operational support policy, **not an implemented write-freeze switch**.
No service shutdown, DB migration or deployment is authorized by this document.

1. Obtain separate approval for the exact migration target and controlled backend
   cutover. Establish a feasible transition without provenance use through
   overlapping legacy writers. Account for every service, script, job and direct
   SQL writer of catalog nutrition. Nullable DDL allows older code to load, but
   does not make its writes semantically compatible.
   Allow for DDL locks and CHECK validation on `nutrition_values`; use bounded
   target-appropriate lock/statement timeouts in the separately agreed migration
   window. Additive DDL alone does not promise uninterrupted reads/writes.
2. Before provenance use, record the exact deployed metadata-aware SHA, active
   writer/service/script inventory, migration revision and verified persisted
   create/update response plus independent read-back. Deliver the server first.
   A new client against an old extra-ignore backend may receive 200 while source
   input was discarded; status alone is not evidence of persistence. Old clients
   on the new backend intentionally clear metadata on full nutrition replacement.
3. After any provenance exists, nutrition writes are supported only through
   metadata-aware versions. A legacy backend can update nutrients while leaving
   a stale declaration. The advisory gate and nullable DDL do not solve this.
   Mixed legacy/new writers, direct legacy SQL writes, snapshot/hash/trigger
   invalidation guards and a new write-freeze feature are outside this scope.
4. Record a concrete metadata-aware rollback artifact SHA when one exists; none is
   invented here. Once source is in use, an older writing backend is not a safe
   rollback target. Without a compatible artifact, fix forward or keep nutrition
   mutations unavailable until a compatible writer is restored, using separately
   agreed operational controls. Do not assume the application has a switch for it.
5. If the writer-version boundary cannot be guaranteed, stop the delivery plan and
   report the exact conflicting writer/cutover constraint to the owner. Do not
   deploy unsafely or add guards/infra implicitly. Health checks alone do not prove
   writer compatibility. Never run migration downgrade automatically on rollback.

Record migration, application cutover, CI/review, deployment decision, APK and
actual scoped QA independently through the [delivery workflow](development-workflow.md#task-handoff).
The [staging guide](staging.md#nutrition-provenance-writer-cutover) links this policy;
these instructions do not close broader W9 missing/zero decisions.
