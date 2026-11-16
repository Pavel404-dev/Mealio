# Canonical meal-plan slots (W12.1)

Meal-plan assignments use `breakfast`, `lunch`, `dinner` and `snack` as their
canonical meal types. A slot is unique within a plan by `(planned_date,
meal_type)`. The day is represented by `planned_date`; no separate day table is
needed for this slice. Recipe classification is independent of a planner slot.

## Compatibility and adoption

Existing `/api/v1` writes and reads keep their string-based contract, including
custom labels such as `brunch`. Restricting these requests or rewriting existing
labels would break clients or merge distinct slots. No data is reclassified,
deleted or backfilled, and no database migration is needed.

New clients opt into canonical writes through three endpoints:

| Method | Path | Request |
| --- | --- | --- |
| POST | `/api/v2/meal-plans` | Plan with optional canonical items |
| POST | `/api/v2/meal-plans/{meal_plan_id}/items` | Canonical item |
| PATCH | `/api/v2/meal-plans/{meal_plan_id}/items/{item_id}` | Partial item update |

These endpoints share the v1 authentication, services, repositories, ownership,
date-range validation and unique-slot checks. Successful response shapes remain
the same. Reading, updating plan metadata, deleting, calendar queries, summaries
and shopping lists continue through `/api/v1`; this is a versioned write contract,
not a copy of the entire API. There are no v2 read/delete endpoints in this slice.

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

Portion assignments and weighted nutrition/shopping-list rollups are a subsequent
W12 slice. Existing items still mean the whole recipe; this change does not divide
nutrition or grams by recipe servings. Flutter and AI generation are unchanged.
