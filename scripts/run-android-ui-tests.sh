#!/usr/bin/env bash
set -euo pipefail

if [[ $# != 2 ]]; then
  echo "Usage: bash scripts/run-android-ui-tests.sh APK REPORT_DIRECTORY" >&2
  exit 2
fi

apk=$(realpath "$1")
reports=$(realpath -m "$2")
cd "$(dirname "${BASH_SOURCE[0]}")/.."
mkdir -p "$reports"
git rev-parse HEAD > "$reports/SOURCE_COMMIT.txt"
sha256sum "$apk" > "$reports/SHA256SUMS"

serial=$(adb -e get-serialno)
if [[ ! "$serial" =~ ^emulator-[0-9]+$ ]]; then
  echo "Start one disposable Android emulator for this test." >&2
  exit 2
fi
device=(adb -s "$serial")

today=$(date -u +%F)
lunch_date=$(date -u -d "$today +2 days" +%F)
dinner_date=$(date -u -d "$today +3 days" +%F)
date_arguments=(
  -e "LUNCH_DATE_INPUT=$(date -u -d "$lunch_date" +%m/%d/%Y)"
  -e "LUNCH_DATE_LABEL=$(LC_ALL=C date -u -d "$lunch_date" '+%A, %B %-d, %Y')"
  -e "DINNER_DATE_INPUT=$(date -u -d "$dinner_date" +%m/%d/%Y)"
  -e "DINNER_DATE_LABEL=$(LC_ALL=C date -u -d "$dinner_date" '+%A, %B %-d, %Y')"
)

(
  cd backend
  exec python -m uvicorn tests.android_qa:create_app --factory \
    --host 127.0.0.1 --port 8120 --timeout-keep-alive 0
) > "$reports/backend.log" 2>&1 &
backend_pid=$!

cleanup() {
  local status=$?
  if (( status != 0 )); then
    "${device[@]}" exec-out screencap -p > "$reports/failure.png" || true
    "${device[@]}" reverse --list > "$reports/adb-reverse.txt" || true
    tail -n 50 "$reports/backend.log" >&2
  fi
  "${device[@]}" shell cmd connectivity airplane-mode disable >/dev/null 2>&1 || true
  "${device[@]}" reverse --remove tcp:8120 >/dev/null 2>&1 || true
  kill "$backend_pid" 2>/dev/null || true
  wait "$backend_pid" 2>/dev/null || true
}
trap cleanup EXIT

wait_for_backend() {
  for ((attempt = 0; attempt < 25; attempt++)); do
    if ! kill -0 "$backend_pid" 2>/dev/null; then
      echo "Android QA backend stopped before it was ready." >&2
      return 1
    fi
    if curl --fail --silent --max-time 2 http://127.0.0.1:8120/health/db >/dev/null; then
      return 0
    fi
    sleep 1
  done
  echo "Android QA backend did not become ready." >&2
  return 1
}

run_flow() {
  local flow=$1
  local output="$reports/$flow"
  mkdir -p "$output"
  maestro --device "$serial" test --format junit --output "$output/report.xml" \
    --debug-output "$output" --test-output-dir "$output" \
    "${date_arguments[@]}" ".maestro/$flow.yaml"
}

wait_for_backend
"${device[@]}" shell cmd connectivity airplane-mode disable
"${device[@]}" reverse tcp:8120 tcp:8120
"${device[@]}" install -r "$apk"
run_flow meal-plan-calendar

# ADB forwarding stays active in airplane mode until the runner removes it.
"${device[@]}" reverse --remove tcp:8120
run_flow meal-plan-offline

"${device[@]}" shell cmd connectivity airplane-mode disable
"${device[@]}" reverse tcp:8120 tcp:8120
wait_for_backend
run_flow meal-plan-retry
