#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_root/frontend"

check_lockfile() {
  if ! git diff --quiet HEAD -- pubspec.lock; then
    echo 'Error: tracked frontend/pubspec.lock changed; inspect it before continuing.' >&2
    return 1
  fi
}

git ls-files --error-unmatch pubspec.lock >/dev/null || {
  echo 'Error: frontend/pubspec.lock must be tracked.' >&2
  exit 1
}
trap 'status=$?; if ! check_lockfile; then exit 1; fi; exit "$status"' EXIT
check_lockfile

flutter pub get --enforce-lockfile
check_lockfile
dart run tool/check_l10n.dart
flutter gen-l10n
dart format --output=none --set-exit-if-changed .
flutter analyze --no-pub
flutter test --no-pub
