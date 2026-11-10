#!/bin/sh
# Secure CI gates (M6 Task 6.7): ONE definition used locally, in GitHub Actions and in GitLab CI.
#
#   sh scripts/security-gates.sh secrets      # gitleaks over the full git history          -> fails on ANY finding
#   sh scripts/security-gates.sh sast         # semgrep: OWASP registry rules + project rules -> fails on ERROR
#   sh scripts/security-gates.sh sca          # trivy (Maven, npm) + pip-audit (Python)       -> fails on CRITICAL / known vuln
#   sh scripts/security-gates.sh all          # all three; exit code != 0 if any gate failed
#   sh scripts/security-gates.sh selftest     # proves the secret gate FAILS on a planted fake secret (temp repo)
#
# Each tool runs natively when installed (CI tool images); otherwise in its pinned Docker image (your laptop).
# Reports go to reports/security/ (git-ignored). Policy and merge blocking: docs/operations/devsecops-baseline.md
set -eu
set -f   # no filename globbing: patterns such as **/target are passed to the tools verbatim

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
REPORTS=reports/security
mkdir -p "$REPORTS"

# Pinned tool versions (bump deliberately; M9 moves to digest pinning)
GITLEAKS_IMAGE=${GITLEAKS_IMAGE:-zricethezav/gitleaks:v8.30.1}
SEMGREP_IMAGE=${SEMGREP_IMAGE:-semgrep/semgrep:1.178.0}
TRIVY_IMAGE=${TRIVY_IMAGE:-aquasec/trivy:0.75.0}
PYTHON_IMAGE=${PYTHON_IMAGE:-python:3.14.7-slim}
PIP_AUDIT_SPEC=${PIP_AUDIT_SPEC:-pip-audit>=2.9,<3}

# git inside containers: the mounted repo belongs to another uid ("dubious ownership"); trust it for this run only
export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0='*'

log() { printf '\n\033[1;36m== %s ==\033[0m\n' "$*"; }
pass() { printf '\033[1;32mPASS\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31mFAIL\033[0m %s\n' "$*"; }

# run_tool <binary> <image> <args...>: native binary if present, else the pinned image with the repo at /src
run_tool() {
  bin=$1 image=$2
  shift 2
  if command -v "$bin" >/dev/null 2>&1; then
    "$bin" "$@"
  elif command -v docker >/dev/null 2>&1; then
    if ! docker info >/dev/null 2>&1; then
      echo "Docker is installed but not running: start Docker Desktop and re-run." >&2
      return 125
    fi
    # Run as the calling user so reports written into the repo stay owned by you (and by the CI runner user);
    # tool caches (trivy DB, semgrep rules) persist under the git-ignored reports/.cache/.
    mkdir -p "$REPORTS/../.cache"
    m2_mount=""
    if [ "$bin" = trivy ] && [ -d "${M2_DIR:-$HOME/.m2}" ]; then m2_mount="-v ${M2_DIR:-$HOME/.m2}:/tmp/.m2:ro"; fi
    # shellcheck disable=SC2086  # $m2_mount is intentionally word-split (empty or "-v src:dst:ro")
    docker run --rm -v "$ROOT":/src -w /src --user "$(id -u):$(id -g)" $m2_mount \
      -e HOME=/tmp -e XDG_CACHE_HOME=/src/reports/.cache \
      -e GIT_CONFIG_COUNT -e GIT_CONFIG_KEY_0 -e GIT_CONFIG_VALUE_0 \
      --entrypoint "$bin" "$image" "$@"
  else
    echo "Neither '$bin' nor docker is available" >&2
    return 127
  fi
}

# ---------------------------------------------------------------------------------------------------------------
# Distinct exit codes: a finding is never confused with a scanner/runtime error (both still fail the gate).
GITLEAKS_LEAK_RC=3

gate_secrets() {
  log "Secret detection: gitleaks, full git history (any finding fails)"
  rc=0
  run_tool gitleaks "$GITLEAKS_IMAGE" git --no-banner --config .gitleaks.toml --redact --verbose \
    --report-format json --report-path "$REPORTS/gitleaks.json" --exit-code $GITLEAKS_LEAK_RC . || rc=$?
  case $rc in
    0) pass "no secrets in git history" ;;
    "$GITLEAKS_LEAK_RC") fail "secrets found (values redacted above; details in $REPORTS/gitleaks.json). Rotate first, then remove: docs/operations/runbook.md"; return 1 ;;
    *) fail "secret scan could not run (exit $rc): not a finding, but the gate fails closed"; return 1 ;;
  esac
}

