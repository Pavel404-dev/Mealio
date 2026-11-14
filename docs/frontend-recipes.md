# Saved recipes in Flutter (W11)

The Home **Recipes** card opens the protected `/recipes` route. This slice is a
read-only list of saved recipes. Selecting a card opens protected
`/recipes/:recipeId` detail with named ingredients, grams and instructions.
The separate AI Recipe card still describes future generation. Editing,
generation and planner integration remain follow-up work. W11.1 (list) and
W11.2 (detail) have local test coverage; final-SHA CI/review and app delivery
are separate gates, not established by this document.

## Data and presentation

`RecipeRepository` uses the configured `ApiClient`, Dio and authentication
handling. `GET /api/v1/recipes?limit=50&offset=0` returns an array of `RecipeRead`,
not an envelope. Explicit **Load more** requests use the same page size and the
next offset. There are no catalog lookups or writes on the list path.

`Recipe.fromJson` reads the saved serving count, optional metadata, nullable
decimal-string totals, timestamps and ingredient references. Additional fields
are ignored; malformed responses produce a safe error rather than an empty
success. The ingredient reference contains UUIDs and `quantity_g`, not a nested
ingredient name. Detail resolves those names using exact UUID reads as described
below.

Servings and nutrition have the [W10 semantics](database/erd.md#servings-contract-w10):

- `servings` is the saved count, including the compatibility default of 1 for
  historical recipes. It does not recover their original serving counts.
- Calories, protein, carbs, fat and ingredient grams refer to the **whole
  recipe**. The client does not divide by servings or recalculate nutrition.
- A null total is displayed as **No data**; a numeric zero is displayed as 0.
  Zero does not establish complete ingredient nutrition coverage. See
  [missing data and zero values](nutrition-storage-consistency.md#missing-data-and-zero-values).
- Numbers use the selected locale with at most two fractional digits; API
  fields remain unchanged. Labels and plurals are supplied in en/ru/uk/sk.
  Recipe titles remain server/user text.

## Page state and login lifetime

`RecipeListController` follows the existing route-local nutrition controller
pattern with Riverpod dependency injection. It belongs to one route visit and
one local login lifetime. The screen watches auth transitions and keys the visit
by that lifetime. Repository and controller both check ownership before dispatch
and after async work. Logout, relogin (including the same user) and disposal
retire the visit and clear its rows/errors. Same-lifetime token rotation, current
user reload and locale changes retain the current pages.

Initial loading, empty, failure and explicit retry are separate states. During
Load more, existing rows remain visible. A failed page preserves the rows and
offset; Retry requests that page once. Pending loads reject duplicate actions;
there is no automatic retry loop. Connection, final authentication and rate-limit
failures have localized safe copy; other failures use a generic load error.
Server error bodies are never displayed.

The next offset counts received server rows, including overlapping UUIDs. The
visible list deduplicates by UUID without moving the offset backwards. A short
page ends pagination; an exactly full final page requires one additional empty
request. Offset pagination preserves the API's ordering and limitations: it is
not a consistent snapshot during concurrent insertions/deletions, and client
deduplication cannot guarantee that no rows are skipped while the collection
changes. Leaving and reopening the route starts a fresh list.

## Detail and ingredient resolution (W11.2)

Detail always fetches `GET /recipes/{id}` rather than trusting a list card or
navigation extra. Direct entry works without first visiting the list. The app
back button pops a pushed detail to the retained list; with no previous page it
returns to `/recipes`. Recipe title, optional description and multiline
instructions remain plain server/user text.

`getRecipeDetail` resolves unique ingredient UUIDs through the existing
`GET /ingredients/{id}` endpoint using the existing Ingredient parser. Four
lookups at most run concurrently, in bounded batches. The visible composition
retains the recipe's order and gram quantities. No catalog search page, name
guessing or nutrient recomputation is involved. The response recipe ID,
composition recipe IDs and each catalog response ID must match their requests.

This is an all-or-error read: detail is published after every name resolves.
Missing recipe (including foreign ownership) and unavailable ingredient have
distinct safe messages; connection, final auth, rate-limit, malformed and
unexpected failures are also handled. Empty composition is a successful detail
with an explicit empty message and the instructions. Retry rereads the recipe
and names from the beginning, so it sees the current composition instead of
mixing data from different attempts. No result cache survives route visits.

`RecipeDetailController` owns one recipe ID and login lifetime. Changing either
replaces the visit; auth loss or disposal clears data and cancels its shared
request token. The additive optional `ApiClient.get(cancelToken: ...)` passes
Dio cancellation through without changing existing callers or authentication
semantics. Each recipe/catalog dispatch checks the original lifetime and token,
including after awaits; a failed/cancelled batch cannot start another batch.
Already dispatched requests cannot be unsent. Cancelling a view does not cancel
the session's shared token refresh, but the cancelled request is not replayed.

List and detail use `RecipeNutritionSummary`, so servings, units, locale number
formatting, whole-recipe labels and null/zero semantics are identical. Detail
labels/errors exist in all four ARBs; locale change and same-lifetime auth reload
retain loaded detail without additional requests. Long names and instructions
are wrapped in a scrollable body rather than truncated into fixed-height rows.

## Behavior examples and verification

1. A four-serving recipe with totals 330 kcal / 62 g protein / 0 g carbs /
   7.20 g fat displays those whole-recipe totals and four servings. Null and
   explicit zero remain distinct.
2. `[]` shows an empty state. Timeout, malformed JSON, final 401, 429 and 5xx
   produce safe errors; explicit Retry can recover without duplicate requests.
3. With 51 recipes, Load more can show recipe 51. A failed second page preserves
   page one and retries offset 50. Late success/error from an old login lifetime
   cannot overwrite a new visit.
4. A 255-character title, status text and retry actions remain scrollable at
   320px with text scale 2 in all four languages. Changing locale retranslates
   existing states without another HTTP request.
5. Detail opened from a card rereads the latest recipe, shows exact ingredient
   names/grams and instructions, and Back preserves the list. A direct route
   works without extras and falls back to the list on app Back.
6. A recipe 404 starts no catalog lookups. A catalog 404 has its own safe error.
   Changing ID or login during either stage cancels the old visit; late success
   and errors cannot replace the new detail. Empty ingredients retain instructions.

Tests cover domain parsing, repository HTTP/JSON/error contracts, controller
pagination and ownership, widgets, the real router/repository/provider wiring
with a fake HTTP adapter, bounded/deduplicated catalog reads, cancellation during
refresh, ID changes and logout/relogin barriers. Run the focused gate from
`frontend/`:

```sh
flutter test --no-pub test/features/recipes
flutter test --no-pub test/core/network/session_isolation_test.dart
```

Run the full frontend gate from the repository root:

```sh
bash scripts/check-frontend.sh
git diff --check
```

CI/review on the final committed SHA and APK/device QA remain separate delivery
steps. No backend deployment or migration is required for this frontend slice;
after merge the owner follows the [Android staging QA workflow](android-staging-qa.md).
