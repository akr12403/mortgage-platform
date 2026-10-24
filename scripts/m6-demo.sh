#!/usr/bin/env bash
# M6 demo: follows the milestone's 5-step demo scenario against the running compose stack (~10 minutes).
#   bash scripts/m6-demo.sh            # run straight through
#   PAUSE=1 bash scripts/m6-demo.sh    # wait for Enter before each step (rehearsal / live demo)
#   ALL_GATES=1 bash scripts/m6-demo.sh  # step 5 runs every security gate locally (several minutes) instead of the fast ones
# Prereq: docker compose up --build -d (all healthy) and AUTH_SEED_PASSWORD in .env
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
MS=${MORTGAGE_API_BASE:-http://localhost:8080}
SS=${SERVICING_API_BASE:-http://localhost:8081}
MTG=MTG-1001

env_value() { [[ -f .env ]] && grep -E "^$1=" .env | tail -1 | cut -d= -f2- || true; }
SEED_PASSWORD="${AUTH_SEED_PASSWORD:-$(env_value AUTH_SEED_PASSWORD)}"
[[ -n "$SEED_PASSWORD" ]] || { echo "AUTH_SEED_PASSWORD is not set (export it or put it in .env)." >&2; exit 1; }

step() {
  printf '\n\033[1;36m== %s ==\033[0m\n' "$*"
  if [[ "${PAUSE:-0}" == "1" ]]; then read -r -p "   (Enter to run) " _; fi
}
say() { printf '   \033[2m%s\033[0m\n' "$*"; }

login() {  # login USERNAME -> access token on stdout (never printed by this script)
  local body
  body=$(SEED_PASSWORD="$SEED_PASSWORD" U="$1" python3 -c 'import json,os; print(json.dumps({"username":os.environ["U"],"password":os.environ["SEED_PASSWORD"]}))')
  curl -sS -X POST "$MS/api/v1/auth/login" -H 'Content-Type: application/json' -d "$body" \
    | python3 -c 'import json,sys
try: print(json.load(sys.stdin).get("accessToken",""))
except Exception: print("")'
}
claims() {  # show JWT claims (payload only; the token itself is never shown)
  python3 - "$1" <<'PY'
import base64, json, sys, datetime
p = sys.argv[1].split(".")[1]
c = json.loads(base64.urlsafe_b64decode(p + "=" * (-len(p) % 4)))
exp = datetime.datetime.fromtimestamp(c["exp"], datetime.timezone.utc).strftime("%H:%M:%S UTC")
print(f"   JWT claims: sub={c['sub']} roles={c['roles']} iss={c['iss']} exp={exp} (token itself not shown)")
PY
}

printf '\033[1mM6 Security Engineering demo\033[0m  (stack: %s, %s)\n' "$MS" "$SS"
for url in "$MS/actuator/health" "$SS/actuator/health"; do
  curl -sS -o /dev/null -w '' "$url" || { echo "Stack not reachable at $url - run: docker compose up --build -d" >&2; exit 1; }
done

# ------------------------------------------------------------------------------------------------------------------
step "1. Login as SERVICING_AGENT; GET servicing history  (2 min)"
say "POST /api/v1/auth/login -> HS256 JWT (sub, roles, iss, exp). BCrypt-hashed seed users; 1 h TTL."
printf '   GET servicing-history with NO token      -> HTTP %s\n' "$(curl -sS -o /dev/null -w '%{http_code}' "$SS/api/v1/mortgages/$MTG/servicing-history")"
TOKEN=$(login servicing@capstone.local)
[[ -n "$TOKEN" ]] || { echo "Login failed: AUTH_SEED_PASSWORD must match what mortgage-service seeded." >&2; exit 1; }
claims "$TOKEN"
TMP=$(mktemp)
code=$(curl -sS -o "$TMP" -w '%{http_code}' -H "Authorization: Bearer $TOKEN" "$SS/api/v1/mortgages/$MTG/servicing-history")
printf '   GET servicing-history with Bearer token  -> HTTP %s' "$code"
if [[ "$code" == "200" ]]; then
  python3 - "$TMP" <<'PY'
import json, sys
d = json.load(open(sys.argv[1])); ev = d["events"]
print(f", {len(ev)} event(s) for {d['mortgageExternalId']}")
for e in ev[-3:]:
    print(f"      - {e['eventType']}: {e['description']}")
PY
else
  echo; sed 's/^/      /' "$TMP"; echo
fi
rm -f "$TMP"
say "Same token works on servicing-service: one issuer (mortgage-service), every service validates sig + iss + exp."

# ------------------------------------------------------------------------------------------------------------------
step "2. Same token on a restricted POST -> 403  (2 min)"
say "POST /api/v1/mortgages is ORIGINATION-only (ADMIN, UNDERWRITER). Enforced server-side, deny-by-default."
printf '   servicing@ POST /mortgages               -> '
curl -sS -X POST "$MS/api/v1/mortgages" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"mortgageExternalId":"MTG-0001","borrowerExternalId":"BOR-001","originalAmount":1,"outstandingBalance":1,"originationDate":"2025-06-01"}' \
  -w '  (HTTP %{http_code})\n'
SUP=$(login support@capstone.local)
printf '   support@   POST underwriting-decision    -> '
curl -sS -X POST "$MS/api/v1/mortgages/$MTG/underwriting-decision" -H "Authorization: Bearer $SUP" -H 'Content-Type: application/json' \
  -d '{"decision":"APPROVED"}' -w '  (HTTP %{http_code})\n'
say "403 comes BEFORE validation (no hints about valid bodies). Matrix: docs/security/security-controls.md#rbac-matrix"

# ------------------------------------------------------------------------------------------------------------------
step "3. Run the TypeScript consumer  (2 min)"
say "clients/mortgage-api-consumer: token in memory only, Bearer on every call, 401 -> one re-login + retry, 403 never retried."
CLIENT=clients/mortgage-api-consumer
node_major=$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)
if [[ "$node_major" -ge 22 ]]; then
  (
    cd "$CLIENT"
    [[ -d node_modules ]] || npm install --silent
    MORTGAGE_API_BASE=$MS SERVICING_API_BASE=$SS MORTGAGE_API_PASSWORD="$SEED_PASSWORD" npm run --silent demo
  )
