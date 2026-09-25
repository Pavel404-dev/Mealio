# Mealio Frontend

Flutter mobile application for Mealio.

The frontend is part of the Mealio monorepo and communicates with the FastAPI backend located in the `backend/` directory.

## Requirements

- Flutter stable
- Dart stable
- Android Studio
- Android SDK
- Android Emulator or physical Android device

Initial development environment:

```text
Flutter 3.44.8
Dart 3.12.2
```

## Install dependencies

```bash
cd frontend
flutter pub get
```

## API configuration

- The backend origin is supplied through `API_BASE_URL`.
- `AppConfig` adds the `/api/v1` prefix centrally.
- Feature repositories use paths relative to that prefix, for example `/auth/register`, `/auth/login` and `/auth/me`.

### Android Emulator

```bash
flutter run \
  --dart-define=API_BASE_URL=http://10.0.2.2:8000
```

### Physical Android device

Forward the backend port through USB:

```bash
adb reverse tcp:8000 tcp:8000
```

Run the application:

```bash
flutter run \
  --dart-define=API_BASE_URL=http://127.0.0.1:8000
```

To run on a specific device:

```bash
flutter devices

flutter run -d <device-id> \
  --dart-define=API_BASE_URL=http://127.0.0.1:8000
```

## Authentication

Mealio supports registration, authenticated sessions with access/refresh tokens,
automatic access-token refresh, backend logout, email verification, and password
reset.

```text
App start
    ↓
restore access + refresh token pair
    ↓
GET /auth/me
    ├── valid/refreshable session → Home
    └── no/invalid session → Login

Register
    ↓
POST /auth/register
    ↓
backend starts initial verification email delivery
    ↓
Verify Email
    ├── follow the verification link
    ├── resend link email if needed
    ├── explicitly request + confirm a six-digit OTP
    └── Continue to Login

Login
    ↓
POST /auth/login
    ↓
save access + refresh token pair
    ↓
GET /auth/me
    ↓
Home

Protected request → 401
    ↓
POST /auth/refresh
    ↓
rotate refresh token pair
    ↓
retry original request once

Logout
    ↓
clear local token pair
    ↓
POST /auth/logout (best effort)
    ↓
Login
```

Email verification:

```text
Link:
    /verify-email?token=<opaque-token>
        ↓
    POST /auth/email-verification/confirm

OTP (only after an explicit user action):
    POST /auth/email-verification/otp/request
        ↓
    enter a six-digit ASCII code
        ↓
    POST /auth/email-verification/otp/confirm

Either confirmation method:
    204 No Content
        ├── logged out → verified success → Login
        └── logged in → reload /auth/me → verified success → Home
```

Password reset:

```text
Login → Forgot password
    ↓
POST /auth/password-reset/request
    ↓
generic 202 Accepted success
    ↓
/reset-password?token=<opaque-token>
    ↓
enter + confirm a new 15–128 character password
    ↓
POST /auth/password-reset/confirm
    ↓
204 No Content
    ↓
clear the local authenticated session when present
    ↓
Login with the new password
```

Authentication details:

- `POST /auth/register` creates a user and returns `UserRead`; it does not create a session or return authentication tokens.
- Registration validates email, optional full name, a 15–128 character password, and password confirmation before sending the request.
- The backend automatically initiates the first verification email after successful registration; the frontend does not immediately resend it.
- Link and OTP confirmation are supported alternatives on the same Verify Email screen.
- OTP delivery is requested only after an explicit user action; opening or rebuilding the screen and restoring a session never request a code.
- `GET /auth/me` and `UserRead.email_verified` are the source of truth for persistent verification state.
- `POST /auth/email-verification/request` is used only for manual resend and keeps enumeration-resistant backend semantics.
- `POST /auth/email-verification/confirm` accepts the opaque verification token and does not require an authenticated session.
- `POST /auth/email-verification/otp/request` preserves the backend's enumeration-resistant response semantics and does not use a frontend cooldown.
- `POST /auth/email-verification/otp/confirm` sends the email and six-digit code as strings, preserving leading zeroes.
- The `/verify-email` and `/reset-password` routes are public, including while session restoration is in progress.
- Verification tokens, OTP codes, and password-reset tokens are not persisted in secure storage or preferences. OTP values never enter route URLs.
- `POST /auth/password-reset/request` uses the backend's generic enumeration-resistant success semantics.
- `POST /auth/password-reset/confirm` accepts an opaque token and a 15–128 character password; the frontend preserves the password exactly as entered.
- A successful password reset does not auto-login. If a Mealio session is active, the frontend clears it because the backend revokes refresh sessions during reset.
- `POST /auth/login` returns an access/refresh token pair.
- `GET /auth/me` restores and synchronizes the current authenticated user.
- Access and refresh tokens are stored with `flutter_secure_storage`.
- A Dio interceptor adds bearer authentication only to protected requests.
- A failed protected request can trigger one serialized refresh-token rotation and retry.
- Public auth endpoints do not trigger automatic refresh.
- Logout clears local credentials first and sends backend session revocation as a best-effort request.
- Passwords are never stored by the frontend.

