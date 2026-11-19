# AI meal plan preview

W13.1 proposes assignments for one day from the authenticated user's saved
recipes. The client chooses the date, app locale, and one to four distinct
canonical meal slots. The preview returns assignments in request order and
nutrition totals based on the saved recipes and their current serving yields.

- Given a recipe yielding four servings with 330 kcal, a model selection of one
  serving contributes 82.50 kcal to the preview.
- A provider response that selects a recipe outside the supplied candidates,
  repeats a slot, or supplies its own nutrition returns HTTP 502.
- With allergies declared, the API returns HTTP 422 before contacting the
  provider. The catalog has no verified allergen coverage for this feature.
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
nutrition or ingredient names matching the user's dislikes. A canonical recipe
meal type restricts its eligible slot. Unclassified recipes can fill any
requested slot. If an eligible candidate is missing for any slot, the request
returns 422 with no provider call. The nutrition profile's recipe labels and
targets guide selection. The API does not promise that targets or a dietary label
are clinically verified.

The model receives candidate numbers, slot options, serving yields, stored
nutrition, diet labels and counts of matching liked ingredients. It also receives
the requested date and locale, the profile goal, diet label, preferred meal count
and daily targets. Emails, UUIDs, ingredient names, recipe titles and instructions
stay on the server. Any declared allergy stops the request before generation.
The server accepts only one selection per requested slot and looks up each
candidate number in the same snapshot. Portion counts are integer hundredths
from 1 to 1200 in the model contract and decimals from 0.01 to 12 in the API.

When the request covers the preferred number of daily meals and has at least
one nutrition target, the server compares the valid model plan with a bounded
set of alternatives from the same snapshot. Per slot it tries the model's recipe
and up to one alternative, using 0.75, 1, 1.25 or 1.5 servings. It also includes
the model's original portion for its recipe. Alternatives follow any specific
diet label in the profile and are shortlisted by liked ingredient count, then
recency. The server minimizes the largest relative difference from the provided
targets, then the sum of those differences. For equally close plans it prefers
more liked ingredients, then keeps the model plan if it ties. Partial requests,
requests with no preferred meal count, and profiles with no targets use the
validated model selection. The comparison uses the same model response.

Nutrition is summed as exact fractions and rounded half up once for the day,
using the same policy as saved plans.

The preview is disabled by default. Configure `OPENAI_MEAL_PLAN_MODEL` and
provide `OPENAI_MEAL_PLAN_API_KEY`. If the dedicated key is omitted, the
provider uses `OPENAI_API_KEY`. Set `OPENAI_MEAL_PLAN_REASONING_EFFORT` only to
a value supported by the configured model. Staging uses `gpt-6-luna` with
`low`.

The provider uses Structured Outputs,
`store=false`, a 1000-token output cap and the existing
`AI_REQUEST_TIMEOUT_SECONDS` as a deadline. Unavailable providers return 503
and rejected output returns 502. Logs record the configured model, elapsed time,
outcome and usage when returned. Prompts, profiles and raw provider outputs are
excluded from these logs.

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