gate_sast() {
  log "SAST: semgrep (OWASP Top 10 + Java/Python/TypeScript registry rules + security/semgrep/capstone-rules.yml)"
  rc=0
  run_tool semgrep "$SEMGREP_IMAGE" scan --metrics=off --disable-version-check \
    --config p/owasp-top-ten --config p/java --config p/python --config p/typescript \
    --config security/semgrep/capstone-rules.yml \
    --severity ERROR --error --json-output "$REPORTS/semgrep.json" . || rc=$?
  case $rc in
    0) pass "no ERROR-severity SAST findings" ;;
    1) fail "SAST findings at ERROR severity (listed above; JSON in $REPORTS/semgrep.json)"; return 1 ;;
    *) fail "SAST scan could not run (exit $rc): not a finding, but the gate fails closed"; return 1 ;;
  esac
}

# Trivy: report HIGH+CRITICAL, fail only on CRITICAL with a fix available (team policy, R-16).
# Exit code 5 = vulnerabilities found; any other non-zero = the scan itself failed. Both fail the gate (fail closed),
# but the message says which, so a network problem is never reported as a CVE.
TRIVY_VULN_RC=5
# Scan the manifests (pom.xml, package-lock.json), not local build output, so laptop and CI results match.
TRIVY_SKIP='--skip-dirs **/target --skip-dirs **/node_modules --skip-dirs **/dist'
MAVEN_IMAGE=${MAVEN_IMAGE:-maven:3.9-eclipse-temurin-17}
M2_DIR=${M2_DIR:-$HOME/.m2}

trivy_dir() {
  label=$1 dir=$2
  shift 2   # remaining args: extra trivy flags for this ecosystem
  run_tool trivy "$TRIVY_IMAGE" fs --quiet --scanners vuln --ignorefile .trivyignore --cache-dir reports/.cache/trivy $TRIVY_SKIP "$@" \
    --severity HIGH,CRITICAL --format table --exit-code 0 "$dir" > "$REPORTS/trivy-$label.txt" 2>&1 || true
  cat "$REPORTS/trivy-$label.txt"
  set +e
  run_tool trivy "$TRIVY_IMAGE" fs --quiet --scanners vuln --ignorefile .trivyignore --cache-dir reports/.cache/trivy $TRIVY_SKIP "$@" \
    --severity CRITICAL --ignore-unfixed --exit-code $TRIVY_VULN_RC --format table "$dir" >/dev/null 2>&1
  trivy_rc=$?
  set -e
  return $trivy_rc
}

# Trivy reads POMs from the local Maven repository instead of fetching hundreds of them from Maven Central
# (which rate-limits with HTTP 429). Maven itself resolves them first; this is a no-op when ~/.m2 is warm.
resolve_maven() {
  svc=$1
  if [ -n "${GITLAB_CI:-}" ]; then
    return 0   # GitLab: the dependency_resolve job already filled $CI_PROJECT_DIR/.m2 (see .gitlab-ci.yml)
  fi
  if command -v mvn >/dev/null 2>&1; then
    (cd "services/$svc" && mvn -B -q dependency:resolve)
  else
    mkdir -p "$M2_DIR"
    docker run --rm -v "$ROOT":/src -v "$M2_DIR":/root/.m2 -w "/src/services/$svc" "$MAVEN_IMAGE" mvn -B -q dependency:resolve
  fi
}

gate_sca_java() {
  java_rc=0
  for svc in mortgage-service servicing-service; do
    log "SCA: $svc (Maven, transitive dependencies via trivy, offline against the local Maven repository)"
    if ! resolve_maven "$svc"; then
      fail "$svc: could not resolve Maven dependencies (network or Maven Central rate limit?): scan not run"; java_rc=1; continue
    fi
    trivy_rc=0
    trivy_dir "$svc" "services/$svc" --offline-scan || trivy_rc=$?
    case $trivy_rc in
      0) pass "$svc: no fixable CRITICAL CVEs" ;;
      "$TRIVY_VULN_RC") fail "$svc: fixable CRITICAL CVE(s), see $REPORTS/trivy-$svc.txt"; java_rc=1 ;;
      *) fail "$svc: trivy scan error (exit $trivy_rc), see $REPORTS/trivy-$svc.txt: not a CVE result, but the gate fails closed"; java_rc=1 ;;
    esac
  done
  return $java_rc
}

gate_sca_npm() {
  npm_rc=0
  # The TS client and the M10 E2E suite (tests/e2e): npm lockfiles via trivy, including dev/build dependencies.
  for entry in ts-client:clients/mortgage-api-consumer e2e-tests:tests/e2e; do
    label=${entry%%:*}; dir=${entry#*:}
    log "SCA: $dir (npm lockfile via trivy, including dev/build dependencies)"
    trivy_rc=0
    trivy_dir "$label" "$dir" --include-dev-deps || trivy_rc=$?
    case $trivy_rc in
      0) pass "$label: no fixable CRITICAL CVEs" ;;
      "$TRIVY_VULN_RC") fail "$label: fixable CRITICAL CVE(s), see $REPORTS/trivy-$label.txt"; npm_rc=1 ;;
      *) fail "$label: trivy scan error (exit $trivy_rc), see $REPORTS/trivy-$label.txt"; npm_rc=1 ;;
    esac
  done
  return $npm_rc
}

