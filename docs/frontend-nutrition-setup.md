# Optional nutrition setup (W6 + W7)

Issues: [#201](https://github.com/Pavel404-dev/Mealio/issues/201),
[#203](https://github.com/Pavel404-dev/Mealio/issues/203).

Home opens the existing protected `/nutrition/setup` route. Login still leads to
Home; there is no mandatory onboarding redirect, completion flag, separate W7
profile, stored age, target weight/pace or persistent draft. Each route visit
loads the canonical profile and starts at step 1, including after restart or a
new login of the same user. The progress indicator is only the current position.

## Six steps and explicit saves

1. Goal (`maintain` is the API default, not evidence of prior confirmation).
2. Sex, actual birth date, height, weight. All four inputs are required for this
   step. Existing partial values remain empty; none are inferred.
3. Activity.
4. Free-text diet, allergies, liked and disliked ingredients.
5. Maximum total minutes per dish and optional seven-day food budget per person.
6. Summary, read-only estimate, and explicit target choice.

`NutritionProfile` reads the six formula inputs, typed `NutritionPreferences`,
and `NutritionTargets` (including partial legacy targets). `NutritionPatch`
provides operation-specific formula, food, practical and targets serializers;
it cannot write a full profile. `NutritionChange<T>` distinguishes an omitted
member from explicit null. Lists stay lists, cooking time stays an integer,
and amounts stay decimal strings. Preference data and wire values are never
translated or changed by locale.

Body measurements retain W4 integer-scaled validation and UTC birth-date rules;
W5's narrower support envelope is not a storage validator. Money accepts comma
or point, 0.01–1000000.00 with at most two fractional digits, including trailing
zeros. Validation and equality use integer cents, never double or rounding.
Currency accepts exactly three ASCII letters, uppercases them and does no
registry lookup or conversion. Cooking time accepts a whole number 1–480.
Diet remains nullable free text up to 100 Unicode characters. Existing custom
diet/currency and full lists are preserved. List controls edit individual entries
without delimiter splitting, truncation, deduplication, translation or removal
of overlaps; likes do not override allergy/dislike exclusions.

Save sends only changed members of the current step. Budget edits always send
both amount and currency; the pair can be deliberately cleared together. Diet
and cooking time can also be deliberately cleared. Unedited nullable members
are omitted. No-change navigation sends no PATCH. Meals-per-day and targets
are never included in preference or formula writes.

Each successful PATCH immediately saves that step on the server. Its response
acknowledges only that step; dirty input and comparison baselines of other steps
survive. Back retains current-visit edits. Exit with unsaved edits offers
stay/discard; saved steps are not undone. Failures retain input and position
and allow an explicit retry. Timeout may have committed; there are no
compensating writes. Saving blocks duplicate submissions and conflicting
navigation/edits. Errors use localized categories, never backend detail.

## Estimate and target adoption

Summary shows existing saved daily targets separately from an estimate. The
Calculate action calls only W5 `POST /user-preferences/nutrition/calculate`, with
an explicit UTC date-only `calculation_date` and `mealio-nutrition-v1`. Dart does
not reproduce the formula or call AI. Calculate/retry/GET/Back/locale changes
never apply targets.

Outcomes are typed as calculated, incomplete or unsupported. Missing fields and
all known reason codes have EN/RU/UK/SK labels. Unknown/malformed outcomes,
mismatching metadata, missing likes (old server) and invalid typed responses
produce a safe failure with explicit retry. No placeholder zeroes or fallback
estimates are shown. Calculated `used_inputs` must match this visit's formula
inputs numerically before adoption is available; a mismatch is a safe failure.
Exit remains available, including for unsupported age-18 W4 profiles, without
claiming successful target calculation. The user can go Back to edit inputs.

Any formula-input edit invalidates the estimate and replacement selection.
Changed formula inputs must be saved before calculating. Every calculation is
bound to an input/request generation: older successes and failures cannot
replace a newer generation in the same lifetime. Back during a pending
calculation invalidates that request. Preference edits do not change the formula.

Existing targets, including a partial legacy set, are preserved by default.
Keep targets sends no mutation and does not fill missing targets. Replacing them
requires selecting the displayed estimate and pressing its explicit confirmation
button. With no saved targets the button explicitly confirms and saves the
shown estimate. Apply sends exactly four integer `daily_*` fields in one PATCH;
it never recalculates or applies unseen numbers. A failed apply retains the shown
snapshot for explicit retry.

The owner-serialized last-write-wins contract remains. Calculate and apply are
separate operations: another device can change inputs or targets between them,
and confirmation can overwrite intervening target writes. There are no
revisions, ETags or atomic apply endpoint. GET/recalculation cannot close this
race. The user confirms a shown snapshot, not optimistic concurrency protection.

## Login lifetime and ownership

The route-local controller captures `SecureStorageService.sessionLifetime`
before loading. It checks authentication, lifetime and disposal before dispatch,
after awaits and before publication. Repository checks occur immediately before
the synchronous ApiClient invocation/lifetime capture, with no intermediate await.
Transport/interceptor guards preserve the original lifetime through credential
preparation and refresh retry.

The screen clears its controller on auth loss and keys each wizard by lifetime,
not user ID, token contents or AuthUser identity. A→B and A→A clear drafts,
estimates, selection, errors and pending effects. Same-lifetime refresh and
locale changes retain them. UI callbacks check ownership before navigation or
toast. An already dispatched request may commit for the previous owner; it must
not replay or publish under a new login. No compensation writes are issued.

## Rollout, rollback and verification

Deploy backend plus additive likes migration before this frontend. The new
reader requires `liked_ingredients`; an old server is a safe compatibility
failure, never interpreted as a persisted empty list. The W6 reader ignores the
additional response field. Preferred application rollback restores the previous
frontend and retains the additive schema and saved data. Downgrading the likes
column loses those values; see [nutrition profile](nutrition-profile.md).

Focused tests under `frontend/test/features/nutrition/` cover domain and exact
wire contracts, null/omitted/list/Decimal semantics, all outcome types, partial
saves, no-change, draft navigation, explicit keep/apply, retry and controlled
same-lifetime/lifetime barriers. Widget tests use the actual app/router, all four
locales, small screens and large text. Transport tests exercise credential
preparation, stale responses and no replay. Existing auth/recovery/pantry suites
remain part of the full frontend gate.

```sh
cd frontend
flutter test --no-pub test/features/nutrition
cd ..
bash scripts/check-frontend.sh
git diff --check
```

Backend fixture/migration runs require new explicit authorization for the local
`mealio_test` database: they recreate tables/schema and migration tests remove
likes on downgrade. Local results, exact-SHA CI, independent human review and
physical Android QA are separate gates. Widget tests and an APK build do not
establish physical-device or iOS evidence. Record actual source/build/device and
scenarios before declaring delivery.
