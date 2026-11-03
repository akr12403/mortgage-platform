#!/usr/bin/env bash
# M8 Task 8.2: prove the S3 controls on the real buckets.
#   bash scripts/aws/s3-verify.sh
# 1. Configuration: Block Public Access, ACLs disabled, SSE-S3 default encryption, TLS-only policy, not public, tags.
# 2. Live, as mortgage-analytics-role (15-minute STS credentials, never printed or written to disk):
#    upload over HTTPS works and is encrypted; reading it back, writing outside mortgages/ and plain HTTP are denied;
#    an anonymous GET is denied. Test objects are deleted at the end (by the developer session).
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

log "Session"
require_session
R="$AWS_SANDBOX_REGION"
fails=0
pass_() { printf '    \033[1;32mPASS\033[0m %s\n' "$*"; }
fail_() { printf '    \033[1;31mFAIL\033[0m %s\n' "$*"; fails=$((fails + 1)); }
check() {  # check LABEL EXPECTED ACTUAL
  if [ "$2" = "$3" ]; then pass_ "$1"; else fail_ "$1 (expected '$2', got '$3')"; fi
}

log "Configuration"
for bucket in "$DOCS_BUCKET" "$ANALYTICS_BUCKET"; do
  printf '\n  \033[1ms3://%s\033[0m\n' "$bucket"
  check "Block Public Access (4/4)" "True True True True" \
    "$(aws_sb s3api get-public-access-block --bucket "$bucket" --output text \
       --query 'PublicAccessBlockConfiguration.[BlockPublicAcls,IgnorePublicAcls,BlockPublicPolicy,RestrictPublicBuckets]' | tr '\t' ' ')"
  check "ACLs disabled (BucketOwnerEnforced)" "BucketOwnerEnforced" \
    "$(aws_sb s3api get-bucket-ownership-controls --bucket "$bucket" --output text --query 'OwnershipControls.Rules[0].ObjectOwnership')"
  check "default encryption SSE-S3" "AES256" \
    "$(aws_sb s3api get-bucket-encryption --bucket "$bucket" --output text \
       --query 'ServerSideEncryptionConfiguration.Rules[0].ApplyServerSideEncryptionByDefault.SSEAlgorithm')"
  check "bucket is not public (policy status)" "False" \
    "$(aws_sb s3api get-bucket-policy-status --bucket "$bucket" --output text --query 'PolicyStatus.IsPublic')"
  sids=$(aws_sb s3api get-bucket-policy --bucket "$bucket" --output text --query Policy \
    | python3 -c 'import json,sys; print(" ".join(s["Sid"] for s in json.load(sys.stdin)["Statement"]))')
  check "policy denies non-TLS and TLS < 1.2" "DenyInsecureTransport DenyTlsOlderThan12" "$sids"
  check "lifecycle rules present" "yes" \
    "$(aws_sb s3api get-bucket-lifecycle-configuration --bucket "$bucket" --output text --query 'length(Rules) > `0`' | sed 's/True/yes/')"
  check "tag Project" "$TAG_PROJECT" \
    "$(aws_sb s3api get-bucket-tagging --bucket "$bucket" --output text --query "TagSet[?Key=='Project'].Value | [0]")"
done

log "Live checks as mortgage-analytics-role"
ROLE_ARN=$(aws_sb iam get-role --role-name mortgage-analytics-role --query Role.Arn --output text)
CREDS=$(aws_sb sts assume-role --role-arn "$ROLE_ARN" --role-session-name m8-s3-verify --duration-seconds 900 \
  --query 'Credentials.[AccessKeyId,SecretAccessKey,SessionToken]' --output text)