### Production link deployment follow-up

Flutter routing for verification and password-reset tokens is implemented independently
from platform domain association. Production Android App Links still require a real
HTTPS domain, Android signing information, `/.well-known/assetlinks.json`, an
Android intent filter, and matching backend `EMAIL_VERIFICATION_URL_BASE` and
`PASSWORD_RESET_URL_BASE` configuration. iOS Universal Links can be configured
separately when iOS deployment becomes a priority.

Not implemented yet:

- production Android App Links domain association;
- iOS Universal Links deployment configuration;
- social login.

## Quality checks

```bash
dart format .
dart format --output=none --set-exit-if-changed .
flutter analyze
flutter test
```

## Debug APK

For an internal APK targeting the staging backend, use the manual
[Android staging QA workflow and installation guide](../docs/android-staging-qa.md).
It includes source commit and checksum verification and debug-signing limitations.

```bash
flutter build apk --debug \
  --dart-define=API_BASE_URL=http://10.0.2.2:8000
```

The generated APK is located at:

```text
build/app/outputs/flutter-apk/app-debug.apk
```

## Project structure

```text
lib/
├── main.dart
├── app/
│   ├── app.dart
│   ├── router/
│   └── theme/
├── core/
│   ├── auth/
│   ├── config/
│   ├── network/
│   │   ├── api_client.dart
│   │   ├── auth_interceptor.dart
│   │   ├── dio_provider.dart
│   │   └── token_refresh_coordinator.dart
│   └── storage/
└── features/
    ├── splash/
    ├── auth/
    │   ├── data/
    │   ├── domain/
    │   └── presentation/
    └── home/
```

## Current scope

The frontend contains:

- Material 3 theme;
- Riverpod dependency providers and one global authentication state source;
- GoRouter navigation with protected routes and public email-verification and password-reset routes;
- Dio bearer authentication with serialized automatic token refresh;
- secure access/refresh-token storage;
- session restoration;
- registration and login flows;
- backend logout integration;
- link and OTP email-verification request and confirmation UX;
- password-reset request and confirmation UX;
- authenticated Home dashboard;
- widget, navigation, controller, repository, storage, and interceptor tests.

## Out of scope

This frontend authentication scope does not implement:

- production Android App Links domain association;
- iOS Universal Links deployment configuration;
- social login;
- pantry integration;
- AI recipe generation frontend;
- meal plans;
- shopping lists;
- nutrition analytics;
- premium design, animations, or mascot.

## Localization

English, Russian, Ukrainian and Slovak are generated from `lib/l10n/app_*.arb`
by Flutter `gen_l10n`. Running `flutter pub get` generates ignored Dart files in
`lib/l10n/generated`; do not edit those files manually.

The app chooses the first supported language in the system preference list
(regional variants match by language), with English as the fallback. The language
menu on Login and in the Home AppBar applies an override immediately. “System
language” removes it and resumes following system changes. The override uses
its own secure-storage key, `mealio_locale_override`, independent of token
storage and logout. Read failures fall back to system selection; write failures
keep the current selection for the session and show a localized notification.
Writes are serialized and a delayed restore cannot overwrite a newer choice.

Language does not determine country, currency, units or time zone. Pantry
quantities remain grams, date-only displays retain ISO dates, and server ingredient
names/categories remain unchanged. Repository failure messages stay compatible;
presentation maps typed failures and pantry operation context to localized text.

When adding UI text:

1. Add a meaningful key in every ARB (en, ru, uk, sk).
2. Declare matching typed placeholders in each catalog. Use ICU plurals for
   counts, and pass opaque server/user strings as values rather than keys.
3. Resolve text during widget build; retain state or typed failures rather than
   storing translated strings.
4. Run the catalog check, generation and affected tests:

```bash
dart run tool/check_l10n.dart
flutter gen-l10n
flutter test test/core/localization
```

The frontend CI runs the catalog check and generation before analysis/tests.
The check rejects missing/extra/empty translations, inconsistent placeholder
contracts and malformed ICU structures; `gen_l10n` validates generator syntax.
