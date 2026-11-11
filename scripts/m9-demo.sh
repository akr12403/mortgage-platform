#!/usr/bin/env bash
# M9 demo: the milestone's 5-step demo scenario (~10 minutes). Checklist: docs/operations/m9-demo-checklist.md
#   bash scripts/m9-demo.sh             # run straight through
#   PAUSE=1 bash scripts/m9-demo.sh     # wait for Enter before each step (rehearsal / live demo)
# Prereqs: bash scripts/splunk/local-up.sh (stack + local Splunk); gh logged in;
#          aws login --profile capstone-dev --region us-east-2 (step 2). Nothing is changed in AWS.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
MS=${MORTGAGE_API_BASE:-http://localhost:8080}
export MS

step() {
  printf '\n\033[1;36m== %s ==\033[0m\n' "$*"
  if [[ "${PAUSE:-0}" == "1" ]]; then read -r -p "   (Enter to run) " _; fi
}
say() { printf '   \033[2m%s\033[0m\n' "$*"; }
[[ -f .env.splunk-local ]] || { echo "run bash scripts/splunk/local-up.sh first" >&2; exit 1; }
set -a; . ./.env.splunk-local; set +a

printf '\033[1mM9 CI/CD, Terraform & Observability demo\033[0m\n'

# ----------------------------------------------------------------------------------------------------------------
step "1. Push -> pipeline green through deploy dev  (4 min)"
say "ci.yml: build -> unit tests -> secrets/SAST/SCA -> container build -> container scan -> integration -> publish"
gh run list --workflow ci --branch develop -L 3
say "Deploy: the sandbox SCP blocks GitHub OIDC, so the run ends with 'deploy-dev (run locally)' and this command:"
say "  bash scripts/deploy/deploy-dev.sh sha-<commit>   (tested images only; plan, then apply)"
say "Deployments so far: docs/operations/cicd.md#deployment-record"

# ----------------------------------------------------------------------------------------------------------------
step "2. Terraform plan artifact: dev matches the code  (2 min)"
say "5 modules, dev/test/prod identical except tfvars; S3 state with native locking; M8 resources imported."
tag="$(AWS_PROFILE=capstone-dev AWS_REGION=us-east-2 bash scripts/ci/current-image-tag.sh dev)"
say "running image: $tag"
set +e
bash scripts/terraform/tf.sh dev plan -detailed-exitcode -no-color -var "image_tag=$tag" > /tmp/m9-demo-plan.txt 2>&1
rc=$?
set -e
grep -E '^(Plan:|No changes)' /tmp/m9-demo-plan.txt || tail -5 /tmp/m9-demo-plan.txt
case $rc in 0) say "exit 0: no drift" ;; 2) say "exit 2: drift (see the drift exercise)" ;; *) say "plan failed (exit $rc)" ;; esac
rm -f /tmp/m9-demo-plan.txt

# ----------------------------------------------------------------------------------------------------------------
step "3. Splunk search by correlationId from a live API call  (2 min)"
cid="demo-$(python3 -c 'import uuid; print(uuid.uuid4().hex[:12])')"
SEED="$(grep -E '^AUTH_SEED_PASSWORD=' .env | cut -d= -f2-)"
code=$(CID="$cid" SEED="$SEED" python3 - <<'PY'
import json, os, urllib.request, urllib.error
ms = os.getenv("MS", "http://localhost:8080")
def post(path, body, headers):
    req = urllib.request.Request(ms + path, json.dumps(body).encode(), {"Content-Type": "application/json", **headers})
    return urllib.request.urlopen(req)
token = json.load(post("/api/v1/auth/login", {"username": "servicing@capstone.local", "password": os.environ["SEED"]},
                       {"X-Correlation-ID": os.environ["CID"]}))["accessToken"]
req = urllib.request.Request(ms + "/api/v1/mortgages/MTG-1001", headers={
    "Authorization": f"Bearer {token}", "X-Correlation-ID": os.environ["CID"]})
print(urllib.request.urlopen(req).status)
PY
)
say "GET /api/v1/mortgages/MTG-1001 -> HTTP $code, X-Correlation-ID: $cid"
say "Splunk: index=mortgage_dev correlationId=\"$cid\""
for i in $(seq 1 12); do
  if python3 scripts/splunk/apply.py --search "index=mortgage_dev correlationId=\"$cid\" | sort _time | table _time service.name log.level message http.route http.status durationMs" --earliest -10m; then
    break
  fi
  sleep 5
done

# ----------------------------------------------------------------------------------------------------------------
step "4. Dashboard + the alerts that fired during the simulation  (2 min)"
say "Dashboard: http://localhost:8002/en-US/app/search/mortgage_platform_overview  (time range: the drill window)"
python3 scripts/splunk/apply.py --earliest -30d \
  --search 'index=_audit action=alert_fired ss_name="mortgage_dev - *" | eval fired=strftime(_time, "%Y-%m-%dT%H:%M:%SZ") | table fired ss_name' \
  || say "no fired alerts in the last 30 days (run python3 scripts/incident/db_outage_drill.py)"

# ----------------------------------------------------------------------------------------------------------------
step "5. RCA summary  (2 min)"
awk '/^## 1\. Summary/{p=1;next} /^## 2\./{exit} p' docs/operations/rca-2026-11-10.md | sed 's/^/   /'
say "Full RCA: docs/operations/rca-2026-11-10.md (impact, timeline, root cause, corrective + preventive actions)"

printf '\n\033[1;32mDemo complete.\033[0m Checklist and sign-off: docs/operations/m9-demo-checklist.md\n'
