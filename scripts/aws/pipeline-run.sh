#!/usr/bin/env bash
# M8 Task 8.5: run the pipeline once.  PostgreSQL -> export/S3 raw -> Glue -> S3 curated -> (analytics reads it)
#   docker compose up --build -d                  # local PostgreSQL with the seed data
#   aws login --profile capstone-dev --region us-east-2
#   bash scripts/aws/pipeline-run.sh              # partition = today (UTC)
#   RUN_DATE=2026-11-04 bash scripts/aws/pipeline-run.sh
#   DRIFT_COLUMN=property_state bash scripts/aws/pipeline-run.sh                          # Task 8.6 drift: run FAILS + alert
#   DRIFT_COLUMN=property_state SCHEMA_DRIFT_MODE=evolve bash scripts/aws/pipeline-run.sh # tolerated, recorded in manifest
# Steps 2 and 3 run as mortgage-analytics-role (15-minute STS credentials): it may write raw/pg-export/ and start this
# one job, but cannot write curated/ (only the Glue role can). Runbook: docs/operations/data-pipeline-runbook.md
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

log "Session"
require_session
cd "$REPO_ROOT"
RUN_DATE="${RUN_DATE:-$(date -u +%F)}"
DRIFT_COLUMN="${DRIFT_COLUMN:-}"; SCHEMA_DRIFT_MODE="${SCHEMA_DRIFT_MODE:-fail}"
case "$DRIFT_COLUMN" in ''|[a-z]*) ;; *) die "DRIFT_COLUMN must be a lower-case column name" ;; esac
case "$DRIFT_COLUMN" in *[!a-z0-9_]*) die "DRIFT_COLUMN must be a lower-case column name" ;; esac
PIPELINE_RUN_ID="pr-$(date -u +%Y%m%dT%H%M%SZ)-$(python3 -c 'import uuid; print(uuid.uuid4().hex[:8])')"
WORK="$RENDER_DIR/pipeline/date=$RUN_DATE"; rm -rf "$WORK"; mkdir -p "$WORK"
env_value() { [ -f .env ] && grep -E "^$1=" .env | tail -1 | cut -d= -f2- || true; }
PGUSER_="${POSTGRES_USER:-$(env_value POSTGRES_USER)}"; PGUSER_="${PGUSER_:-mortgage_app}"
PGDB_="${POSTGRES_DB:-$(env_value POSTGRES_DB)}"; PGDB_="${PGDB_:-mortgage_intel}"
docker compose ps --status running --services 2>/dev/null | grep -qx postgres \
  || die "start the local stack first: docker compose up --build -d"
aws_sb glue get-job --job-name "$GLUE_JOB" >/dev/null 2>&1 || die "run bash scripts/aws/pipeline-deploy.sh first"
psql_() { docker exec -i capstone-postgres psql -U "$PGUSER_" -d "$PGDB_" -v ON_ERROR_STOP=1 -qAt "$@"; }

log "1. Export PostgreSQL (run date $RUN_DATE, pipeline run $PIPELINE_RUN_ID)"
# Only the columns the report needs. The borrower export has the business ID only: no names, contact data or DOB.
declare_sql() {
  case "$1" in
    mortgage)    echo "SELECT id, mortgage_external_id, borrower_id, status, original_amount, outstanding_balance, origination_date${DRIFT_COLUMN:+, 'CA'::text AS $DRIFT_COLUMN} FROM mortgage ORDER BY mortgage_external_id" ;;
    borrower)    echo "SELECT id, borrower_external_id FROM borrower ORDER BY borrower_external_id" ;;
    delinquency) echo "SELECT mortgage_id, delinquent_since, days_past_due, severity FROM delinquency ORDER BY mortgage_id" ;;
    payment)     echo "SELECT mortgage_id, due_date, paid_date, amount, status FROM payment ORDER BY mortgage_id, due_date" ;;
  esac
}
[ -z "$DRIFT_COLUMN" ] || warn "DRIFT DEMO: the mortgage export gets an extra column '$DRIFT_COLUMN' (schema drift mode: $SCHEMA_DRIFT_MODE)"
for table in mortgage borrower delinquency payment; do
  psql_ -c "\\copy ($(declare_sql "$table")) TO STDOUT WITH (FORMAT csv, HEADER true)" > "$WORK/$table.csv"
  ok "$table.csv  $(($(wc -l < "$WORK/$table.csv") - 1)) rows"
