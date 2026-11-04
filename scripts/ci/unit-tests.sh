#!/usr/bin/env bash
# M9 Task 9.1: unit-test suites, one per CI matrix entry. Each writes JUnit XML to reports/junit/.
#   bash scripts/ci/unit-tests.sh <suite>
# Suites: mortgage-service | servicing-service | analytics-service | knowledge-assistant | ts-client | repo-checks
# Runs the same way locally (needs Docker for the two Python services, a JDK 17 + Maven for Java, Node 22 for TS).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
OUT="$ROOT/reports/junit"; mkdir -p "$OUT"
suite="${1:?usage: unit-tests.sh <suite>}"

case "$suite" in
  mortgage-service|servicing-service)
    # mvn test runs from the service folder; the event-schema contract test reads ../../docs (repo checked out).
    (cd "services/$suite" && mvn -B test)
    cp services/"$suite"/target/surefire-reports/TEST-*.xml "$OUT/" 2>/dev/null || true
    ;;
  analytics-service|knowledge-assistant)
    # The dedicated test stage of the service's own Dockerfile: exactly the runtime dependencies + dev tools.
    tag="ci/$suite-tests:local"
    docker build -f "docker/Dockerfile.$suite" --target test -t "$tag" .
    if [ "$suite" = knowledge-assistant ]; then
      # Repo mounted so the docs/runbook link checks (prompt library, incident runbooks) run too, as in the README.
      docker run --rm -v "$ROOT":/repo -w /repo/ai/mortgage-knowledge-assistant "$tag" \
        python -m pytest -q -p no:cacheprovider tests --junitxml="/repo/reports/junit/pytest-$suite.xml" -o junit_suite_name="$suite"
    else
      docker run --rm -v "$OUT":/reports "$tag" \
        python -m pytest -q -p no:cacheprovider tests --junitxml="/reports/pytest-$suite.xml" -o junit_suite_name="$suite"
    fi
    ;;
  ts-client)
    cd clients/mortgage-api-consumer
    npm ci --no-audit --no-fund
    npm run build
    node --test --test-reporter=spec --test-reporter-destination=stdout \
      --test-reporter=junit --test-reporter-destination="$OUT/node-ts-client.xml" "dist/test/**/*.test.js"
    ;;
  repo-checks)
    # Contract tests (event schemas <-> examples <-> catalog <-> producers) and the stdlib guards/unit tests.
    python3 -m pip install -q --disable-pip-version-check pytest jsonschema
    python3 -m pytest -q -p no:cacheprovider tests/contract --junitxml="$OUT/pytest-contract.xml" -o junit_suite_name=contract
    python3 -m pytest -q -p no:cacheprovider \
      tests/security/test_static_sql.py tests/security/test_iam_policies.py \
      infrastructure/aws/lambda/doc_processor/tests infrastructure/glue/tests \
      --junitxml="$OUT/pytest-repo-guards.xml" -o junit_suite_name=repo-guards
    ;;
  *) echo "unknown suite: $suite" >&2; exit 2 ;;
esac
