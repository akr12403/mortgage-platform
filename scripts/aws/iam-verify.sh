#!/usr/bin/env bash
# M8 Task 8.1: prove least privilege with the IAM policy simulator (read-only; no resource needs to exist yet).
#   bash scripts/aws/iam-verify.sh            # every case must match: what each role needs is allowed,
#                                             # everything around it is denied. Exit 1 on any mismatch.
# Evidence for docs/architecture/aws-iam-matrix.md#verification and demo step 1.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

log "Session"
require_session

A="$ACCOUNT_ID"; R="$AWS_SANDBOX_REGION"
DOC="arn:aws:s3:::$DOCS_BUCKET/${DOCS_UPLOAD_PREFIX}MTG-1001/sample.pdf"
RAW="arn:aws:s3:::$ANALYTICS_BUCKET/${RAW_PREFIX}date=2026-11-02/mortgage_export.csv"
CUR="arn:aws:s3:::$ANALYTICS_BUCKET/${CURATED_PREFIX}part-0000.csv"
LAKE="arn:aws:s3:::$ANALYTICS_BUCKET"
TOPIC="arn:aws:sns:$R:$A:$LIFECYCLE_TOPIC"
SQ="arn:aws:sqs:$R:$A:$SERVICING_QUEUE"
AQ="arn:aws:sqs:$R:$A:$ANALYTICS_QUEUE"
LOOKUP="arn:aws:dynamodb:$R:$A:table/$LOOKUP_TABLE"
META="arn:aws:dynamodb:$R:$A:table/$DOC_METADATA_TABLE"
JOB="arn:aws:glue:$R:$A:job/$GLUE_JOB"
# CloudWatch Logs authorizes CreateLogStream and PutLogEvents against the log GROUP ARN (…:log-group:NAME:*),
# not the stream, so these cases use that form.
LOGS="arn:aws:logs:$R:$A:log-group:/aws/lambda/$LAMBDA_FUNCTION:*"
GLUELOGS="arn:aws:logs:$R:$A:log-group:/aws-glue/python-jobs/output:*"

# role | action | resource | expected (allow|deny) | s3:prefix context (optional) | why
CASES=$(cat <<EOF
mortgage-api-role|sns:Publish|$TOPIC|allow||publishes lifecycle events
mortgage-api-role|sns:Publish|arn:aws:sns:$R:$A:some-other-topic|deny||only its own topic
mortgage-api-role|sns:Subscribe|$TOPIC|deny||cannot add subscribers
mortgage-api-role|s3:GetObject|$DOC|deny||no document access
mortgage-api-role|sqs:ReceiveMessage|$SQ|deny||not a consumer
mortgage-servicing-role|sqs:ReceiveMessage|$SQ|allow||consumes its queue
mortgage-servicing-role|sqs:DeleteMessage|$SQ|allow||acks processed messages
mortgage-servicing-role|sqs:PurgeQueue|$SQ|deny||cannot wipe the queue
mortgage-servicing-role|sqs:ReceiveMessage|$AQ|deny||not the analytics queue
mortgage-servicing-role|sns:Publish|$TOPIC|deny||not a producer
mortgage-analytics-role|s3:PutObject|$DOC|allow||document upload endpoint
mortgage-analytics-role|s3:GetObject|$DOC|deny||cannot read borrower documents back
mortgage-analytics-role|s3:DeleteObject|$DOC|deny||cannot delete documents
mortgage-analytics-role|s3:PutObject|$RAW|allow||writes the PG export
mortgage-analytics-role|s3:GetObject|$CUR|allow||reads the curated report
mortgage-analytics-role|s3:PutObject|$CUR|deny||only Glue writes curated
mortgage-analytics-role|s3:ListBucket|$LAKE|allow|$CURATED_PREFIX|lists the curated prefix
mortgage-analytics-role|s3:ListBucket|$LAKE|deny||cannot list the whole bucket
mortgage-analytics-role|glue:StartJobRun|$JOB|allow||starts the ETL job
mortgage-analytics-role|glue:StartJobRun|arn:aws:glue:$R:$A:job/any-other-job|deny||only that job
mortgage-analytics-role|dynamodb:GetItem|$LOOKUP|allow||lookup by mortgageExternalId
mortgage-analytics-role|dynamodb:Scan|$LOOKUP|deny||no full-table scans
mortgage-analytics-role|dynamodb:DeleteTable|$LOOKUP|deny||no table admin
mortgage-analytics-role|sqs:ReceiveMessage|$AQ|allow||consumes analytics queue
mortgage-analytics-role|iam:PassRole|arn:aws:iam::$A:role/mortgage-glue-etl-role|deny||cannot hand out roles
lambda-doc-processor-role|s3:GetObject|$DOC|allow||reads the uploaded file
lambda-doc-processor-role|s3:PutObject|$DOC|deny||cannot change documents
lambda-doc-processor-role|s3:GetObject|$CUR|deny||no data-lake access
lambda-doc-processor-role|dynamodb:PutItem|$META|allow||writes the metadata item
lambda-doc-processor-role|dynamodb:PutItem|$LOOKUP|deny||not the lookup table
lambda-doc-processor-role|logs:CreateLogStream|$LOGS|allow||new stream per container
lambda-doc-processor-role|logs:PutLogEvents|$LOGS|allow||its own log group
lambda-doc-processor-role|logs:PutLogEvents|arn:aws:logs:$R:$A:log-group:/aws/lambda/other-fn:*|deny||no other log groups
mortgage-glue-etl-role|s3:GetObject|$RAW|allow||reads the raw export
mortgage-glue-etl-role|s3:PutObject|$CUR|allow||writes curated output
mortgage-glue-etl-role|s3:PutObject|$RAW|deny||raw zone is append-by-export only
mortgage-glue-etl-role|s3:GetObject|$DOC|deny||no borrower documents in ETL
mortgage-glue-etl-role|logs:PutLogEvents|$GLUELOGS|allow||writes job output logs
mortgage-glue-etl-role|logs:PutLogEvents|$LOGS|deny||not the Lambda log group
EOF
)