done
psql_ -F '|' -c "SELECT (SELECT count(*) FROM mortgage), (SELECT coalesce(sum(outstanding_balance),0) FROM mortgage),
                        (SELECT count(*) FROM borrower), (SELECT count(*) FROM delinquency), (SELECT count(*) FROM payment)" \
  | python3 -c 'import json,sys
m,bal,b,d,p = sys.stdin.read().strip().split("|")
print(json.dumps({"exportedAt": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(timespec="seconds"),
  "runDate": sys.argv[1], "pipelineRunId": sys.argv[2], "source": "postgresql", "rowCounts": {"mortgage": int(m), "borrower": int(b), "delinquency": int(d), "payment": int(p)},
  "mortgageOutstandingBalanceTotal": bal}, indent=2))' "$RUN_DATE" "$PIPELINE_RUN_ID" > "$WORK/_export_manifest.json"
ok "_export_manifest.json  (control totals for reconciliation)"

log "2. Upload to s3://$ANALYTICS_BUCKET/${RAW_PREFIX}date=$RUN_DATE/ as mortgage-analytics-role"
ROLE_ARN=$(aws_sb iam get-role --role-name mortgage-analytics-role --query Role.Arn --output text)
CREDS=$(aws_sb sts assume-role --role-arn "$ROLE_ARN" --role-session-name pipeline-run --duration-seconds 900 \
  --query 'Credentials.[AccessKeyId,SecretAccessKey,SessionToken]' --output text)
as_role() {
  env -u AWS_PROFILE AWS_ACCESS_KEY_ID="$(printf '%s' "$CREDS" | cut -f1)" \
    AWS_SECRET_ACCESS_KEY="$(printf '%s' "$CREDS" | cut -f2)" AWS_SESSION_TOKEN="$(printf '%s' "$CREDS" | cut -f3)" \
    aws --region "$AWS_SANDBOX_REGION" "$@"
}
for f in mortgage.csv borrower.csv delinquency.csv payment.csv _export_manifest.json; do
  case "$f" in *.csv) ct=text/csv ;; *) ct=application/json ;; esac
  as_role s3api put-object --bucket "$ANALYTICS_BUCKET" --key "${RAW_PREFIX}date=$RUN_DATE/$f" --body "$WORK/$f" \
    --content-type "$ct" >/dev/null
done
ok "5 objects uploaded (SSE-S3 by bucket default)"

log "3. Glue job $GLUE_JOB"
RUN_ID=$(as_role glue start-job-run --job-name "$GLUE_JOB" --arguments "{\"--RUN_DATE\":\"$RUN_DATE\",\"--PIPELINE_RUN_ID\":\"$PIPELINE_RUN_ID\",\"--SCHEMA_DRIFT_MODE\":\"$SCHEMA_DRIFT_MODE\"}" \
  --query JobRunId --output text)
ok "started Glue run $RUN_ID for pipeline run $PIPELINE_RUN_ID (as mortgage-analytics-role)"
state=""; started=$(date +%s)
while :; do
  read -r state secs < <(as_role glue get-job-run --job-name "$GLUE_JOB" --run-id "$RUN_ID" \
    --query 'JobRun.[JobRunState, ExecutionTime]' --output text)
  [ -n "$state" ] || die "could not read the state of run $RUN_ID"
  [ $(( $(date +%s) - started )) -lt 900 ] || die "run $RUN_ID still $state after 15 min (job timeout is 10 min)"
  case "$state" in SUCCEEDED|FAILED|ERROR|TIMEOUT|STOPPED) break ;; esac
  printf '  ... %s (%ss)\n' "$state" "$(( $(date +%s) - started ))"
  sleep 15
done
if [ "$state" = "SUCCEEDED" ]; then ok "SUCCEEDED in ${secs}s of execution"; else
  err "run $RUN_ID ended $state: $(as_role glue get-job-run --job-name "$GLUE_JOB" --run-id "$RUN_ID" --query JobRun.ErrorMessage --output text)"
