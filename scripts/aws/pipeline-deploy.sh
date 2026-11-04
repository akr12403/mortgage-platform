#!/usr/bin/env bash
# M8 Task 8.5: deploy the Glue ETL job (idempotent).
#   aws login --profile capstone-dev --region us-east-2
#   bash scripts/aws/pipeline-deploy.sh     # upload script + schema to s3://<analytics>/glue/, create/update the job
#   bash scripts/aws/pipeline-run.sh        # export PostgreSQL -> raw, run the job -> curated
# Job: Python shell, Python 3.9, 0.0625 DPU (about $0.0005 per 1-minute run), 10-minute timeout, no retries,
# one concurrent run, role mortgage-glue-etl-role. Code: infrastructure/glue/delinquency_report_etl.py.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

log "Session"
require_session
SCRIPT_KEY="${GLUE_ASSETS_PREFIX}scripts/delinquency_report_etl.py"
SCHEMA_KEY="${GLUE_ASSETS_PREFIX}schemas/delinquency_report.schema.json"

log "1. Job assets -> s3://$ANALYTICS_BUCKET/$GLUE_ASSETS_PREFIX"
aws_sb s3api head-bucket --bucket "$ANALYTICS_BUCKET" >/dev/null 2>&1 || die "run bash scripts/aws/s3-apply.sh first"
aws_sb s3api put-object --bucket "$ANALYTICS_BUCKET" --key "$SCRIPT_KEY" \
  --body "$REPO_ROOT/infrastructure/glue/delinquency_report_etl.py" --content-type text/x-python >/dev/null
aws_sb s3api put-object --bucket "$ANALYTICS_BUCKET" --key "$SCHEMA_KEY" \
  --body "$REPO_ROOT/infrastructure/glue/schemas/delinquency_report.schema.json" --content-type application/json >/dev/null
ok "uploaded $SCRIPT_KEY and $SCHEMA_KEY"

log "2. Log groups (7-day retention)"
for group in /aws-glue/python-jobs/output /aws-glue/python-jobs/error; do
  if [ "$(aws_sb logs describe-log-groups --log-group-name-prefix "$group" --query "length(logGroups[?logGroupName=='$group'])" --output text)" = "0" ]; then
    aws_sb logs create-log-group --log-group-name "$group" --tags "Project=$TAG_PROJECT,Environment=$TAG_ENVIRONMENT,Team=$TAG_TEAM"
  fi
  aws_sb logs put-retention-policy --log-group-name "$group" --retention-in-days 7
  ok "$group"
done

log "3. Glue job $GLUE_JOB"
ROLE_ARN=$(aws_sb iam get-role --role-name mortgage-glue-etl-role --query Role.Arn --output text)
OUT="$RENDER_DIR/glue"; mkdir -p "$OUT"
python3 - "$OUT/job.json" "$ROLE_ARN" "$ANALYTICS_BUCKET" "$SCRIPT_KEY" "$SCHEMA_KEY" "$RAW_PREFIX" "$CURATED_PREFIX" <<'PY'
import json, sys
out, role, bucket, script, schema, raw, curated = sys.argv[1:]
job = {
    "Role": role,
    "Description": "M8: PostgreSQL export (raw) -> delinquency_report (curated), schema-checked",
    "Command": {"Name": "pythonshell", "PythonVersion": "3.9", "ScriptLocation": f"s3://{bucket}/{script}"},
    "MaxCapacity": 0.0625, "Timeout": 10, "MaxRetries": 0,
    "ExecutionProperty": {"MaxConcurrentRuns": 1},
    "DefaultArguments": {"--library-set": "analytics", "--BUCKET": bucket, "--RAW_PREFIX": raw,
                         "--CURATED_PREFIX": curated, "--SCHEMA_KEY": schema, "--enable-job-insights": "false"},
}
json.dump(job, open(out, "w"), indent=2)
PY
if aws_sb glue get-job --job-name "$GLUE_JOB" >/dev/null 2>&1; then
  aws_sb glue update-job --job-name "$GLUE_JOB" --job-update "file://$OUT/job.json" >/dev/null
  ok "updated (Python shell 3.9, 0.0625 DPU, timeout 10 min, role mortgage-glue-etl-role)"
else
  aws_sb glue create-job --name "$GLUE_JOB" --cli-input-json "file://$OUT/job.json" \
    --tags "Project=$TAG_PROJECT,Environment=$TAG_ENVIRONMENT,Team=$TAG_TEAM" >/dev/null
  ok "created (Python shell 3.9, 0.0625 DPU, timeout 10 min, role mortgage-glue-etl-role)"
fi

printf '\n\033[1;32mGlue job deployed.\033[0m Next: bash scripts/aws/pipeline-run.sh\n'