as_role() {  # run aws as the assumed role (env credentials only for this one command)
  env -u AWS_PROFILE AWS_ACCESS_KEY_ID="$(printf '%s' "$CREDS" | cut -f1)" \
    AWS_SECRET_ACCESS_KEY="$(printf '%s' "$CREDS" | cut -f2)" AWS_SESSION_TOKEN="$(printf '%s' "$CREDS" | cut -f3)" \
    aws --region "$R" "$@"
}
expect_denied() {  # expect_denied LABEL aws-args...
  local label="$1" out; shift
  if out=$(as_role "$@" 2>&1); then fail_ "$label (request succeeded)"
  elif printf '%s' "$out" | grep -q 'AccessDenied'; then pass_ "$label (AccessDenied)"
  else fail_ "$label (unexpected error: $(printf '%s' "$out" | tail -1))"; fi
}
printf '  assumed %s (15 min)\n\n' "$(as_role sts get-caller-identity --query Arn --output text)"

STAMP=$(date -u +%Y%m%dT%H%M%SZ)
BODY="$RENDER_DIR/s3-verify-body.txt"; mkdir -p "$RENDER_DIR"
printf 'M8 s3-verify test object %s (synthetic, no borrower data)\n' "$STAMP" > "$BODY"
DOC_KEY="${DOCS_UPLOAD_PREFIX}MTG-0000/s3-verify-$STAMP.txt"
RAW_KEY="${RAW_PREFIX}s3-verify/s3-verify-$STAMP.txt"

sse=$(as_role s3api put-object --bucket "$DOCS_BUCKET" --key "$DOC_KEY" --body "$BODY" --content-type text/plain \
  --query ServerSideEncryption --output text 2>&1) || sse="error: $(printf '%s' "$sse" | tail -1)"
check "upload to $DOCS_BUCKET/$DOC_KEY over HTTPS, stored encrypted" "AES256" "$sse"
expect_denied "read the document back" s3api get-object --bucket "$DOCS_BUCKET" --key "$DOC_KEY" "$RENDER_DIR/s3-verify-get.txt"
expect_denied "upload outside ${DOCS_UPLOAD_PREFIX}" s3api put-object --bucket "$DOCS_BUCKET" --key "other/s3-verify-$STAMP.txt" --body "$BODY"
expect_denied "upload over plain HTTP (bucket policy)" s3api put-object --bucket "$DOCS_BUCKET" --key "${DOCS_UPLOAD_PREFIX}MTG-0000/http-$STAMP.txt" \
  --body "$BODY" --endpoint-url "http://s3.$R.amazonaws.com"
expect_denied "delete the document" s3api delete-object --bucket "$DOCS_BUCKET" --key "$DOC_KEY"
raw=$(as_role s3api put-object --bucket "$ANALYTICS_BUCKET" --key "$RAW_KEY" --body "$BODY" --query ServerSideEncryption --output text 2>&1) \
  || raw="error: $(printf '%s' "$raw" | tail -1)"
check "write the raw export zone ($ANALYTICS_BUCKET/$RAW_PREFIX)" "AES256" "$raw"
expect_denied "write the curated zone (Glue only)" s3api put-object --bucket "$ANALYTICS_BUCKET" --key "${CURATED_PREFIX}s3-verify-$STAMP.txt" --body "$BODY"

code=$(curl -s -o /dev/null -w '%{http_code}' "https://$DOCS_BUCKET.s3.$R.amazonaws.com/$DOC_KEY")
check "anonymous GET from the internet is refused (HTTP status)" "403" "$code"

log "Clean up test objects (developer session)"
aws_sb s3api delete-object --bucket "$DOCS_BUCKET" --key "$DOC_KEY" >/dev/null && ok "deleted s3://$DOCS_BUCKET/$DOC_KEY"
aws_sb s3api delete-object --bucket "$ANALYTICS_BUCKET" --key "$RAW_KEY" >/dev/null && ok "deleted s3://$ANALYTICS_BUCKET/$RAW_KEY"
rm -f "$BODY" "$RENDER_DIR/s3-verify-get.txt"

[ "$fails" = 0 ] || die "$fails check(s) failed"
printf '\n\033[1;32mS3 controls verified.\033[0m Encrypted, private, TLS-only; the analytics role can upload but not read back.\n'
