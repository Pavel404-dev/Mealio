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
│   └── storage/
└── features/
    ├── splash/
    ├── auth/
    └── home/
```

## Current scope

The initial frontend contains:

- Material 3 theme;
- Riverpod dependency providers;
- GoRouter navigation;
- Dio configuration;
- secure storage infrastructure;
- Splash screen;
- Login placeholder;
- Home dashboard placeholder;
- widget tests.

## Out of scope

This PR does not implement:

- real registration or login requests;
- storage of a real JWT;
- authentication interceptors;
- refresh tokens;
- pantry integration;
- AI recipe generation;
- meal plans;
- shopping lists;
- nutrition analytics.

Real backend authentication integration is planned for the next frontend PR.
