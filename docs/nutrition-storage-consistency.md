# Gram-based nutrition writes and transaction ownership (W9 foundation)

Nutrients still describe the stored `portion_g` (default 100 g). No schema,
provider, per-100g representation, historical repair, or missing-data change is
introduced. The F3 portion contract and omitted/null nutrition semantics remain
in [the portion contract](ingredient-portion-storage.md). Omitted macros remain
zero. Decimal responses remain JSON strings.

## Write and read boundaries

Ingredient POST/PATCH nutrients must be finite decimals in `0..999999.99`, exactly
representable in existing `NUMERIC(8,2)`. Recipe and Pantry POST/PATCH quantities
must be in `0.01..99999999.99`, exactly representable in `NUMERIC(10,2)`.
`1.2300`, `12300e-4`, and `1E+2` are accepted; significant excess precision,
booleans, nonfinite values, and overflow return 422 before mutation. Validation
inspects raw Decimal digits without context-dependent normalization or rounding.
These are write-only types: existing read schemas do not inherit the tightening.

AI save reuses `RecipeIngredientCreate`, including the quantity constraint.
Preview generation keeps its existing contract; saving an unsupported generated
mass fails validation rather than silently rounding it. Client/provider nutrient
and total fields remain forbidden at the AI preview/save boundaries. Saving
requires no provider call. Shopping-list refill validates resulting Pantry stock
against storage bounds under its existing owner lock before any upsert.

## Calculation boundaries

Both Pantry and recipes use `aggregate_grams`:

```
contribution = stored nutrient * quantity_g / stored portion_g
```

Products and sums are accumulated as exact rational numbers derived from the
original Decimals. This prevents intermediate repeating-ratio errors from moving
an exact half-cent tie across the rounding boundary (three contributions of
`1 / 600` sum to exactly `0.005`). No rounded per-100g intermediate is used.
Missing nutrition and nonpositive legacy portions retain their previous zero
contribution; stored zero nutrients remain zero.

Decimal conversion uses an explicit Context: `ROUND_HALF_UP`, Emin=-999999,
Emax=999999, clamp=0, capitals=1, cleared flags, and only InvalidOperation,
DivisionByZero and Overflow traps enabled. Neither ambient nor DefaultContext
settings affect results. Pantry returns the aggregate with
`50 + digits(row count)` significant digits and no final two-place quantization.
This is deterministic finite decimal rendering of repeating rational totals,
not a promise of infinitely many decimal places.

Recipe conversion precision is at least the Pantry precision and at least
`digits(abs(numerator)) + digits(denominator) + 4`. Supported inputs have at most
8 nutrient, 10 quantity, and 8 portion digits; exact rational aggregation prevents
loss with any row count. The reduced denominator bounds the distance to a cent
rounding boundary; the extra precision preserves which side of a half-cent the
sum occupies. Exact half-cent sums terminate. Only after summation do we quantize
to two places with explicit `ROUND_HALF_UP`. Each resulting total must fit
`NUMERIC(10,2)`, otherwise the operation returns 422 and rolls back. For example,
`99999999.995` overflows after rounding. Meal plans continue summing stored recipe
totals; they do not independently rescale ingredients.

## Transactions and lock order

`nutrition_transaction` owns the complete ingredient PATCH and recipe
create/update/delete operation, including the transaction autobegun by auth.
Ingredient delete also participates. Repositories flush but never commit inside
this context. Ingredient create remains independent: a new UUID cannot yet be
referenced by committed recipes. A PATCH updates name/category/nutrition and all
dependent recipe totals with one commit; any exception, including cancellation,
calculation failure, flush failure or commit failure, rolls back the operation.
Existing W8 identity constraints and 404/409 mappings remain authoritative.

All participating writers acquire one PostgreSQL transaction advisory lock,
namespace `1296384332` (`MEAL`), key `207`, before reading mutable ingredients or
recipe composition, acquiring row locks, or flushing. Under PostgreSQL's existing
READ COMMITTED isolation, subsequent reads see the preceding writer's commit.
Repository queries use `populate_existing` for ingredient/nutrition and
recipe/composition loads so an identity-map snapshot retained before the wait
cannot override freshly read state. Dependent recipes are loaded in UUID order.
The advisory lock is released by commit/rollback, including empty operations.

The single gate deliberately serializes unrelated recipe/catalog writes too.
This bounded design trades write throughput for an auditable order without a
schema change or a retry protocol over changing recipe membership. It prevents
cycles among participating writers; tests prove actual PostgreSQL lock waits and
bounded completion using independent sessions. External SQL writers must follow
the same protocol if they require this consistency guarantee. No automatic repair
of previously stale totals is performed.

Pantry uses its existing user lock and does not acquire the nutrition gate.
Meal-plan writers do not acquire it either. Recipe ownership filters are retained;
global catalog nutrient changes intentionally update dependent recipes across
owners, without exposing those recipes through a user endpoint.

## Compatibility and rollback

Previously accepted lossy numeric writes now receive 422. Existing exact writes,
portion storage, auth, identity, ownership and response fields remain compatible.
Pantry repeating decimals can carry more digits; Flutter must continue decoding
Decimal JSON strings. No persistent schema change or migration is needed.
Reverting the application patch preserves data and references but reopens stale
recipe totals and numeric coercion risks; it does not restore historical inputs.
DB verification requires fresh target-specific approval under AGENTS.md and
issue #207. CI, review and owner delivery remain separate gates.
