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
    --host 127.0.0.1 --port 8120
) > "$reports/backend.log" 2>&1 &
backend_pid=$!

cleanup() {
  local status=$?
  if (( status != 0 )); then
    "${device[@]}" exec-out screencap -p > "$reports/failure.png" || true
    tail -n 50 "$reports/backend.log" >&2
  fi
  "${device[@]}" shell cmd connectivity airplane-mode disable >/dev/null 2>&1 || true
  kill "$backend_pid" 2>/dev/null || true
  wait "$backend_pid" 2>/dev/null || true
}
trap cleanup EXIT

wait_for_device_network() {
  local response
  for ((attempt = 0; attempt < 25; attempt++)); do
    if ! kill -0 "$backend_pid" 2>/dev/null; then
      echo "Android QA backend stopped before it was ready." >&2
      return 1
    fi
    if response=$(timeout 4 "${device[@]}" shell \
      'printf "GET /health/db HTTP/1.0\r\n\r\n" | toybox nc -w 2 10.0.2.2 8120' 2>/dev/null) \
      && [[ "$response" == "HTTP/1.1 200 "* ]]; then
      return 0
    fi
    sleep 1
  done
  echo "The emulator did not reach the Android QA backend." >&2
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

"${device[@]}" shell cmd connectivity airplane-mode disable
"${device[@]}" shell cmd wifi connect-network AndroidWifi open
"${device[@]}" install -r "$apk"
wait_for_device_network
run_flow meal-plan-calendar

"${device[@]}" shell cmd connectivity airplane-mode disable
wait_for_device_network
run_flow meal-plan-retry
