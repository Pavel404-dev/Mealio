# Personal nutrition estimates (W5, v0.3)

`mealio-nutrition-v1` is a fixed, deterministic product rule set. It estimates
personal energy and macronutrient targets from the existing W4 nutrition profile.
It does not calculate recipe nutrients or apply/save recommendations. Changes to
any coefficient, support policy, or rounding policy require a new rules version.
There are no environment coefficients, provider calls, clocks, randomness,
history, retries, background jobs, or caches in the calculator.

## API and ownership

Authenticated `POST /api/v1/user-preferences/nutrition/calculate`:

```json
{"calculation_date": "2026-10-04", "rules_version": "mealio-nutrition-v1"}
```

`calculation_date` is required, strictly ISO `YYYY-MM-DD`. Timestamps, epochs,
booleans, null, malformed dates, and surrounding whitespace are rejected. There
is no default date or restriction based on today's date. Omitted `rules_version`
defaults to exactly `mealio-nutrition-v1`; null, unknown versions, and invalid
types return 422 with no fallback. Extra fields are forbidden, including `id`,
`user_id`, `profile`, `age`, and any profile/target overrides. Unauthenticated
requests return 401. Expected domain outcomes all return HTTP 200.

The service reads only the authenticated user's profile through the existing
repository, once, and copies the six relevant values into an immutable snapshot.
No extra locks are taken. A concurrent PATCH may affect a later request, but one
calculation never combines values from separate reads. Authentication uses its
existing owner lookup. No INSERT/UPDATE/DELETE, flush, commit, recommendation
persistence, or metadata persistence is performed. Autoflush is suppressed around
the profile read, including for internal callers with pending session changes.

The existing GET/PATCH and W4 validation/storage limits remain unchanged. GET
still returns defaults without creating a row. An absent calculation profile
uses the existing `goal=maintain` default and null demographic inputs. All manual
`daily_*` targets, preferences, row counts, and timestamps remain unchanged.
Manual targets and `diet_type` do not affect the estimate. Progress/gaps, pantry
personalization, recipe nutrient calculations and AI context still use their
existing inputs; no consumer automatically adopts these estimates.

## Inputs, validation, and support

Only `sex`, `birth_date`, `height_cm`, `weight_kg`, `activity_level`, and `goal`
participate. Missing/null fields produce `incomplete_profile` before support
checks. `missing_fields` uses exactly that field order, restricted to missing
fields. No numeric result is included (`result: null`).

Internal inputs are frozen typed models with forbidden extra fields and
revalidation at calculator entry. They accept native `date` and finite `Decimal`
measurements, not implicit string/float/boolean conversions. Height has at most
one fractional digit, weight at most two, including trailing zeroes; enums match
W4. Invalid types, nonfinite numbers, and excess precision raise validation errors
even without an HTTP boundary. Internal input validation never inherits W4's
clock-dependent write validator. Well-typed out-of-envelope values instead
produce `unsupported_profile`.

Age is completed years on `calculation_date`, with month/day comparison. The
birthday increments age on that date. For February 29 births in a non-leap year,
the increment is on March 1 (including 2100). Historical and future calculation
dates use exactly the same rules; a birth date after the calculation date is
unsupported. Age is never stored.

Support checks return **the first failing reason**, in this fixed order:

| Reason code | Check |
|---|---|
| `birth_date_after_calculation_date` | Birth date must not be later than calculation date. |
| `age_out_of_range` | 19–78 completed years, inclusive. |
| `height_out_of_range` | 130.0–230.0 cm, inclusive. |
| `weight_out_of_range` | 35.00–250.00 kg, inclusive. |
| `bmi_out_of_range` | 18.5 ≤ BMI < 40, where BMI = kg / (cm / 100)². |
| `nonpositive_energy` | REE and TDEE must be positive. |
| `calories_out_of_range` | Both raw and rounded calorie target must be 1000–6000 kcal/day, inclusive. |

Checks precede rounding and never clamp a value. BMI uses exact cross-products:
`18.5 × height_cm² ≤ weight_kg × 10000 < 40 × height_cm²`; division cannot shift
a boundary. The bounded input scales keep these products exact at precision 28.
At 250 kg, even 230 cm exceeds the BMI envelope, so that weight boundary cannot
yield a successful example. The weight check itself is inclusive.

