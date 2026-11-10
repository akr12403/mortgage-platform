#!/usr/bin/env bash
# M9 Task 9.3: local Splunk on this computer + the stack shipping its JSON logs to it (index mortgage_dev).
#   bash scripts/splunk/local-up.sh          # first run: ~5-10 min (image download, Splunk start under emulation)
#   bash scripts/splunk/local-up.sh --down   # stop the stack and Splunk (data kept in Docker volumes)
# What it does:
#   1. creates .env.splunk-local (git-ignored, mode 600) with a random admin password and HEC token, once
#   2. starts Splunk Enterprise (free, single instance; UI http://localhost:8002, user admin)
#   3. creates index mortgage_dev, a HEC token limited to it, the dashboard and the alerts (scripts/splunk/apply.py)
#   4. starts the stack with docker-compose.splunk.yml (Fluent Bit ships the four services' logs to HEC)
#   5. proves it: one request with a known correlationId must be searchable in Splunk
# Show the local admin password when you need to log in to the UI:  grep PASSWORD .env.splunk-local
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
ENV_FILE="$ROOT/.env.splunk-local"
COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.splunk.yml --profile splunk-local)
step() { printf '\n\033[1;36m== %s ==\033[0m\n' "$*"; }
die() { printf '\033[1;31mFAIL\033[0m %s\n' "$*" >&2; exit 1; }

docker info >/dev/null 2>&1 || die "Docker is not running"
[ -f .env ] || die ".env missing: the stack needs it (see .env.example)"

if [ "${1:-}" = "--down" ]; then
  [ -f "$ENV_FILE" ] && { set -a; . "$ENV_FILE"; set +a; }
  "${COMPOSE[@]}" down
  exit 0
fi

step "1. Local credentials (.env.splunk-local, git-ignored)"
if [ ! -f "$ENV_FILE" ]; then
  echo "  Splunk Enterprise runs under the Splunk General Terms and license (https://www.splunk.com/en_us/legal/splunk-general-terms.html)."
  read -r -p "  Accept them for this local, non-production instance? [y/N] " a
  [ "$a" = y ] || die "not accepted, nothing started"
  umask 077
  python3 - "$ENV_FILE" <<'PY'
import secrets, sys, uuid
password = secrets.token_urlsafe(18) + "Aa1!"          # Splunk requires >= 8 chars; never printed
with open(sys.argv[1], "w") as f:
    f.write("# Local Splunk only (scripts/splunk/local-up.sh). Never commit; never reuse elsewhere.\n")
    f.write(f"SPLUNK_LOCAL_ADMIN_PASSWORD={password}\n")
    f.write(f"SPLUNK_HEC_TOKEN={uuid.uuid4()}\n")
    f.write("SPLUNK_HEC_HOST=splunk\nSPLUNK_HEC_PORT=8088\nSPLUNK_HEC_TLS_VERIFY=Off\nSPLUNK_INDEX=mortgage_dev\n")
PY
  echo "  created (random admin password and HEC token)"
else
  echo "  reusing the existing file"
fi
git check-ignore -q "$ENV_FILE" || die ".env.splunk-local is not git-ignored: stop"
set -a; . "$ENV_FILE"; set +a

step "2. Start Splunk (first start under emulation takes several minutes)"
[ "$(uname -m)" = arm64 ] && echo "  Apple silicon: Splunk is amd64-only. Docker Desktop > Settings > General > 'Use Rosetta' makes it much faster."
"${COMPOSE[@]}" up -d splunk
python3 scripts/splunk/apply.py --wait 900 --search '| makeresults' >/dev/null \
  || die "Splunk did not become ready (docker compose logs splunk)"
echo "  management API ready"

step "3. Index, HEC token, dashboard, alerts"
python3 scripts/splunk/apply.py --local-setup

step "4. Start the stack with log shipping"
"${COMPOSE[@]}" up -d
for i in $(seq 1 60); do
  curl -fsS -o /dev/null http://localhost:8080/actuator/health 2>/dev/null && break
  [ "$i" = 60 ] && die "mortgage-service not healthy after 5 min (docker compose logs mortgage-service)"
  sleep 5
done
echo "  stack up"

step "5. End-to-end check: request -> logs -> Splunk"
cid="splunk-check-$(python3 -c 'import uuid; print(uuid.uuid4().hex[:12])')"
curl -s -o /dev/null -H "X-Correlation-ID: $cid" http://localhost:8080/api/v1/mortgages || true
for i in $(seq 1 24); do
  if python3 scripts/splunk/apply.py --search "index=mortgage_dev correlationId=\"$cid\"" --earliest -15m > /tmp/splunk-check.$$ 2>/dev/null; then
    sed -E 's/"_raw": "[^"]{120}[^"]*"/"_raw": "…"/' /tmp/splunk-check.$$ | head -3 | cut -c1-240; rm -f /tmp/splunk-check.$$
    printf '\n\033[1;32mSplunk is receiving the logs.\033[0m\n'
    echo "  UI:        http://localhost:8002  (user admin; password: grep PASSWORD .env.splunk-local)"
    echo "  Dashboard: http://localhost:8002/en-US/app/search/mortgage_platform_overview"
    echo "  Search:    index=mortgage_dev correlationId=\"$cid\""
    exit 0
  fi
  sleep 5
done
rm -f /tmp/splunk-check.$$
die "correlationId $cid not found in Splunk after 2 min: check 'docker compose logs log-shipper' and docs/operations/observability.md#troubleshooting"
