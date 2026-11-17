# Meal-plan slots and portions (W12)

Meal-plan assignments use `breakfast`, `lunch`, `dinner` and `snack` as their
canonical meal types. A slot is unique within a plan by `(planned_date,
meal_type)`. The day is represented by `planned_date`; no separate day table is
needed for this slice. Recipe classification is independent of a planner slot.

## Compatibility and adoption

Existing `/api/v1` writes and reads keep their string-based contract, including
custom labels such as `brunch`. Restricting these requests or rewriting existing
labels would break clients or merge distinct slots. No data is reclassified,
deleted or backfilled. W12.1 canonical slots needed no database migration;
W12.2 adds a nullable portion count as described below.

New clients opt into canonical writes through three endpoints:

| Method | Path | Request |
| --- | --- | --- |
| POST | `/api/v2/meal-plans` | Plan with optional canonical items |
| POST | `/api/v2/meal-plans/{meal_plan_id}/items` | Canonical item |
| PATCH | `/api/v2/meal-plans/{meal_plan_id}/items/{item_id}` | Partial item update |

These endpoints share the v1 authentication, services, repositories, ownership,
date-range validation and unique-slot checks. V2 responses now add
`planned_servings` to items. V2 also provides GET `/api/v2/meal-plans` with the
same search, date filters and pagination as v1, and GET
`/api/v2/meal-plans/{meal_plan_id}`, so clients can reload the saved count.
Updating plan metadata, deleting, calendar queries, summaries and shopping lists
continue through `/api/v1`. V1 request/response fields remain unchanged.

V2 accepts only the four canonical strings after trimming whitespace and
lowercasing. Unknown labels, null, blank, non-text values and unknown request
fields return 422 before any write. PATCH omission preserves the stored value,
including a legacy custom label; explicit `meal_type` must be canonical. Responses
therefore retain string meal types so that legacy assignments can still be read.
New clients should offer canonical choices and preserve unrecognized saved labels
when editing unrelated fields. The v1 contract has no removal date in this slice.

## Behavior examples and checks

- A v2 plan containing `"  LuNcH "` stores `"lunch"`; all four canonical slots can
  coexist on one date. GET through v1 returns the same assignments.
- Creating a plan with both `"Lunch"` and `"lunch"` on one day returns 409 and
  creates no plan. Adding or moving an item into an occupied slot also returns 409.
- A v1 `"brunch"` assignment remains readable. A date-only v2 PATCH preserves it;
  PATCH with `"snack"` explicitly converts it. PATCH with `"brunch"` returns 422
  and leaves the recipe, date and label unchanged.
- Foreign plans/items/recipes remain inaccessible (404); unauthenticated requests
  return 401. Invalid plan ranges or assignment dates return 422 without writes.

Schema/OpenAPI tests verify canonical validation and the untouched v1 contract.
PostgreSQL API tests verify cross-version persistence, legacy PATCH preservation,
atomic rejection, duplicate slots, dates and ownership using the shared services.

## Planned portions (W12.2)

`planned_servings` is optional on v2 nested items, add-item and item PATCH.
It accepts finite numbers or decimal strings from `0.01` to `12`, in exact
hundredths; booleans and values needing rounding return 422 before any write.
For example `"1.2500"` is accepted as 1.25, whereas `"1.005"` is rejected.
The bound is per assignment; a recipe yielding four portions may be planned for
six. PATCH omission preserves the count; explicit null restores whole-recipe
mode. Create omission/null means the whole recipe. V1 ignores this unknown
request field and never returns it; unrelated v1 PATCHes preserve a stored count.

For each item, the multiplier is `planned_servings / recipe.servings`, or 1 for
null. The recipe's current yield, whole-recipe nutrition and ingredients are used,
so recipe edits immediately affect explicit portions. Changing yield alone never
changes a null assignment's whole-recipe totals. Recipe suggestions still score
whole recipes; the nutrition gap they use reflects planned portions.

The same weighting applies to plan summaries, daily summaries, nutrition calendar
progress (and derived gaps/recommendations), per-plan shopping lists and combined
shopping lists. Totals sum exact fractions before rounding once to hundredths
with `ROUND_HALF_UP`. Each returned group is rounded independently: a whole-plan
total can differ from the sum of displayed daily totals. Shopping
lists round required grams first, then subtract pantry stock; add-missing uses
those same grams and keeps the existing storage-overflow and transaction guards.
SQL uses the common denominator 27720 for integer recipe yields 1..12, avoiding
intermediate division/rounding. A change to that yield range must update this
denominator and its regression cases.

- Recipe: four portions, 330 kcal, 62 g protein, 7.20 g fat, 200 g ingredient.
  Planning one portion gives 82.50 kcal, 15.50 g protein, 1.80 g fat and 50 g
  ingredient. Null gives the original 330 kcal and 200 g.
- Three one-portion assignments of a three-portion recipe with a whole-recipe
  quantity of 0.01 sum to 0.01, even though each displayed partial amount would
  round to zero. Half-cent totals round up.

Migration `a457b0d32c04` adds nullable unconstrained NUMERIC plus a CHECK for
bounds and exact hundredths; it has no default/backfill and leaves historical
rows null. An unconstrained type prevents PostgreSQL from rounding invalid writes
before checking them. Deploy the migration before the new backend. Old writers
can omit the column and preserve it during unrelated updates.

Downgrade rejects any non-null portion count before dropping schema. Rolling back
to an old application also ignores weighted amounts and is unsafe once explicit
counts exist. Keep weighted readers available or make a deliberate data migration
decision before rollback; no automatic clearing or reinterpretation is provided.

Regression tests cover validation, versioned reads and PATCH behavior, ownership,
live recipe edits, exact aggregate rounding, pantry subtraction/refill, storage
bounds, and populated migration preservation/rejection. Flutter and AI generation
are unchanged by this backend slice.
