#!/usr/bin/env bash
# M9 Task 9.2 drift detection mini exercise (dev): manual change -> plan shows the diff -> remediate via code.
#   bash scripts/terraform/drift-demo.sh          # asks before each AWS change
#   bash scripts/terraform/drift-demo.sh --yes    # no prompts
# Two "console hotfixes" an operator might make:
#   1. Lambda capstone-mortgage-doc-processor-dev memory 256 -> 512 MB    (configuration drift)
#   2. AWS managed policy AmazonS3ReadOnlyAccess attached to mortgage-api-role (least-privilege drift, M8 Task 8.1)
# Then: terraform plan -detailed-exitcode must return 2 (changes) and name both; terraform apply puts the code's
# values back; a final plan must return 0. Plans are saved to reports/terraform/ (git-ignored: they contain ARNs).
# Write-up: docs/operations/terraform-drift-exercise.md
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../aws/lib.sh"
TF="bash $REPO_ROOT/scripts/terraform/tf.sh dev"
OUT="$REPO_ROOT/reports/terraform"; mkdir -p "$OUT"
YES=0; [ "${1:-}" = "--yes" ] && YES=1
ROGUE_POLICY_ARN="arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess"
ROLE=mortgage-api-role

confirm() { [ "$YES" = 1 ] && return 0; read -r -p "  $1 [y/N] " a; [ "$a" = y ] || die "aborted"; }
plan() {  # plan FILE -> prints Terraform's exit code (0 no changes, 2 changes); 1 = error -> exit
  local rc=0
  $TF plan -input=false -no-color -lock-timeout=60s -detailed-exitcode > "$1" 2>&1 || rc=$?
  [ "$rc" = 1 ] && { tail -30 "$1" >&2; die "terraform plan failed (see $1)"; }
  echo "$rc"
}

log "Session"
require_session

log "0. Baseline: dev must match the code before the exercise"
rc=$(plan "$OUT/drift-0-baseline.txt")
[ "$rc" = 0 ] || die "dev already has pending changes (exit $rc). Run: bash scripts/terraform/tf.sh dev apply   then re-run"
ok "no changes (exit 0)"

log "1. Manual changes outside Terraform (simulated console hotfix)"
confirm "Set $LAMBDA_FUNCTION memory to 512 MB and attach AmazonS3ReadOnlyAccess to $ROLE?"
aws_sb lambda update-function-configuration --function-name "$LAMBDA_FUNCTION" --memory-size 512 >/dev/null
aws_sb lambda wait function-updated-v2 --function-name "$LAMBDA_FUNCTION"
ok "Lambda memory 256 -> 512 MB"
aws_sb iam attach-role-policy --role-name "$ROLE" --policy-arn "$ROGUE_POLICY_ARN"
ok "$ROLE: attached $ROGUE_POLICY_ARN"

log "2. Detect: terraform plan"
rc=$(plan "$OUT/drift-1-detected.txt")
[ "$rc" = 2 ] || die "expected exit 2 (drift), got $rc"
grep -E 'memory_size|policy_arns|AmazonS3ReadOnlyAccess|will be updated in-place|Plan:' "$OUT/drift-1-detected.txt" | sed 's/^/    /'
grep -q 'memory_size' "$OUT/drift-1-detected.txt" || die "plan does not show the Lambda memory drift"
grep -q 'AmazonS3ReadOnlyAccess' "$OUT/drift-1-detected.txt" || die "plan does not show the attached policy"
ok "drift detected (exit 2): Lambda memory and the extra managed policy"

log "3. Remediate via code: terraform apply"
confirm "Apply the code's values (memory 256 MB, no managed policies on $ROLE)?"
$TF apply -input=false -auto-approve -lock-timeout=60s -no-color > "$OUT/drift-2-apply.txt" 2>&1 \
  || { tail -30 "$OUT/drift-2-apply.txt" >&2; die "apply failed"; }
grep -E '^Apply complete' "$OUT/drift-2-apply.txt" | sed 's/^/    /'

log "4. Verify"
rc=$(plan "$OUT/drift-3-after.txt")
[ "$rc" = 0 ] || die "still drifting after apply (exit $rc), see $OUT/drift-3-after.txt"
mem=$(aws_sb lambda get-function-configuration --function-name "$LAMBDA_FUNCTION" --query MemorySize --output text)
attached=$(aws_sb iam list-attached-role-policies --role-name "$ROLE" --query 'length(AttachedPolicies)' --output text)
[ "$mem" = 256 ] && [ "$attached" = 0 ] || die "unexpected state: memory $mem MB, $attached managed policies"
ok "plan clean (exit 0); Lambda memory $mem MB; $ROLE has $attached managed policies"

printf '\n\033[1;32mDrift exercise complete.\033[0m Plans: %s/drift-*.txt\n' "${OUT#$REPO_ROOT/}"
