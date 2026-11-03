#!/usr/bin/env bash
# M8 Task 8.1: create or update the least-privilege IAM roles in infrastructure/aws/iam/roles.json (idempotent).
#   aws login --profile capstone-dev --region us-east-2     # short-lived console session, no access keys
#   bash scripts/aws/iam-apply.sh
#   bash scripts/aws/iam-verify.sh                          # prove allow/deny with the IAM policy simulator
# Each role gets: its trust policy, ONE inline policy (<role>-policy), the standard tags, 1 h max session.
# Policies are rendered from templates into reports/aws/iam/ (git-ignored) and checked by IAM Access Analyzer first.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

log "Session"
require_session

log "Render templates"
OUT="$RENDER_DIR/iam"
rm -rf "$OUT"
for f in "$IAM_DIR"/trust/*.json "$IAM_DIR"/policies/*.json; do
  rel="${f#$IAM_DIR/}"
  render "$f" "$OUT/$rel"
done
ok "rendered $(find "$OUT" -name '*.json' | wc -l | tr -d ' ') documents into ${OUT#$REPO_ROOT/}"

log "Validate with IAM Access Analyzer (errors and security warnings fail the run)"
validate() {  # validate FILE POLICY_TYPE [RESOURCE_TYPE]
  local extra=() findings
  [ -n "${3:-}" ] && extra=(--validate-policy-resource-type "$3")
  if ! findings=$(aws_sb accessanalyzer validate-policy --policy-type "$2" ${extra[@]+"${extra[@]}"} \
        --policy-document "file://$1" --query 'findings[].[findingType,issueCode]' --output text 2>&1); then
    warn "validate-policy not available here ($(printf '%s' "$findings" | head -1)); relying on tests/security/test_iam_policies.py"
    return 0
  fi
  if printf '%s' "$findings" | grep -Eq '^(ERROR|SECURITY_WARNING)'; then
    err "${1#$OUT/}:"; printf '%s\n' "$findings" | sed 's/^/         /' >&2; return 1
  fi
  if [ -n "$findings" ]; then warn "${1#$OUT/}: $(printf '%s' "$findings" | tr '\t\n' ' ;')"; else ok "${1#$OUT/}"; fi
}
failed=0
for f in "$OUT"/policies/*.json; do validate "$f" IDENTITY_POLICY || failed=1; done
for f in "$OUT"/trust/*.json; do validate "$f" RESOURCE_POLICY AWS::IAM::AssumeRolePolicyDocument || failed=1; done
[ "$failed" = 0 ] || die "fix the findings above, then re-run"

log "S3 bucket names (global namespace; buckets themselves are created in Task 8.2)"
check_bucket() {
  local out
  if out=$(aws_sb s3api head-bucket --bucket "$1" 2>&1); then ok "$1 exists in this account"; return; fi
  case "$out" in
    *"Not Found"*|*404*) ok "$1 is free" ;;
    *) warn "$1 belongs to another AWS account ($(printf '%s' "$out" | tail -1)). Pick another name in infrastructure/aws/resources.conf (e.g. add your initials) and re-run." ;;
  esac
}
check_bucket "$DOCS_BUCKET"
check_bucket "$ANALYTICS_BUCKET"

log "Roles"
TAGS=()
while IFS= read -r t; do TAGS+=("$t"); done < <(tag_args)
while IFS='|' read -r name trust policy description <&3; do
  trust_file="$OUT/$trust"; policy_file="$OUT/$policy"
  if aws_sb iam get-role --role-name "$name" >/dev/null 2>&1; then
    aws_sb iam update-assume-role-policy --role-name "$name" --policy-document "file://$trust_file"
    aws_sb iam update-role --role-name "$name" --description "$description" --max-session-duration 3600
    aws_sb iam tag-role --role-name "$name" --tags "${TAGS[@]}"
    state="updated"
  else
    aws_sb iam create-role --role-name "$name" --description "$description" --max-session-duration 3600 \
      --assume-role-policy-document "file://$trust_file" --tags "${TAGS[@]}" >/dev/null
    state="created"
  fi
  aws_sb iam put-role-policy --role-name "$name" --policy-name "$name-policy" --policy-document "file://$policy_file"
  # Exactly one inline policy and no managed policies: everything the role can do is in the repo.
  for stale in $(aws_sb iam list-role-policies --role-name "$name" --query 'PolicyNames' --output text); do
    [ "$stale" = "$name-policy" ] || { aws_sb iam delete-role-policy --role-name "$name" --policy-name "$stale"; warn "$name: removed stale inline policy $stale"; }
  done
  attached=$(aws_sb iam list-attached-role-policies --role-name "$name" --query 'AttachedPolicies[].PolicyArn' --output text)
  [ -z "$attached" ] || warn "$name has managed policies attached outside this script: $attached"
  ok "$name $state (trust ${trust#trust/}, policy $name-policy)"
done 3< <(roles)

printf '\n\033[1;32mIAM applied.\033[0m Next: bash scripts/aws/iam-verify.sh (IAM changes can take ~10 s to propagate).\n'
