# AI meal plan preview

W13.1 proposes assignments for one day from the authenticated user's saved
recipes. The client chooses the date, app locale, and one to four distinct
canonical meal slots. The preview returns assignments in request order and
nutrition totals based on the saved recipes and their current serving yields.

- Given a recipe yielding four servings with 330 kcal, a model selection of one
  serving contributes 82.50 kcal to the preview.
- A provider response that selects a recipe outside the supplied candidates,
  repeats a slot, or supplies its own nutrition returns HTTP 502.
- With allergies declared, the API considers recipes whose structured
  ingredients all have verified absence for every declared allergen. Missing
  eligible slots result in HTTP 422 before contacting the provider.
- A timed-out provider returns HTTP 503. The caller can retry or continue
  planning manually. Preview requests leave saved plans and recipes untouched.

The authenticated route is `POST /api/v2/meal-plans/ai/generate-preview`.
It accepts `planned_date`, `locale` (`en`, `ru`, `uk` or `sk`) and
`meal_types`. It returns `items` with `recipe_id`, `planned_date`,
`meal_type` and `planned_servings`, plus `nutrition` for the proposed day.
Saving remains an explicit v2 plan write with its normal ownership and slot
checks. A preview describes the recipe snapshot read for the request. Recipe
edits made afterwards can change saved-plan nutrition.

The service considers up to 50 recent owned recipes with stored nutrition,
ordered by creation time and ID. It excludes recipes with incomplete ingredient
nutrition or ingredient names matching the user's dislikes. For a specific
profile `diet_type`, only recipes with a matching label are eligible. Matching
ignores letter case and surrounding whitespace. A `balanced` or unset
preference accepts both labeled and unlabeled recipes. A canonical recipe meal
type restricts its eligible slot. Unclassified recipes can fill any requested
slot. If an eligible candidate is missing for any slot, the request returns
422 before the provider call. The nutrition profile's targets guide selection.
The API does not promise that targets or a dietary label are clinically verified.

The model receives candidate numbers, slot options, serving yields, stored
nutrition, diet labels and counts of matching liked ingredients. It also receives
the requested date and locale, the profile goal, diet label, preferred meal count
and daily targets. Emails, UUIDs, ingredient names, recipe titles, instructions,
declared allergies and the review evidence stay on the server.
The server accepts only one selection per requested slot and looks up each
candidate number in the same snapshot. Portion counts are integer hundredths
from 1 to 1200 in the model contract and decimals from 0.01 to 12 in the API.

When the request covers the preferred number of daily meals and has at least
one nutrition target, the server compares the valid model plan with a bounded
set of alternatives from the same snapshot. Per slot it tries the model's recipe
and up to one alternative, using 0.75, 1, 1.25 or 1.5 servings. It also includes
the model's original portion for its recipe. The search shortlists eligible
alternatives by liked ingredient count, then recency. The server minimizes the
largest relative difference from the provided targets, then the sum of those
differences. For equally close plans it prefers more liked ingredients, then
keeps the model plan if it ties. Partial requests, requests with no preferred
meal count, and profiles with no targets use the validated model selection.
The comparison uses the same model response.

Nutrition is summed as exact fractions and rounded half up once for the day,
using the same policy as saved plans.

## Verified allergen information

The preview checks the recipe's structured ingredient list against the allergies
in the saved profile. An allergen key matches the profile text after trimming
outer whitespace and applying Python `casefold()`. Each ingredient must have an
`absent` record for each key. A missing record, `present`, or `possible` excludes
the recipe. An ingredient whose name matches a declared allergy is also excluded.
The review covers the listed ingredients. Users must verify the actual products
used in cooking, including ingredients mentioned only in the instructions.

Generation and idempotent replay recheck the selected recipes' coverage before
returning a preview. The normalized allergen keys participate in the request
fingerprint and stay out of the model prompt. A catalog rename or category
change revokes all verification records for that ingredient in the same database
transaction. Catalog deletion removes the records as well.

The migration starts with an empty `ingredient_allergen_verifications` table.
Populate it through a reviewed database operation. Record `absent` only when a
traceable source supports absence, including cross-contact, for the exact
ingredient and allergen. Use `possible` for a cross-contact risk and leave the
record missing when coverage is unknown. Record a source name and a product or
report reference. Withdraw a record when its evidence ceases to apply.

Use bound parameters for the reviewed catalog identity and evidence. This
statement locks the matching ingredient during the write. Expect one returned
row. Zero rows means the ingredient identity must be checked again.

```sql
WITH reviewed AS (
    SELECT id FROM public.ingredients
    WHERE id = :ingredient_id AND name = :reviewed_name
      AND category IS NOT DISTINCT FROM :reviewed_category
    FOR UPDATE
)
INSERT INTO public.ingredient_allergen_verifications
    (ingredient_id, allergen_key, status, source_name, source_reference)
SELECT id, :allergen_key, :status, :source_name, :source_reference FROM reviewed
ON CONFLICT (ingredient_id, allergen_key) DO UPDATE SET
    status = EXCLUDED.status,
    source_name = EXCLUDED.source_name,
    source_reference = EXCLUDED.source_reference,
    verified_at = EXCLUDED.verified_at
RETURNING ingredient_id, allergen_key;
```

