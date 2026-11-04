#!/usr/bin/env bash
# M9 Task 9.1: integration tests against the full compose stack built from the PIPELINE'S images.
#   IMAGE_TAG=sha-<commit> bash scripts/ci/integration-tests.sh      # CI: pulls ghcr.io/<repo>/<service>:<tag>
#   LOCAL_IMAGES=1 bash scripts/ci/integration-tests.sh               # locally: uses the images docker compose built
# Secrets for the run are generated here (random JWT secret, DB and seed passwords), written to a git-ignored .env
# that exists only on the runner, and never printed. Tests: M6 auth/RBAC/OWASP smoke + M9 end-to-end event flow.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
OUT="$ROOT/reports/junit"; mkdir -p "$OUT"
SERVICES="mortgage-service servicing-service analytics-service knowledge-assistant"

if [ "${LOCAL_IMAGES:-0}" != "1" ]; then
  : "${IMAGE_TAG:?IMAGE_TAG (e.g. sha-<commit>) is required}"
  prefix="${IMAGE_PREFIX:-ghcr.io/${GITHUB_REPOSITORY:?}}"
  prefix="$(printf '%s' "$prefix" | tr '[:upper:]' '[:lower:]')"
  for s in $SERVICES; do
    docker pull -q "$prefix/$s:$IMAGE_TAG"
    docker tag "$prefix/$s:$IMAGE_TAG" "capstone/$s:dev"     # the names docker-compose.yml runs
  done

  # Throwaway secrets for this run only (CI). A developer's real .env is never touched locally.
  rnd() { python3 -c 'import secrets; print(secrets.token_urlsafe(int(__import__("sys").argv[1])))' "$1"; }
  cp .env.example .env
  python3 - "$(rnd 48)" "$(rnd 18)" "$(rnd 18)" <<'PY'
import re, sys
jwt, db, seed = sys.argv[1:]
text = open(".env").read()
for key, value in (("JWT_SECRET", jwt), ("POSTGRES_PASSWORD", db), ("AUTH_SEED_PASSWORD", seed)):
    text = re.sub(rf"^{key}=.*$", f"{key}={value}", text, flags=re.M)
open(".env", "w").write(text)
PY
fi
export AUTH_SEED_PASSWORD="$(grep -E '^AUTH_SEED_PASSWORD=' .env | cut -d= -f2-)"
[ -n "$AUTH_SEED_PASSWORD" ] || { echo "AUTH_SEED_PASSWORD missing in .env" >&2; exit 1; }

printf '\n\033[1;36m== Start the stack (no build: pipeline images) ==\033[0m\n'
docker compose up -d --no-build
# Wait on the services' own health endpoints (one-shot containers such as db-migrate exit by design).
for url in http://localhost:8080/actuator/health http://localhost:8081/actuator/health \
           http://localhost:8000/health http://localhost:8001/health; do
  for i in $(seq 1 60); do
    curl -fsS -o /dev/null "$url" 2>/dev/null && { echo "  healthy: $url"; break; }
    [ "$i" = 60 ] && { echo "  NOT healthy after 5 min: $url" >&2; docker compose ps; exit 1; }
    sleep 5
  done
done
docker compose ps --format 'table {{.Name}}\t{{.Image}}\t{{.Status}}'

printf '\n\033[1;36m== Integration tests ==\033[0m\n'
python3 -m pip install -q --disable-pip-version-check pytest 2>/dev/null \
  || python3 -m pip install -q --disable-pip-version-check --user --break-system-packages pytest
python3 -m pytest -q -p no:cacheprovider \
  tests/security/test_auth_smoke.py tests/security/test_rbac_smoke.py tests/security/test_owasp_smoke.py \
  tests/integration/test_stack_smoke.py \
  --junitxml="$OUT/pytest-integration.xml" -o junit_suite_name=integration