else
  say "(no Node 22 on this machine: running it in node:22-alpine)"
  docker run --rm -v "$ROOT/$CLIENT":/app -w /app \
    -e MORTGAGE_API_BASE=http://host.docker.internal:8080 -e SERVICING_API_BASE=http://host.docker.internal:8081 \
    -e MORTGAGE_API_PASSWORD="$SEED_PASSWORD" node:22-alpine sh -c "npm install --silent && npm run --silent demo"
fi

# ------------------------------------------------------------------------------------------------------------------
step "4. Walk one STRIDE threat and its mitigation  (3 min)"
say "Open docs/security/threat-model.md -> 'Walk-through for the demo: T-06' (and Diagram 3, payment post)."
sed -n '/^## Walk-through for the demo/,/^## Sign-off/p' docs/security/threat-model.md | sed '$d' | sed 's/^/   /'
say "Evidence: MassAssignmentRegressionTest + tests/security/test_owasp_smoke.py::test_payment_body_cannot_choose_the_payment_id"

# ------------------------------------------------------------------------------------------------------------------
step "5. Show the pipeline security jobs passing  (1 min)"
say "On GitHub: PR #90 -> Checks: security-gates / secret-detection, sast, dependency-scanning all green."
say "Screenshots: docs/operations/devsecops-baseline.md#pipeline-evidence-redacted-screenshot (green run + PR #91 secret blocked)"
if [[ "${ALL_GATES:-0}" == "1" ]]; then
  sh scripts/security-gates.sh all
else
  say "Live, the same script CI runs (fast gates; ALL_GATES=1 for SAST + dependency scanning too):"
  sh scripts/security-gates.sh secrets
  sh scripts/security-gates.sh selftest
fi

printf '\n\033[1;32mDemo complete.\033[0m Evidence index: docs/operations/m6-demo-checklist.md\n'
