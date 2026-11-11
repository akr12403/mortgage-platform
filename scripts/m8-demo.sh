#!/usr/bin/env bash
# M8 demo: the milestone's 5-step demo scenario against the AWS sandbox + local stack (~12 minutes).
#   bash scripts/m8-demo.sh             # run straight through
#   PAUSE=1 bash scripts/m8-demo.sh     # wait for Enter before each step (rehearsal / live demo)
# Prereqs: docker compose up --build -d (all healthy); aws login --profile capstone-dev --region us-east-2;
#          everything deployed once (iam-apply, s3-apply, lambda-deploy, lookup-deploy + lookup-load, pipeline-deploy).
# Cost: one Lambda invocation, one Glue run (~$0.0005), a few S3/DynamoDB requests; Free plan. The demo leaves
# analytics-service back on LocalStack-only at the end.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
source scripts/aws/lib.sh
mkdir -p "$RENDER_DIR"
MS=${MORTGAGE_API_BASE:-http://localhost:8080}
AS=${ANALYTICS_API_BASE:-http://localhost:8000}

step() {
  printf '\n\033[1;36m== %s ==\033[0m\n' "$*"
  if [[ "${PAUSE:-0}" == "1" ]]; then read -r -p "   (Enter to run) " _; fi
}
say() { printf '   \033[2m%s\033[0m\n' "$*"; }
env_value() { [[ -f .env ]] && grep -E "^$1=" .env | tail -1 | cut -d= -f2- || true; }
SEED_PASSWORD="${AUTH_SEED_PASSWORD:-$(env_value AUTH_SEED_PASSWORD)}"
[[ -n "$SEED_PASSWORD" ]] || { echo "AUTH_SEED_PASSWORD is not set (export it or put it in .env)." >&2; exit 1; }
login() {  # login USERNAME -> access token (never printed)
  SEED_PASSWORD="$SEED_PASSWORD" U="$1" python3 -c 'import json,os,urllib.request
r=urllib.request.Request(os.environ["MS"]+"/api/v1/auth/login",json.dumps({"username":os.environ["U"],"password":os.environ["SEED_PASSWORD"]}).encode(),{"Content-Type":"application/json"})
print(json.load(urllib.request.urlopen(r))["accessToken"])'
}
export MS
trap 'docker compose up -d analytics-service >/dev/null 2>&1 || true' EXIT   # always back to LocalStack-only

printf '\033[1mM8 AWS & Data Platform demo\033[0m  (project Region %s)\n' "$AWS_SANDBOX_REGION"
require_session

# ----------------------------------------------------------------------------------------------------------------
step "1. IAM matrix for one service role: mortgage-analytics-role  (2 min)"
say "docs/architecture/aws-iam-matrix.md: one role per workload, one inline policy, exact ARNs, no '*' actions."
awk '/^\| `mortgage-analytics-role`/{p=1} p&&/^\| `lambda-doc-processor-role`/{exit} p' docs/architecture/aws-iam-matrix.md \
  | cut -d'|' -f5-7 | sed 's/^/     /'
say "Proved with the IAM policy simulator (needed actions allowed, everything around them denied):"
ROLE=mortgage-analytics-role bash scripts/aws/iam-verify.sh 2>&1 | sed -n '/mortgage-analytics-role/,$p'

# ----------------------------------------------------------------------------------------------------------------
step "2. Upload a document -> Lambda log line  (3 min)"
say "analytics-service on real S3 with 1-hour mortgage-analytics-role credentials (no access keys):"
bash scripts/aws/compose-aws-up.sh 2>&1 | grep -E 'OK|credentials' | sed 's/^/  /'
for _ in $(seq 1 20); do curl -fs "$AS/health" >/dev/null 2>&1 && break; sleep 2; done
TOKEN=$(login servicing@capstone.local)
printf '%%PDF-1.4\n%% synthetic M8 demo deed, no borrower data\n%%%%EOF\n' > "$RENDER_DIR/m8-demo-deed.pdf"
resp=$(curl -s -i -X POST "$AS/api/v1/documents/upload" -H "Authorization: Bearer $TOKEN" \
  -F mortgage_external_id=MTG-1002 -F document_type=DEED -F "file=@$RENDER_DIR/m8-demo-deed.pdf;type=application/pdf")
CID=$(printf '%s' "$resp" | awk -F': ' 'tolower($1)=="x-correlation-id"{print $2}' | tr -d '\r')
printf '   POST /api/v1/documents/upload -> %s\n' "$(printf '%s' "$resp" | head -1 | tr -d '\r')"
printf '   %s\n' "$(printf '%s' "$resp" | tail -1)"
say "S3 ObjectCreated -> Lambda validates the first 1 KB -> DynamoDB metadata item -> one JSON log line (correlationId $CID):"
line=""
for _ in $(seq 1 15); do
  line=$(aws_sb logs filter-log-events --log-group-name "/aws/lambda/$LAMBDA_FUNCTION" --start-time $(( ($(date +%s) - 300) * 1000 )) \
    --filter-pattern "{ \$.correlationId = \"$CID\" }" --max-items 1 --query 'events[0].message' --output json 2>/dev/null || true)
  [[ -n "$line" && "$line" != "null" ]] && break
  sleep 4
done
printf '%s' "$line" | python3 -c 'import json,sys
m=json.loads(json.load(sys.stdin)); print("   " + json.dumps(m))' 2>/dev/null || say "(log line not found yet: aws logs tail /aws/lambda/$LAMBDA_FUNCTION --since 5m --profile $AWS_SANDBOX_PROFILE)"

# ----------------------------------------------------------------------------------------------------------------
step "3. Run the pipeline; show the curated file  (3 min)"
say "PostgreSQL export -> s3 raw/pg-export/ -> Glue (schema-checked) -> s3 curated/delinquency_report/"
bash scripts/aws/pipeline-run.sh 2>&1 | grep -v -E '^\s*$|^== Session|account [0-9]' | sed -n '1,200p'
say "The same partition through the analytics API (latest curated report):"
ADMIN_TOKEN=$(login admin@capstone.local)
curl -s "$AS/api/v1/analytics/curated/delinquency-report" -H "Authorization: Bearer $ADMIN_TOKEN" | python3 -c 'import json,sys
r=json.load(sys.stdin)
print("   %s: %d mortgages, %d delinquent (%.1f%%), balance at risk %s of %s" % (r["reportDate"], r["mortgageCount"], r["delinquentCount"],
      100 * r["delinquencyRate"], format(r["balanceAtRisk"], ",.2f"), format(r["outstandingBalanceTotal"], ",.2f")))
print("   risk buckets: " + ", ".join("%s %d" % (k, v["count"]) for k, v in r["byRiskBucket"].items()))' 2>/dev/null \
  || say "(report API needs the AWS mode; the pipeline output above is the evidence)"

# ----------------------------------------------------------------------------------------------------------------
step "4. Reconciliation output  (2 min)"
say "PostgreSQL vs curated: rows 0 difference, balance sum within 0.01, per-row and export-control checks:"
bash scripts/aws/reconcile.sh 2>&1 | sed -n '/report date/,$p' || true

# ----------------------------------------------------------------------------------------------------------------
step "5. DynamoDB partition key choice  (2 min)"
say "docs/architecture/aws-dynamodb-mortgage-lookup.md#partition-key-exercise-session-29"
awk '/^\| Candidate PK/{p=1} p&&/^$/{exit} p' docs/architecture/aws-dynamodb-mortgage-lookup.md | cut -c1-170 | sed 's/^/     /'
say "Live: one GetItem by mortgageExternalId through the analytics API:"
curl -s "$AS/api/v1/lookup/mortgages/MTG-1002" -H "Authorization: Bearer $TOKEN" | python3 -c 'import json,sys
r=json.load(sys.stdin)
print("   MTG-1002: status %s, balance %s, source %s, last event %s, %s ms" % (r["status"], format(r["outstandingBalance"], ",.2f"),
      r["source"], r.get("lastEventType", "-"), r["lookupMs"]))' 2>/dev/null \
  || say "(lookup unavailable: run bash scripts/aws/lookup-load.sh)"

printf '\n\033[1;32mDemo complete.\033[0m analytics-service is switched back to LocalStack-only. Evidence index: docs/operations/m8-demo-checklist.md\n'