## Target fit (W14 first slice)

The response also includes a server-calculated `target_fit`. Its `metrics` use
the same four `total_*` keys as `nutrition`. Each metric has the profile's daily
`target` (or `null`), the returned nutrition `actual`, signed `delta`
(`actual - target`), signed `delta_percent` (`100 * delta / target`), and
`within_tolerance`. Deltas and percentages are decimal strings rounded half up
to two places. A missing target gives `null` for both deltas and the metric's
`within_tolerance`; zero actual nutrition remains a measured zero.

The accepted tolerance for this slice is **±10% inclusive**, reported as
`tolerance_percent: 10`. The comparison uses the returned nutrition totals and
the unrounded percentage. This is a product fit indicator, not a clinical
assessment or a guarantee that the bounded search can reach every goal.

Expected behavior examples:

- A complete three-meal day returning 1,800 kcal, 105 g protein, 210 g carbs and
  60 g fat against those same targets has `status: within_tolerance`, zero
  deltas and four true metric flags. Exactly ±10% is also within tolerance.
- A complete day with a 10 g carb goal and 0 g actual carbs reports `delta:
  "-10.00"`, `delta_percent: "-100.00"` and `status: outside_tolerance`, even
  when calories fit. The preview still returns HTTP 200.
- Lunch alone for a three-meal profile has `status: not_evaluated` and `reason:
  partial_day`. Daily targets and numerical deltas remain visible without
  scaling the targets to lunch; all metric flags are `null`.

A day is evaluated only when the requested slot count equals the profile's
`preferred_meals_per_day` and at least one target is set. Every set target must
fit for `within_tolerance`; otherwise the overall status is `outside_tolerance`.
For `not_evaluated`, reasons are `no_targets`, `unknown_meal_count` or
`partial_day`, in that precedence order. Evaluated responses have `reason: null`.
An absent profile uses the existing default profile. Target fit adds no model
calls, writes, migrations or changes to selection and portion fitting.

The preview is disabled by default. Configure `OPENAI_MEAL_PLAN_MODEL` and
provide `OPENAI_MEAL_PLAN_API_KEY`. If the dedicated key is omitted, the
provider uses `OPENAI_API_KEY`. Set `OPENAI_MEAL_PLAN_REASONING_EFFORT` only to
a value supported by the configured model. Staging uses `gpt-6-luna` with
`low`.

The provider uses Structured Outputs, `store=false` and a 1000-token output
cap. The preview can retry once after a connection error, an upstream HTTP 5xx
response, or a selection that omits requested meals and otherwise passes
validation. A repair call receives the original candidates and the list of
missing meal types. Its full replacement must pass the same validation. Both
attempts and their separate quota reservations share the
`AI_REQUEST_TIMEOUT_SECONDS` deadline. Provider timeouts and unavailability
return 503. Rejected model output returns 502. Each model call logs the
configured model, elapsed time, outcome and usage when returned. Prompts,
profiles and raw provider outputs are excluded from these logs.

The `cost_usd` log field estimates the cost of a GPT-6 Luna Standard request
from the reported usage. It uses uncached input, cache reads, default 30-minute
cache writes and total output tokens, including reasoning. An omitted service
tier uses Standard rates for the estimate. For example, 410 uncached input and
34 output tokens give `cost_usd=0.000058`.
[GPT-6 Luna pricing](https://developers.openai.com/api/docs/models/gpt-6-luna)

The field is `unknown` when token counts or required cache details are missing
or inconsistent, or the request falls outside the supported model, service tier
or prompt length. A prompt below the minimum cacheable length can be priced
using its input and output totals.

## Preview rate limit

Each account gets five model attempts in a 60-second window by default.
Configure the count with `AI_MEAL_PLAN_PREVIEW_RATE_LIMIT` and the window in
seconds with `AI_MEAL_PLAN_PREVIEW_RATE_WINDOW_SECONDS`. The first eligible
request starts the window.

The backend reserves an attempt in PostgreSQL after input and recipe eligibility
checks and commits each reservation before its model call. All replicas use
the same account counter. Provider failures and timeouts count as attempts.
When the quota blocks the first or second reservation, the API returns HTTP 429.
The `Retry-After` header gives the remaining seconds rounded up.

## Idempotency-Key

Send the optional `Idempotency-Key` header to retry the same preview request.
Use a fresh key for a new generation. A key contains 1 to 128 ASCII letters,
digits, periods, underscores, tildes or hyphens. The key is scoped to the
authenticated account and bound to the normalized request, profile inputs and
eligible recipe snapshot used for generation.

- One request claims the key and starts generation. A matching request while
  it is in progress returns HTTP 409 with `Retry-After: 1`.
- After a successful generation, a matching request returns the same
  validated preview for five minutes. Replay uses zero model attempts.
- A key bound to different preview inputs returns HTTP 409. The current
  allergy and recipe eligibility checks apply before a stored preview is read.

PostgreSQL stores key and input hashes, a reservation and the validated preview.
A handled generation failure releases the reservation. An interrupted generation
expires five minutes after it started. Expired records are removed on the
account's subsequent keyed requests. Account deletion also removes its records.
