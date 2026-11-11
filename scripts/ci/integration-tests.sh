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
source "$ROOT/scripts/ci/stack-up.sh"

printf '\n\033[1;36m== Integration tests ==\033[0m\n'
python3 -m pip install -q --disable-pip-version-check pytest 2>/dev/null \
  || python3 -m pip install -q --disable-pip-version-check --user --break-system-packages pytest
python3 -m pytest -q -p no:cacheprovider \
  tests/security/test_auth_smoke.py tests/security/test_rbac_smoke.py tests/security/test_owasp_smoke.py \
  tests/integration/test_stack_smoke.py \
  --junitxml="$OUT/pytest-integration.xml" -o junit_suite_name=integration
