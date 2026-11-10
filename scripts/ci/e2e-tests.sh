#!/usr/bin/env bash
# M10 Task 10.3: the five end-to-end journeys (tests/e2e: Cucumber features, Playwright API requests) against the
# full compose stack built from the PIPELINE'S images, as the pipeline's e2e-tests job runs them.
#   IMAGE_TAG=sha-<commit> bash scripts/ci/e2e-tests.sh      # CI only: pulls ghcr.io/<repo>/<service>:<tag>
# J5 runs with the offline embedder and an LLM stub (tests/e2e/docker-compose.e2e.yml), so no API key is needed.
# CI only, on purpose: on a developer machine it would re-create the assistant with the stub and re-embed the local
# knowledge base with the offline embedder, replacing the real vectors. Locally, run the journeys against your own
# stack and your real LLM instead: cd tests/e2e && npm ci && npm test
# Reports: reports/e2e/cucumber-report.html (HTML), reports/junit/e2e-cucumber.xml (JUnit).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
if [ "${CI:-}" != "true" ]; then
  echo "scripts/ci/e2e-tests.sh runs in the pipeline only (it would replace your local knowledge base)." >&2
  echo "Locally: cd tests/e2e && npm ci && npm test   (against your running stack)" >&2
  exit 2
fi
mkdir -p reports/junit reports/e2e

printf '\n\033[1;36m== TLS for the LLM stub (throwaway, git-ignored) ==\033[0m\n'
export E2E_TLS_DIR="$ROOT/reports/e2e/tls"
bash tests/e2e/llm-stub/make-tls.sh "$E2E_TLS_DIR"
export COMPOSE_FILE="docker-compose.yml:tests/e2e/docker-compose.e2e.yml"

source "$ROOT/scripts/ci/stack-up.sh"

printf '\n\033[1;36m== Knowledge base (offline embedder) ==\033[0m\n'
docker compose --profile ingest run --rm knowledge-ingest
for i in $(seq 1 30); do
  curl -fsS -o /dev/null http://localhost:8001/health/ready 2>/dev/null && { echo "  assistant ready"; break; }
  [ "$i" = 30 ] && { echo "  assistant NOT ready:" >&2; curl -sS http://localhost:8001/health/ready >&2 || true; exit 1; }
  sleep 2
done

printf '\n\033[1;36m== E2E journeys J1-J5 ==\033[0m\n'
cd tests/e2e
npm ci --no-audit --no-fund
npm test