log "Policy simulator ($(printf '%s\n' "$CASES" | wc -l | tr -d ' ') cases)"
fails=0; current=""
while IFS='|' read -r role action resource expect prefix why <&3; do
  if [ "$role" != "$current" ]; then
    current="$role"
    role_arn=$(aws_sb iam get-role --role-name "$role" --query Role.Arn --output text 2>/dev/null) \
      || die "$role not found: run bash scripts/aws/iam-apply.sh first"
    printf '\n  \033[1m%s\033[0m\n' "$role"
  fi
  # A real request always carries its Region. The project's guardrail policy (SCP "RegionFloor") denies requests
  # outside the project Region, and in the simulator a missing aws:RequestedRegion counts as "outside", so pass it.
  ctx=(--context-entries "ContextKeyName=aws:RequestedRegion,ContextKeyValues=$R,ContextKeyType=string")
  [ -n "$prefix" ] && ctx+=("ContextKeyName=s3:prefix,ContextKeyValues=$prefix,ContextKeyType=string")
  result=$(aws_sb iam simulate-principal-policy --policy-source-arn "$role_arn" --action-names "$action" \
    --resource-arns "$resource" "${ctx[@]}" --output text \
    --query 'EvaluationResults[0].[EvalDecision, join(`,`, MatchedStatements[].SourcePolicyId || `[]`), join(`,`, MissingContextValues || `[]`)]')
  decision=$(printf '%s' "$result" | cut -f1)
  got=deny; [ "$decision" = "allowed" ] && got=allow
  case "$resource" in
    arn:aws:logs:*) short="${resource#*log-group:}"; short="${short%%:log-stream*}"; short="${short%:\*}" ;;
    *) short="${resource##*:::}"; short="${short##*:}" ;;
  esac
  if [ "$got" = "$expect" ]; then
    printf '    \033[1;32mPASS\033[0m %-5s %-22s %-48s %s\n' "$expect" "$action" "$short${prefix:+ (prefix $prefix)}" "$why"
  else
    printf '    \033[1;31mFAIL\033[0m expected %s, simulator says %s: %s on %s\n' "$expect" "$decision" "$action" "$resource"
    printf '         matched policies: %s   missing context: %s\n' \
      "$(printf '%s' "$result" | cut -f2)" "$(printf '%s' "$result" | cut -f3)"
    fails=$((fails + 1))
  fi
done 3< <(printf '%s\n' "$CASES")

[ "$fails" = 0 ] || die "$fails case(s) did not match"
printf '\n\033[1;32mLeast privilege verified.\033[0m Every needed action is allowed; everything around it is denied.\n'
