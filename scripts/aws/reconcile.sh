#!/usr/bin/env bash
# M8 Task 8.6: reconcile PostgreSQL against the curated delinquency report (run right after pipeline-run.sh).
#   bash scripts/aws/reconcile.sh                    # latest curated partition
#   RUN_DATE=2026-11-04 bash scripts/aws/reconcile.sh
# Runs `python -m src.services.reconcile` in a one-off analytics-service container (it reaches PostgreSQL directly)
# with 15-minute mortgage-analytics-role credentials (read-only on curated/ and raw/). Prints a PASS/FAIL table, saves
# the full JSON report to reports/aws/reconciliation/ (git-ignored). Exit 0 PASS, 1 FAIL, 2 could not run.
# Tolerances: docs/operations/data-pipeline-runbook.md#reconciliation
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

log "Session"
require_session
cd "$REPO_ROOT"
docker compose ps --status running --services 2>/dev/null | grep -qx postgres \
  || die "start the local stack first: docker compose up --build -d"

ROLE_ARN=$(aws_sb iam get-role --role-name mortgage-analytics-role --query Role.Arn --output text)
read -r AK SK ST < <(aws_sb sts assume-role --role-arn "$ROLE_ARN" --role-session-name reconcile \
  --duration-seconds 900 --query 'Credentials.[AccessKeyId,SecretAccessKey,SessionToken]' --output text)
[ -n "${ST:-}" ] || die "assume-role failed"
export M8_ANALYTICS_AWS_ACCESS_KEY_ID="$AK" M8_ANALYTICS_AWS_SECRET_ACCESS_KEY="$SK" M8_ANALYTICS_AWS_SESSION_TOKEN="$ST"
export M8_AWS_REGION="$AWS_SANDBOX_REGION" M8_DOCS_BUCKET="$DOCS_BUCKET" M8_LOOKUP_TABLE="$LOOKUP_TABLE" M8_ANALYTICS_BUCKET="$ANALYTICS_BUCKET"

log "Reconcile PostgreSQL vs s3://$ANALYTICS_BUCKET/$CURATED_PREFIX${RUN_DATE:+date=$RUN_DATE/} (as mortgage-analytics-role)"
OUT="$RENDER_DIR/reconciliation"; mkdir -p "$OUT"
rc=0
docker compose -f docker-compose.yml -f docker-compose.aws.yml run --rm --no-deps -T \
  -e ANALYTICS_CONSUMER_ENABLED=false -e RAW_PREFIX="$RAW_PREFIX" -e CURATED_PREFIX="$CURATED_PREFIX" \
  analytics-service python -m src.services.reconcile ${RUN_DATE:+--date "$RUN_DATE"} > "$OUT/latest.json" || rc=$?
[ "$rc" -le 1 ] || die "reconciliation could not run (exit $rc); see the error above"

python3 - "$OUT/latest.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1]))
color = {"PASS": "\033[1;32m", "FAIL": "\033[1;31m", "WARN": "\033[1;33m"}
print(f"  report date {r['reportDate']}  pipeline run {r['pipelineRunId']}  schema v{r['schemaVersion']}\n")
print(f"  {'check':<18} {'status':<6} {'expected':<34} {'actual':<34} detail")
for c in r["checks"]:
    exp, act = json.dumps(c["expected"]) if not isinstance(c["expected"], str) else c["expected"], \
               json.dumps(c["actual"]) if not isinstance(c["actual"], str) else c["actual"]
    tol = f" (tolerance {c['tolerance']})" if "tolerance" in c else ""
    print(f"  {c['check']:<18} {color[c['status']]}{c['status']:<6}\033[0m {exp[:34]:<34} {act[:34]:<34} {c.get('detail','')}{tol}")
    if c["status"] == "WARN":
        for item in c["actual"]:
            print(f"  {'':<25} {item}")
print(f"\n  RESULT: {color[r['result']]}{r['result']}\033[0m" + (f"  failed: {', '.join(r['failedChecks'])}" if r["failedChecks"] else "")
      + (f"  warnings: {', '.join(r['warnings'])}" if r["warnings"] else ""))
PY
day=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["reportDate"])' "$OUT/latest.json")
cp "$OUT/latest.json" "$OUT/date=$day.json"
printf '\n  full report: %s\n' "${OUT#$REPO_ROOT/}/date=$day.json"
exit "$rc"
