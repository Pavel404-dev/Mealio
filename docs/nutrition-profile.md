# Backend nutrition profile (W4 + W7)

`GET /api/v1/user-preferences/nutrition` and
`PATCH /api/v1/user-preferences/nutrition` require authentication and operate only
on the authenticated user's profile. Both return HTTP 200 with the profile,
without `id` or `user_id`. An unauthenticated request returns 401.

The profile is stored in `user_nutrition_profiles`, with at most one row per user.
GET returns defaults without inserting a row when no profile exists. PATCH
creates or partially updates that row. W4 demographic and financial fields
default to `null`, including for profiles created before W4; no such data is
inferred. W7 likes default to `[]`.

## Fields

All ranges below are technical storage/input bounds, **not medical advice**.

| Field | Type and units | Accepted values | Default |
|---|---|---|---|
| `goal` | string | `lose_weight`, `maintain`, `gain_weight` | `maintain` |
| `diet_type` | nullable string | trimmed, at most 100 characters; blank becomes `null` | `balanced` |
| `daily_calories_target` | nullable integer, kcal/day | 1–2147483647 (PostgreSQL Integer maximum) | `null` |
| `daily_protein_target_g` | nullable integer, g/day | 1–2147483647 | `null` |
| `daily_carbs_target_g` | nullable integer, g/day | 1–2147483647 | `null` |
| `daily_fat_target_g` | nullable integer, g/day | 1–2147483647 | `null` |
| `allergies` | array of strings | entries trimmed, blanks removed | `[]` |
| `disliked_ingredients` | array of strings | entries trimmed, blanks removed | `[]` |
| `liked_ingredients` | array of strings | entries trimmed, blanks removed; no exclusion override | `[]` |
| `preferred_meals_per_day` | nullable integer | 1–8 | `3` |
| `sex` | nullable string | `male`, `female` | `null` |
| `birth_date` | nullable date | `YYYY-MM-DD`, 1900-01-01 through the current UTC date, inclusive | `null` |
| `height_cm` | nullable Decimal, cm | 50.0–250.0 inclusive, at most 1 fractional digit | `null` |
| `weight_kg` | nullable Decimal, kg | 10.00–500.00 inclusive, at most 2 fractional digits | `null` |
| `activity_level` | nullable string | `sedentary`, `lightly_active`, `moderately_active`, `very_active`, `extra_active` | `null` |
| `max_cooking_time_minutes` | nullable integer, minutes | 1–480 inclusive; preferred maximum **total** cooking time of one dish, matching `prep_time_minutes` semantics | `null` |
| `weekly_food_budget_amount` | nullable Decimal, currency units | 0.01–1000000.00 inclusive, at most 2 fractional digits; food budget for one person over seven days | `null` |
| `budget_currency` | nullable string | trimmed and uppercased, exactly 3 ASCII letters A–Z | `null` |

Currency validation checks **format only**. There is no currency registry or
conversion; a syntactically valid code such as `ZZZ` is accepted. Changing the
currency does not convert or otherwise change the amount.

