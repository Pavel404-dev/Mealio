#!/usr/bin/env bash
set -euo pipefail

smoke_dir=$(mktemp -d)
cleanup() {
  if [[ -s "$smoke_dir/container.cid" ]]; then
    docker rm --force --volumes "$(cat "$smoke_dir/container.cid")" >/dev/null
  fi
  rm -rf "$smoke_dir"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' HUP TERM

# Use the image's default CMD and synthetic configuration only. /health needs no DB.
docker run --detach --network none --cidfile "$smoke_dir/container.cid" \
  --env PORT=18765 \
  --env DATABASE_URL=postgresql+asyncpg://smoke:smoke@127.0.0.1:5432/smoke \
  --env JWT_SECRET_KEY=test_smoke_jwt_secret_with_more_than_32_chars \
  --env AUTH_ABUSE_PEPPER=test_smoke_auth_abuse_pepper_with_more_than_32_chars \
  "${1:-mealio-backend}" >/dev/null

docker exec --interactive "$(cat "$smoke_dir/container.cid")" python - <<'PY'
import json
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

deadline = time.monotonic() + 30
while True:
    try:
        with urlopen("http://127.0.0.1:18765/health", timeout=1) as response:
            assert response.status == 200
            assert json.load(response) == {"status": "ok", "service": "mealio-backend"}
        break
    except (URLError, TimeoutError):
        if time.monotonic() >= deadline:
            raise SystemExit("Backend /health did not become ready within 30 seconds")
        time.sleep(0.5)

argv = Path("/proc/1/cmdline").read_bytes().rstrip(b"\0").decode().split("\0")
assert Path("/proc/1/exe").resolve().name.startswith("python"), "PID 1 must be Python"
assert Path(argv[1]).name == "uvicorn", "PID 1 must run Uvicorn"
assert argv[2:] == [
    "app.main:app", "--host", "0.0.0.0", "--port", "18765", "--no-proxy-headers",
], "Uvicorn must use the synthetic PORT and expected startup arguments"
print("Docker smoke passed: GET /health, PORT=18765, Uvicorn PID 1")
PY