Examples of failure bodies:

```json
{
  "rules_version": "mealio-nutrition-v1",
  "calculation_date": "2026-10-04",
  "status": "incomplete_profile",
  "missing_fields": ["weight_kg"],
  "result": null
}
```

```json
{
  "rules_version": "mealio-nutrition-v1",
  "calculation_date": "2026-10-04",
  "status": "unsupported_profile",
  "reason_codes": ["bmi_out_of_range"],
  "result": null
}
```

These outcomes contain no partial targets or arbitrary input/exception echoes.
`status` is the OpenAPI union discriminator. Programming/arithmetic invariant
failures raise `NutritionCalculationInvariantError`; unexpected validation or
database errors propagate through the normal error path (HTTP 500), rather than
being disguised as a supported domain outcome. They perform no writes.

## Fixed v1 math and rounding

All coefficients are constructed from decimal strings. Each calculation creates
a local Decimal context with precision 28, `ROUND_HALF_UP`, `Emin=-999999`,
`Emax=999999`, `capitals=1`, `clamp=0`, and cleared flags. Traps are enabled for
`InvalidOperation`, `DivisionByZero`, `Overflow`, and `FloatOperation`; all other
traps are disabled. Neither the caller's context nor `DefaultContext` changes
these settings. The caller's precision, rounding, flags, and traps are preserved.

Simplified Mifflin–St Jeor resting energy expenditure, in kcal/day:

```text
REE = 10 × weight_kg + 6.25 × height_cm − 5 × age_years + offset
offset: male = 5; female = −161
TDEE = REE × activity_factor
raw_calories = TDEE × goal_factor
```

| W4 activity_level | activity_factor |
|---|---|
| sedentary | 1.40 |
| lightly_active | 1.60 |
| moderately_active | 1.80 |
| very_active | 2.00 |
| extra_active | 2.20 |

| W4 goal | goal_factor |
|---|---|
| lose_weight | 0.90 |
| maintain | 1.00 |
| gain_weight | 1.10 |

Every `round` below is integer `ROUND_HALF_UP`, in this exact order:

```text
C = round(raw_calories)
P = round(C × 0.20 / 4)
F = round(C × 0.30 / 9)
carb_energy = C − 4P − 9F
Carbs = round(carb_energy / 4)
macro_energy = 4P + 9F + 4Carbs
energy_delta = macro_energy − C
```

All four targets must be positive, and `abs(energy_delta) <= 2` kcal. The calorie
target is never adjusted to force equality. REE/TDEE are not rounded before
downstream multiplication; only after all targets are computed are their display
values rounded to 0.01 kcal. Displayed values may therefore be insufficient to
reproduce the last rounding decision: use the supplied inputs and formulas.

The minimum REE within the envelope is at least 611.5 kcal/day (female, age 78,
130 cm, 35 kg); therefore the nonpositive-energy guard is defensive in v1.
After the raw bound check, integer rounding cannot cross the integer limits.
Positive macros and the discrepancy bound follow from the preset and calorie
range; their explicit guard detects implementation defects. Tests do not alter
the production coefficients to manufacture unreachable profile outcomes.

## Successful response and reproducible examples

```json
{
  "rules_version": "mealio-nutrition-v1",
  "calculation_date": "2026-10-04",
  "status": "calculated",
  "result": {
    "age_years": 30,
    "used_inputs": {
      "sex": "male",
      "birth_date": "1996-10-04",
      "height_cm": "180.0",
      "weight_kg": "80.00",
      "activity_level": "moderately_active",
      "goal": "maintain"
    },
    "activity_factor": "1.80",
    "goal_factor": "1.00",
    "ree_kcal": "1780.00",
    "tdee_kcal": "3204.00",
    "calories_target_kcal": 3204,
    "protein_target_g": 160,
    "fat_target_g": 107,
    "carbs_target_g": 400,
    "energy_delta_kcal": -1
  }
}
```

Decimal measurements, factors, REE and TDEE are **JSON strings**; age, calorie
target, gram targets and discrepancy are JSON integers. Targets are daily values:
calories in kcal/day, macros in g/day, discrepancy in kcal/day. `used_inputs`
contains exactly the six formula inputs, with no identifiers or irrelevant
preferences. Result fields are separate estimates, not saved `daily_*` fields.

