#!/usr/bin/env bash
# M8 Task 8.2: create or harden the two S3 buckets (idempotent).
#   aws login --profile capstone-dev --region us-east-2
#   bash scripts/aws/s3-apply.sh
#   bash scripts/aws/s3-verify.sh       # configuration checks + live allow/deny tests
# Every bucket gets: Block Public Access (all four settings), Object Ownership = BucketOwnerEnforced (ACLs off),
# default encryption SSE-S3 (AES256), a bucket policy that denies plain HTTP and TLS < 1.2, a dev lifecycle rule,
# and the standard tags. Bucket names: infrastructure/aws/resources.conf.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

log "Session"
require_session

OUT="$RENDER_DIR/s3"
mkdir -p "$OUT"
TAGSET=$(python3 -c 'import json,sys; print(json.dumps({"TagSet":[{"Key":k,"Value":v} for k,v in zip(sys.argv[1::2],sys.argv[2::2])]}))' \
  Project "$TAG_PROJECT" Environment "$TAG_ENVIRONMENT" Team "$TAG_TEAM")
ENCRYPTION='{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"},"BucketKeyEnabled":false}]}'
PUBLIC_BLOCK='BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true'

apply_bucket() {  # apply_bucket NAME LIFECYCLE_TEMPLATE
  local bucket="$1" lifecycle="$2" out
  log "s3://$bucket"
  if out=$(aws_sb s3api head-bucket --bucket "$bucket" 2>&1); then
    ok "exists in this account"
  else
    case "$out" in
      *"Not Found"*|*404*)
        aws_sb s3api create-bucket --bucket "$bucket" \
          --create-bucket-configuration "LocationConstraint=$AWS_SANDBOX_REGION" >/dev/null
        aws_sb s3api wait bucket-exists --bucket "$bucket"
        ok "created in $AWS_SANDBOX_REGION" ;;
      *) die "$bucket is owned by another AWS account. Change its name in infrastructure/aws/resources.conf, then re-run iam-apply.sh and this script." ;;
    esac
  fi

  aws_sb s3api put-public-access-block --bucket "$bucket" --public-access-block-configuration "$PUBLIC_BLOCK"
  ok "Block Public Access: all four settings on"
  aws_sb s3api put-bucket-ownership-controls --bucket "$bucket" \
    --ownership-controls 'Rules=[{ObjectOwnership=BucketOwnerEnforced}]'
  ok "Object Ownership: BucketOwnerEnforced (ACLs disabled)"
  aws_sb s3api put-bucket-encryption --bucket "$bucket" --server-side-encryption-configuration "$ENCRYPTION"
  ok "default encryption: SSE-S3 (AES256)"

  export BUCKET="$bucket"
  render "$AWS_INFRA_DIR/s3/bucket-policy.json" "$OUT/$bucket-policy.json"
  aws_sb s3api put-bucket-policy --bucket "$bucket" --policy "file://$OUT/$bucket-policy.json"
  ok "bucket policy: deny non-TLS and TLS < 1.2"

  render "$AWS_INFRA_DIR/s3/$lifecycle" "$OUT/$bucket-lifecycle.json"
  aws_sb s3api put-bucket-lifecycle-configuration --bucket "$bucket" \
    --lifecycle-configuration "file://$OUT/$bucket-lifecycle.json" >/dev/null
  ok "lifecycle: $(python3 -c 'import json,sys; print(", ".join(r["ID"] for r in json.load(open(sys.argv[1]))["Rules"]))' "$OUT/$bucket-lifecycle.json")"

  aws_sb s3api put-bucket-tagging --bucket "$bucket" --tagging "$TAGSET"
  ok "tags: Project=$TAG_PROJECT Environment=$TAG_ENVIRONMENT Team=$TAG_TEAM"
}

apply_bucket "$DOCS_BUCKET" lifecycle-docs.json
apply_bucket "$ANALYTICS_BUCKET" lifecycle-analytics.json

printf '\n\033[1;32mS3 applied.\033[0m Next: bash scripts/aws/s3-verify.sh\n'
