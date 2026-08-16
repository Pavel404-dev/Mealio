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
automatic access-token refresh, backend logout, and email verification.

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
    ├── resend if needed
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
/verify-email?token=<opaque-token>
    ↓
POST /auth/email-verification/confirm
    ↓
204 No Content
    ├── logged out → verified success → Login
    └── logged in → reload /auth/me → verified success → Home
```

Authentication details:

- `POST /auth/register` creates a user and returns `UserRead`; it does not create a session or return authentication tokens.
- Registration validates email, optional full name, a 15–128 character password, and password confirmation before sending the request.
- The backend automatically initiates the first verification email after successful registration; the frontend does not immediately resend it.
- `UserRead.email_verified` is the frontend source for persistent verification state.
- `POST /auth/email-verification/request` is used only for manual resend and keeps enumeration-resistant backend semantics.
- `POST /auth/email-verification/confirm` accepts the opaque verification token and does not require an authenticated session.
- The `/verify-email` route is public, including while session restoration is in progress.
- Verification tokens are not persisted in secure storage and are not rendered by the UI.
- `POST /auth/login` returns an access/refresh token pair.
- `GET /auth/me` restores and synchronizes the current authenticated user.
- Access and refresh tokens are stored with `flutter_secure_storage`.
- A Dio interceptor adds bearer authentication only to protected requests.
- A failed protected request can trigger one serialized refresh-token rotation and retry.
- Public auth endpoints do not trigger automatic refresh.
- Logout clears local credentials first and sends backend session revocation as a best-effort request.
- Passwords are never stored by the frontend.

### Production link deployment follow-up

Flutter routing and verification-token confirmation are implemented independently
from platform domain association. Production Android App Links still require a real
HTTPS domain, Android signing information, `/.well-known/assetlinks.json`, an
Android intent filter, and matching backend `EMAIL_VERIFICATION_URL_BASE`
configuration. iOS Universal Links can be configured separately when iOS
deployment becomes a priority.

Not implemented yet:

- Flutter password-reset UX;
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
- GoRouter navigation with protected routes and a public email-verification route;
- Dio bearer authentication with serialized automatic token refresh;
- secure access/refresh-token storage;
- session restoration;
- registration and login flows;
- backend logout integration;
- email-verification resend and confirmation UX;
- authenticated Home dashboard;
- widget, navigation, controller, repository, storage, and interceptor tests.

## Out of scope

This frontend authentication scope does not implement:

- Flutter password-reset UX;
- production Android App Links domain association;
- iOS Universal Links deployment configuration;
- social login;
- pantry integration;
- AI recipe generation frontend;
- meal plans;
- shopping lists;
- nutrition analytics;
- premium design, animations, or mascot.
