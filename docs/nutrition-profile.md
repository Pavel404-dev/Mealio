# Backend nutrition profile (W4)

`GET /api/v1/user-preferences/nutrition` and
`PATCH /api/v1/user-preferences/nutrition` require authentication and operate only
on the authenticated user's profile. Both return HTTP 200 with the profile,
without `id` or `user_id`. An unauthenticated request returns 401.

The profile is stored in `user_nutrition_profiles`, with at most one row per user.
GET returns defaults without inserting a row when no profile exists. PATCH
creates or partially updates that row. New fields default to `null`, including
for profiles created before W4; no demographic or financial data is inferred.

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
- `goal`, `allergies`, and `disliked_ingredients` cannot be `null`.
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
Flutter onboarding is outside this change.

## Migration and rollback

Migration `e9c4a7b2d610` follows `b7e3c9a1d5f8` and adds eight nullable columns,
without backfilling or altering existing profile values. Named CHECK constraints
cover new enums, ranges, UTC birth-date bounds, uppercase ASCII currency format,
and the budget pair. Numeric scale is provided by column types; direct SQL writes
can be rounded by PostgreSQL's Numeric coercion, so exact input validation belongs
at the API boundary.

Downgrading to `b7e3c9a1d5f8` removes only the new constraints and eight columns.
**Values of all new fields are lost on downgrade**; the original profile row,
its identity, existing goals, targets, lists, and timestamps remain. Export any
new-field data that must be retained before downgrade, and coordinate application
and schema versions: W4 code requires the new columns.
