# Computed per-100g nutrition reads (#209)

`nutrition_value.per_100g` is an additive, read-only presentation of the existing
nutrients. `calories` is kcal per 100 g; `protein_g`, `carbs_g`, and `fat_g` are
grams per 100 g. Each projected value is a Decimal JSON string with exactly two
fractional digits, rounded once at the presentation boundary with `ROUND_HALF_UP`.

```json
{
  "calories": "100.00",
  "protein_g": "2.00",
  "carbs_g": "3.00",
  "fat_g": "0.00",
  "portion_g": "50.00",
  "per_100g": {
    "calories": "200.00",
    "protein_g": "4.00",
    "carbs_g": "6.00",
    "fat_g": "0.00"
  }
}
```

The example omits the unchanged `id` and `ingredient_id` fields for brevity.
Original nutrient fields still describe the saved `portion_g`. No values, UUIDs,
portions, or saved recipe totals are rewritten to produce a read response.

## Response and input contracts

The projection is present in ingredient list, detail, create, and update
responses, and in `ingredient.nutrition_value` in Pantry list, create, and update
responses. Pantry summary remains an aggregate response, without a nested
ingredient. Missing nutrition remains `nutrition_value: null`; reads do not
create nutrition records.

OpenAPI marks `NutritionValueRead.per_100g` as required and `readOnly`. Ingredient
write schemas continue using `NutritionValueCreate`, which has no projection
field. Client-supplied `per_100g` is ignored under the existing ingredient
extra-input policy. It cannot override storage or the computed response.
No new write-only constraints are applied to source read fields, and projected
values have neither the nutrient `NUMERIC(8,2)` nor recipe-total `NUMERIC(10,2)`
limit.

Existing nested-write semantics remain:

| Input | Create | PATCH |
| --- | --- | --- |
| Omitted or null `nutrition_value` | No nutrition row | Preserve current nutrition |
| Nutrition object | Create the supplied nutrient set | Replace the entire nutrient set |
| Omitted macros inside an object | Default each to zero | Default each to zero |
| Omitted `portion_g` inside an object | Default to 100 g | Default to 100 g |

Stored numeric zero projects to `"0.00"`. A small positive value can also round
to `"0.00"`. Neither value certifies exact zero, completeness, provenance, or a
verified source. No missing-data or coverage indicators are introduced.

## Calculation and loading boundaries

The projection uses the exact rational scaling and explicit Decimal Context
helpers shared with [gram-based aggregates](nutrition-storage-consistency.md):

```
per_100g = ROUND_HALF_UP(original nutrient * 100 / original portion_g, 2 places)
```

The rational numerator/denominator determine sufficient conversion precision
before final quantization. Ambient and `DefaultContext` precision, rounding,
exponent limits, flags, and traps cannot change the result. The schema computes
from the same loaded source values it returns; there is no separate database
lookup, lazy relationship, ORM mutation, projection cache, or new lock.

| Source calories / portion | Projected kcal / 100 g | Downstream result |
| --- | --- | --- |
| 100 kcal / 50 g | `"200.00"` | 125 g: Pantry 250 kcal; recipe `"250.00"` |
| 0 kcal / 100 g | `"0.00"` | Numeric zero remains zero |
| 0.01 kcal / 999999.99 g | `"0.00"` | Source remains positive |
| 1 kcal / 200.01 g | `"0.50"` | 1 g: recipe `"0.00"`; rescaling the rounded projection would incorrectly give `"0.01"` |
| 999999.99 kcal / 0.01 g | `"9999999900.00"` | Read succeeds; existing recipe-total bounds still apply to writes |

Pantry, recipes, and AI save always calculate from original nutrients and
`portion_g`. Meal plans continue summing saved recipe totals. The #207 transaction
ownership, advisory gate, and ORM refresh behavior are unchanged. AI generated
preview and save schemas continue forbidding extra nutrient fields, including
`per_100g` at root or ingredient level; saving does not call the provider.

## Compatibility and verification

Production Flutter/UI is unchanged. The current parser ignores the additional
field and still reads the original numeric strings and portion. Domain and
repository regressions cover both new responses and legacy responses without
`per_100g`, including non-100 portions and projections above storage limits.
Application rollback removes the projection without rewriting stored data.

Pure tests cover arithmetic, Decimal contexts, serialization, OpenAPI separation,
input injection, and aggregate counterexamples. DB/API tests additionally cover
all affected responses, independent source reloads, nested defaults/replacement,
constant batch query counts, query-free serialization, aggregates, AI save, and
ownership. These tests require separately authorized database verification under
`AGENTS.md`; their presence is not evidence of a passing DB run. Full affected
suites, exact-SHA CI, API walkthrough, and review remain delivery gates.