# The audit runs inside a throwaway venv so it sees exactly the packages the service resolves today.
PY_AUDIT_SCRIPT='set -e
  if command -v apt-get >/dev/null 2>&1 && [ "$(id -u)" = 0 ]; then
    apt-get update -qq && apt-get install -y -qq --no-install-recommends build-essential libpq-dev >/dev/null
  fi
  python3 -m venv /tmp/audit-venv && . /tmp/audit-venv/bin/activate
  pip install -q --disable-pip-version-check -r analytics/mortgage-analytics-service/requirements-dev.txt \
    -r ai/mortgage-knowledge-assistant/requirements-dev.txt "$PIP_AUDIT_SPEC"
  status=0
  pip-audit --progress-spinner off --desc on -f columns -o "$REPORT_FILE" || status=$?
  cat "$REPORT_FILE" 2>/dev/null || true
  exit $status'

gate_sca_python() {
  log "SCA: analytics + knowledge assistant (pip-audit on the resolved runtime + dev requirements; any known vulnerability fails)"
  if [ -n "${GITLAB_CI:-}" ] || ! command -v docker >/dev/null 2>&1; then
    # GitLab: the job already runs in the pinned python image. Elsewhere (laptop, GitHub runner) use that image.
    set -- env REPORT_FILE="$ROOT/$REPORTS/pip-audit.txt" PIP_AUDIT_SPEC="$PIP_AUDIT_SPEC" sh -c "$PY_AUDIT_SCRIPT"
  else
    set -- docker run --rm -v "$ROOT":/src -w /src -e REPORT_FILE="/src/$REPORTS/pip-audit.txt" \
      -e PIP_AUDIT_SPEC="$PIP_AUDIT_SPEC" "$PYTHON_IMAGE" sh -c "$PY_AUDIT_SCRIPT"
  fi
  if "$@"; then
    pass "python: no known vulnerabilities"
  else
    fail "python: vulnerable packages (see $REPORTS/pip-audit.txt)"; return 1
  fi
}

gate_sca() {
  sca_rc=0
  gate_sca_java || sca_rc=1
  gate_sca_npm || sca_rc=1
  gate_sca_python || sca_rc=1
  return $sca_rc
}

# Proves the secret gate blocks: plant a freshly generated fake key in a throwaway repo and expect a FAIL.
gate_selftest() {
  log "Self-test: the secret gate must FAIL on a planted fake secret"
  tmp="$ROOT/$REPORTS/selftest-repo"
  rm -rf "$tmp" && mkdir -p "$tmp"
  fake=$(LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c 40)   # random, not a real credential
  ( cd "$tmp" && git init -q && git config user.email selftest@example.invalid && git config user.name selftest \
    && printf 'api_key = "%s"\n' "$fake" > leaked-config.txt && git add . && git commit -qm "planted fake secret" )
  rc=0
  (cd "$ROOT" && run_tool gitleaks "$GITLEAKS_IMAGE" git --no-banner --redact \
        --exit-code $GITLEAKS_LEAK_RC "$REPORTS/selftest-repo" >/dev/null 2>&1) || rc=$?
  rm -rf "$tmp"
  case $rc in
    "$GITLEAKS_LEAK_RC") pass "secret gate blocked the planted secret (as required by the M6 validation)" ;;
    0) fail "secret gate did NOT detect the planted secret"; return 1 ;;
    *) fail "self-test could not run (exit $rc), e.g. Docker not running"; return 1 ;;
  esac
}

# ---------------------------------------------------------------------------------------------------------------
case "${1:-all}" in
  secrets)    gate_secrets ;;
  sast)       gate_sast ;;
  sca)        gate_sca ;;
  sca-java)   gate_sca_java ;;
  sca-npm)    gate_sca_npm ;;
  sca-python) gate_sca_python ;;
  selftest)   gate_selftest ;;
  all)
    all_rc=0
    gate_secrets || all_rc=1
    gate_sast || all_rc=1
    gate_sca || all_rc=1
    log "Summary"
    if [ $all_rc -eq 0 ]; then pass "all security gates passed"; else fail "at least one security gate failed (merge must be blocked)"; fi
    exit $all_rc ;;
  *) echo "usage: $0 {secrets|sast|sca|sca-java|sca-npm|sca-python|selftest|all}" >&2; exit 2 ;;
esac