fi

log "Job log lines (/aws-glue/python-jobs/output, stream $RUN_ID)"
sleep 5
for group in /aws-glue/python-jobs/output /aws-glue/python-jobs/error; do
  aws_sb logs filter-log-events --log-group-name "$group" --log-stream-names "$RUN_ID" \
    --query 'events[].message' --output text 2>/dev/null | tr '\t' '\n' | grep '"service": "glue-delinquency-etl"' | sed 's/^/  /' || true
done
if [ "$state" != "SUCCEEDED" ]; then
  log "Alert (EventBridge rule $GLUE_JOB-failed -> $PIPELINE_ALERT_LOG_GROUP)"
  alert=""
  for _ in $(seq 1 12); do
    alert=$(aws_sb logs filter-log-events --log-group-name "$PIPELINE_ALERT_LOG_GROUP" \
      --filter-pattern "{ \$.detail.jobRunId = \"$RUN_ID\" }" --max-items 1 --query 'events[0].message' --output json 2>/dev/null || true)
    [ -n "$alert" ] && [ "$alert" != "null" ] && break
    sleep 10
  done
  if [ -n "$alert" ] && [ "$alert" != "null" ]; then
    printf '%s' "$alert" | python3 -c 'import json,sys; e=json.loads(json.load(sys.stdin)); d=e["detail"]; print("  ALERT %s  %s: job %s run %s -> %s" % (e["time"], e["detail-type"], d["jobName"], d["jobRunId"], d["state"]))' \
      || printf '  ALERT recorded for %s (raw event: aws logs tail %s --since 10m --profile %s)\n' "$RUN_ID" "$PIPELINE_ALERT_LOG_GROUP" "$AWS_SANDBOX_PROFILE"
  else
    warn "no alert event yet (EventBridge can take a minute): aws logs tail $PIPELINE_ALERT_LOG_GROUP --since 10m --profile $AWS_SANDBOX_PROFILE"
  fi
  printf '  Previous curated output for %s is untouched (checks run before any delete/write).\n' "$RUN_DATE"
  die "pipeline failed; see docs/operations/data-pipeline-runbook.md#failure-handling"
fi

log "4. Curated output (read back as mortgage-analytics-role)"
as_role s3api list-objects-v2 --bucket "$ANALYTICS_BUCKET" --prefix "${CURATED_PREFIX}date=$RUN_DATE/" \
  --query 'Contents[].[Key,Size]' --output text | awk '{printf "  s3://'"$ANALYTICS_BUCKET"'/%s  (%s bytes)\n", $1, $2}'
as_role s3api get-object --bucket "$ANALYTICS_BUCKET" --key "${CURATED_PREFIX}date=$RUN_DATE/_manifest.json" "$WORK/_manifest.json" >/dev/null
python3 - "$WORK/_manifest.json" "$WORK/_export_manifest.json" <<'PY'
import json, sys
cur, src = json.load(open(sys.argv[1])), json.load(open(sys.argv[2]))
print(f"  curated rows {cur['rowCount']} (PostgreSQL mortgages {src['rowCounts']['mortgage']}), "
      f"balance {cur['outstandingBalanceTotal']} (PostgreSQL {src['mortgageOutstandingBalanceTotal']}), "
      f"delinquent {cur['delinquentCount']}, schema v{cur['schemaVersion']}, pipeline run {cur.get('pipelineRunId')}")
if cur.get("schemaDrift"):
    print(f"  schema drift tolerated ({cur.get('schemaDriftMode')} mode): {cur['schemaDrift']} - add to the schema in a PR")
PY
as_role s3api get-object --bucket "$ANALYTICS_BUCKET" --key "${CURATED_PREFIX}date=$RUN_DATE/part-0000.csv" "$WORK/curated.csv" >/dev/null
printf '  first rows of part-0000.csv:\n'; head -4 "$WORK/curated.csv" | sed 's/^/    /'

printf '\n\033[1;32mPipeline run complete.\033[0m Next: bash scripts/aws/reconcile.sh   (report API: GET :8000/api/v1/analytics/curated/delinquency-report)\n'
