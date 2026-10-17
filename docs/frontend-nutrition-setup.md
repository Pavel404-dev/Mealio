# Optional nutrition setup (W6)

Issue: [#201](https://github.com/Pavel404-dev/Mealio/issues/201).

Home opens the protected `/nutrition/setup` route. Login still leads to Home;
there is no mandatory onboarding redirect or completion marker. Each visit loads
the canonical profile and starts at step 1, including after a process restart or
a new login. The indicator is the current wizard position only. The API default
`maintain` is not evidence that the user previously confirmed a goal.

## Data and saves

The three steps collect goal; sex, actual birth date, height and weight; and
activity. All four body inputs are required to save that step. Existing partial
profiles display empty fields without inferred dates or measurements. Birth date
uses explicit `YYYY-MM-DD` calendar input and the current UTC date as its upper
bound. Measurements accept comma or point and use integer-scaled validation,
preserving exact decimal strings and rejecting excess precision, including
trailing zeros. W4 bounds apply; W5 applicability limits do not restrict this UI.

Only explicit Save actions write to the existing
`/api/v1/user-preferences/nutrition` API. The repository reads six fields from the
canonical response and has no full-profile serializer. PATCH includes only
changed fields of the current step. It never sends null to represent an unedited
field, never sends unrelated profile fields, and never sends an empty PATCH.
GET alone does not create a profile. A no-change step can advance without writing.

Each successful write updates the active server profile immediately. The UI
advances only after confirmation, and saves acknowledge only the current step;
other steps retain their in-memory edits. Back revisits earlier steps. Leaving
with unsaved edits displays an inline confirmation with stay/discard actions;
system Back dismisses that confirmation. Previously saved steps are not reverted.
Conflicting navigation/edit/submit actions are disabled during saving.

Failures retain the input and position and require explicit retry. Network copy
does not promise rollback: a timed-out request may already have committed. There
are no compensating writes. Failure categories are translated at render time,
never from server detail or exception text. EN/RU/UK/SK cover the feature.

## Login lifetime and ownership

`NutritionSetupController` captures `SecureStorageService.sessionLifetime` at
construction, before loading. The route owns and disposes it. It checks lifetime,
authentication and disposal before dispatch, after awaited results and before
publishing state. The repository also checks the captured owner immediately
before invoking the configured ApiClient, without an intervening await. Existing
transport/interceptor guards retain that lifetime through asynchronous credential
preparation and refresh retry.

The screen listens to auth transitions to clear the old controller immediately
when authentication is lost. Its inner widget is keyed by the lifetime read on
auth rebuilds, not by user ID, AuthUser identity, token contents or token revision.
A new login by the same user therefore cannot reuse the draft. Ordinary user
reloads, token rotation and locale changes retain it. UI callbacks recheck
ownership before navigation or success feedback, including when a fake repository
bypasses the transport guards. No demographics are logged or persisted locally.

An already dispatched request may finish on the server with its original
credentials. The client neither undoes it nor replays it under a new login.

## Verification and delivery

Focused tests are under `frontend/test/features/nutrition/`. Domain tests cover
date/decimal/enum contracts; repository tests exercise real ApiClient paths and
safe response mappings; controller and widget tests cover partial profiles,
dirty navigation, failures, lifetime ownership and controlled late completions.
The widget suite uses the actual app/router and all four locales, including
small viewports and large text. Existing auth/recovery/pantry tests remain part
of the full frontend gate.

```sh
cd frontend
flutter test --no-pub test/features/nutrition
```

From the repository root:

```sh
bash scripts/check-frontend.sh
git diff --check
```

Local tests do not establish device/iOS checks, exact-commit CI, independent
review or post-merge Android QA. Those remain separate delivery gates. No local
backend database run is needed for this frontend-only feature.

Rollback removes the wizard and Home entry while retaining values already saved
to the existing profile. It requires no database downgrade or profile clearing.
Calculation, targets, W7 preferences and persistent drafts remain out of scope.
