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

Mealio currently supports the first complete frontend-to-backend authenticated user flow:

```text
App start
    ↓
restore access token
    ├── valid token → GET /auth/me → Home
    └── no/invalid token → Login

Register
    ↓
POST /auth/register
    ↓
201 Created
    ↓
Login with registered email prefilled

Login
    ↓
POST /auth/login
    ↓
save access token
    ↓
GET /auth/me
    ↓
Home

Logout
    ↓
delete access token
    ↓
Login
```

Authentication details:

- `POST /auth/register` creates a user and returns `UserRead`; it does not create a session or return an access token.
- Registration validates email, optional full name, a 15–128 character password, and password confirmation before sending the request.
- Successful registration returns to Login, shows a success message, and prefills the normalized registered email.
- `POST /auth/login` accepts the user's email and password.
- `GET /auth/me` restores and verifies the current user.
- The access token is stored with `flutter_secure_storage` under `mealio_access_token`.
- A Dio interceptor asynchronously adds `Authorization: Bearer <token>` to authenticated requests.
- Login and registration requests do not attach an existing bearer token.
- Invalid or expired stored tokens are removed during session restoration.
- If `/auth/me` fails after a successful login token was saved, the token is removed to avoid an inconsistent session.
- Logout is local because the backend currently has no logout endpoint.
- Passwords are never stored by the frontend.

Not implemented yet:

- refresh tokens;
- automatic token refresh;
- password reset;
- email verification;
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
│   ├── config/
│   ├── network/
│   │   ├── api_client.dart
│   │   ├── auth_interceptor.dart
│   │   └── dio_provider.dart
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
- GoRouter navigation with authentication redirects;
- Dio configuration with bearer authentication;
- secure access-token storage;
- session restoration;
- real registration flow;
- real login flow;
- local logout;
- authenticated Home dashboard;
- widget, navigation, controller, repository, and interceptor tests.

## Out of scope

This authentication feature does not implement:

- refresh tokens;
- automatic token refresh;
- backend logout;
- pantry integration;
- AI recipe generation frontend;
- meal plans;
- shopping lists;
- nutrition analytics;
- premium design, animations, or mascot.