Decimal inputs accept JSON numbers or decimal strings; strings are recommended
for exact decimal values. Responses use **JSON strings** for Decimal, following
the project's existing Pydantic schemas, e.g. `"170.5"`, `"70.25"`, `"120.50"`.
Storage uses PostgreSQL `Numeric(4,1)`, `Numeric(5,2)`, and `Numeric(9,2)` for
height, weight, and budget respectively. API input rejects booleans, NaN,
Infinity, out-of-range values, and excess fractional digits (including trailing
zeros beyond the field's scale); it never silently rounds. The returned number
of fractional digits reflects the storage scale.

The new integer field rejects booleans, fractional numbers, numeric strings,
and floating-point numbers such as `1.0`. Existing integer fields retain their
previous coercion behavior, with the added PostgreSQL upper bound for the four
daily targets. No arbitrary calorie or macro limits are introduced.

Birth dates are checked against UTC at write time, never against the client's
local timezone. Neither stored nor computed age is part of this API.

## Partial updates and validation

- Omitted fields are preserved; explicit `null` clears a nullable field.
- `goal`, `allergies`, `disliked_ingredients`, and `liked_ingredients` cannot be `null`.
- `[]` clears a list. Normalization preserves order and duplicates.
- Empty `{}` creates a default profile when absent, otherwise changes nothing.
- Unknown fields, including `id`, `user_id`, and `age`, return 422.
- Invalid fields return 422 without modifying the profile.
- Budget amount and currency must be either both `null` or both populated.
  Validation uses the **merged current profile and PATCH** inside the transaction.
  An incomplete pair returns 422 without creating or modifying a row.

The profile retains its existing list compatibility: it does not impose the AI
context's 25-item / 100-character limits. AI generation continues to reject
profiles exceeding those limits separately; allergies are never truncated.

## Examples

An absent profile's GET returns all fields with the defaults in the table,
including the eight new `null` values, and creates no row.

A height/weight PATCH preserves previously set targets and allergies:

```json
{"height_cm": "175.0", "weight_kg": "72.50"}
```

A complete budget PATCH succeeds:

```json
{"weekly_food_budget_amount": "100.00", "budget_currency": " eur "}
```

The response contains `"100.00"` and `"EUR"`. Subsequent
`{"weekly_food_budget_amount": "125.50"}` succeeds and preserves `EUR`.
On a profile with no budget, that same amount-only PATCH returns 422.
`{"budget_currency": null}` returns 422 while the amount is populated; clearing
both fields succeeds:

```json
{"weekly_food_budget_amount": null, "budget_currency": null}
```

## Transactions and consumers

The service owns commit/rollback. Before reading or mutating a profile, PATCH
locks the authenticated user's existing `users` row through
`UsersRepository.get_by_id_for_update`. This covers first creation as well as
updates and works with the transaction opened by authentication's query.
Validation, mutation, flush, response validation, and commit form one operation;
errors before commit roll back all changes. Unexpected database errors propagate.

Concurrent first PATCHes of height and weight create one row containing both
changes. Same-field writes take the value of the last serialized operation.
The profile is reread after acquiring the owner lock, including when the session
previously loaded it. Budget validation therefore also sees committed concurrent
changes.

W4 only stores these inputs. It does not calculate calories/macros, activity
coefficients, recipe time filters, budget conversion, or dietary recommendations.
The AI context continues to include only the previous explicitly selected fields;
none of the eight new fields is sent to the provider. Pantry personalization and
nutrition progress/gaps continue to use explicit existing targets/preferences.
W7 extends the [optional Flutter setup](frontend-nutrition-setup.md) using this
same profile and endpoints; it adds no completion state or forced onboarding.

W5 adds a separate, read-only
[personal nutrition calculation endpoint](nutrition-calculation.md). Its support
envelope does not change W4 input/storage bounds, GET/PATCH semantics or manual
targets, and its estimates are not automatically used by existing consumers.

## Migration and rollback

Migration `e9c4a7b2d610` follows `b7e3c9a1d5f8` and adds eight nullable columns,
without backfilling or altering existing profile values. Named CHECK constraints
cover new enums, ranges, UTC birth-date bounds, uppercase ASCII currency format,
and the budget pair. Numeric scale is provided by column types; direct SQL writes
can be rounded by PostgreSQL's Numeric coercion, so exact input validation belongs
at the API boundary.

Downgrading from `e9c4a7b2d610` to `b7e3c9a1d5f8` removes the W4 constraints
and eight columns. From a later revision it also traverses later migrations;
see the W7 likes data-loss warning below.
**Values of all new fields are lost on downgrade**; the original profile row,
its identity, existing goals, targets, lists, and timestamps remain. Export any
new-field data that must be retained before downgrade, and coordinate application
and schema versions: W4 code requires the new columns.

## W7 likes and explicit adoption

Migration `a7203c91d602` follows `f3b197a01c02`, adding only non-null JSONB
`liked_ingredients` with a database/Python/schema default of `[]`. Existing rows
retain their identities, values, targets and timestamps. Default GET exposes
`[]` without INSERT. Omission preserves likes; `[]` clears; null returns 422.
Normalization trims entries and removes blanks, retaining order, duplicates and
overlaps with allergies/dislikes. There are no AI-specific list limits.

Likes are stored only. They are absent from AI/provider context and cannot weaken
existing allergies/dislikes exclusions. Cooking/budget enforcement and new diet
or allergen filters are not part of W7. Existing consumers continue using saved
`daily_*` targets. W5 calculate stays read-only. Flutter applies a displayed
estimate only by an explicit targets-only PATCH of all four integers; preserving
manual/partial targets sends no target mutation. The multi-step flow is not one
transaction. Calculate/apply remains last-write-wins across devices, without
revisions or stale-confirm rejection; an intervening target update can be
replaced by the confirmed snapshot.

Roll out backend/schema before the new frontend, whose reader requires the likes
field. Preferred rollback removes the new frontend while retaining this additive
column and data. Downgrade to `f3b197a01c02` **permanently removes saved likes**;
all older columns/row identities remain. It requires an explicit backup/migration
plan and target-specific approval. Do not downgrade real data as a verification
step. Authorized migration tests use only disposable local `mealio_test`.