All rows below use birth date 1996-10-04 and calculation date 2026-10-04:

| sex / cm / kg / activity / goal | REE | TDEE | raw calories | C / P / F / Carbs | macro energy / delta |
|---|---:|---:|---:|---|---|
| male / 180.0 / 80.00 / moderately_active / maintain | 1780 | 3204 | 3204 | 3204 / 160 / 107 / 400 | 3203 / −1 |
| female / 165.0 / 60.00 / sedentary / lose_weight | 1320.25 | 1848.35 | 1663.515 | 1664 / 83 / 55 / 209 | 1663 / −1 |
| male / 180.0 / 80.00 / moderately_active / gain_weight | 1780 | 3204 | 3524.4 | 3524 / 176 / 117 / 442 | 3525 / +1 |

## Evidence, product choices, and applicability

- [Mifflin et al. (1990)](https://pubmed.ncbi.nlm.nih.gov/2305711/?format=pubmed)
  studied 498 healthy participants aged 19–78 and reports the simplified REE
  equations used here. This is an estimate of resting energy expenditure, not a
  measured BMR. Those study ages do not validate every supported individual.
- [FAO/WHO/UNU adult energy requirements](https://www.fao.org/4/y5686e/y5686e07.htm)
  describes PAL in relation to BMR and broad lifestyle ranges. Mealio's exact
  mapping to five W4 enums and multiplying estimated REE are product
  approximations, not a FAO-validated composite algorithm.
- [National Academies AMDR description](https://www.ncbi.nlm.nih.gov/books/NBK610333/?report=reader)
  lists adult protein 10–35%, fat 20–35%, carbohydrate 45–65%. Mealio chooses
  20% protein, 30% fat and the carbohydrate remainder as a general preset within
  those ranges, with integer-gram rounding. This is not clinical/sports
  optimization; no g/kg formula, diet-specific preset, or macro cap is implied.
- [FAO section 3.5.1](https://www.fao.org/4/y5022e/y5022e04.htm) documents general
  Atwater factors: 4/9/4 kcal per gram of protein/fat/carbohydrate.
- [NIDDK Body Weight Planner](https://www.niddk.nih.gov/bwp) supplies context for
  the 1000 kcal/day guard and applicability limitations. This floor does not mean
  1000 kcal is appropriate for every person. NIDDK does not validate Mealio's
  ±10% goal defaults, technical 6000 kcal ceiling, or supported input envelope.

Height/weight/BMI limits and calorie/goal policies are explicit product choices,
not evidence of accuracy or safety for every supported profile. Goal factors do
not promise a rate of weight loss or gain. The existing profile cannot identify
pregnancy, lactation, disease, or other special needs; this estimate does not
account for them. No new screening facts are inferred or stored. The result is
not a clinically validated individualized meal plan.

## Verification and rollback

`test_nutrition_calculation.py` uses literal independent reference values for
both sex values, all five activities and all three goals. It covers explicit
dates, leap birthdays, support and calorie edges, half ties, invalid internal
inputs, immutable outputs, and hostile/task-local Decimal contexts without DB
fixtures. `test_nutrition_calculation_api.py` covers authentication, ownership,
response shapes, request rejection, unchanged rows/timestamps/manual targets,
SQL read-only guards, provider-call tripwires, unexpected failures, suppressed
autoflush, and concurrent reads/PATCHes on separate sessions. Existing W4
transaction, rollback, consumer, recipe nutrient, and AI context tests remain
applicable.

Use `backend/.venv` and the explicit synthetic `mealio_test` configuration in
AGENTS.md, even for pure tests because the shared conftest requires it. Obtain
separate approval before recreating that disposable database. Run focused tests,
then Ruff lint/format and the full backend suite. The existing Backend Tests CI
on PRs to `main` and pushes to `main` runs Ruff, Alembic upgrade/check, all pytest
tests with coverage, and Docker build/runtime smoke checks. No workflow changes
or migration are required. Local results, exact-SHA CI, review, merge, and Notion
status are separate delivery states; Codex review is not human approval.

Rollback removes the new calculation endpoint, service operation, calculator,
schemas, tests and documentation. Keep W4 code, tables, fields and migration
history intact. No database downgrade or data conversion is needed; no computed
recommendations were persisted.
