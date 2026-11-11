#!/usr/bin/env bash
# M9 Task 9.1 part B: deploy (or roll back) dev from a laptop with the developer session. The same steps as the CI
# job deploy-dev, which can't run in the sandbox (its SCP denies the GitHub OIDC provider; no access keys by policy).
#   aws login --profile capstone-dev --region us-east-2
#   bash scripts/deploy/deploy-dev.sh                 # newest develop commit with a green ci run
#   bash scripts/deploy/deploy-dev.sh sha-<commit>    # a specific tested image: deploy or ROLLBACK
#   bash scripts/deploy/deploy-dev.sh sha-<commit> --yes
# Steps: 1) check the tag passed ci  2) copy the 4 images GHCR -> dev ECR (no rebuild; immutable tags)
#        3) terraform plan with that image_tag  4) apply exactly that plan after you confirm  5) summary
# Needs: gh (logged in, scope read:packages), Docker running, AWS CLI v2, Terraform.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
die() { printf '\033[1;31mFAIL\033[0m %s\n' "$*" >&2; exit 1; }
step() { printf '\n\033[1;36m== %s ==\033[0m\n' "$*"; }

tag=""; yes=0
for a in "$@"; do case "$a" in --yes) yes=1 ;; *) tag="$a" ;; esac; done
for c in gh docker aws terraform; do command -v "$c" >/dev/null || die "$c not found"; done
docker info >/dev/null 2>&1 || die "Docker is not running"

step "1. Image tag"
repo="$(gh repo view --json nameWithOwner -q .nameWithOwner)"
if [ -z "$tag" ]; then
  sha="$(gh run list --repo "$repo" --workflow ci --branch develop --event push --status success -L 1 --json headSha -q '.[0].headSha')"
  [ -n "$sha" ] || die "no green ci run on develop found"
  tag="sha-$sha"
fi
case "$tag" in sha-[0-9a-f]*|[0-9]*.[0-9]*.[0-9]*) ;; *) die "tag must be sha-<40-char commit> or a semver" ;; esac
if [ "${tag#sha-}" != "$tag" ]; then
  green="$(gh run list --repo "$repo" --workflow ci --commit "${tag#sha-}" --status success -L 1 --json databaseId -q 'length')"
  [ "$green" = 1 ] || die "$tag has no green ci run: only tested images are deployed"
fi
echo "  $tag (green ci run on $repo)"

step "2. Copy the tested images to dev's ECR"
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN AWS_PROFILE AWS_ENDPOINT_URL
creds="$(aws configure export-credentials --profile capstone-dev --format env 2>/dev/null)" \
  || die "No valid AWS session. Run: aws login --profile capstone-dev --region us-east-2"
eval "$creds"; unset creds
export AWS_REGION=us-east-2 AWS_DEFAULT_REGION=us-east-2
gh auth token | docker login ghcr.io -u "$(gh api user -q .login)" --password-stdin >/dev/null 2>&1 \
  || die "GHCR login failed"
IMAGE_PREFIX="ghcr.io/$repo" bash scripts/ci/promote-to-ecr.sh dev "$tag" \
  || die "copy failed. If GHCR denied the pull, give gh the package scope once: gh auth refresh -h github.com -s read:packages"

step "3. terraform plan (dev, image_tag=$tag)"
plan_dir="$(mktemp -d)"; trap 'rm -rf "$plan_dir"' EXIT
bash scripts/terraform/tf.sh dev init -no-color >/dev/null
bash scripts/terraform/tf.sh dev plan -input=false -no-color -lock-timeout=120s -var "image_tag=$tag" -out="$plan_dir/dev.tfplan" > "$plan_dir/plan.txt" 2>&1 \
  || { tail -40 "$plan_dir/plan.txt"; die "plan failed"; }
grep -E '^  # .* (will be|must be)|^Plan:|^No changes' "$plan_dir/plan.txt" | sed -E 's/[0-9]{12}/<account>/g'
# A new image always replaces the task definitions (they are immutable: new revision, old one deregistered);
# anything else being replaced or destroyed deserves a careful read.
grep -E 'must be replaced|will be destroyed' "$plan_dir/plan.txt" | grep -qv 'aws_ecs_task_definition' && printf '\n  \033[1;33mWARN\033[0m the plan replaces or destroys resources: read it before confirming (%s)\n' "$plan_dir/plan.txt"

step "4. Apply"
if grep -q '^No changes' "$plan_dir/plan.txt"; then
  echo "  nothing to apply: dev already runs $tag"
else
  if [ "$yes" != 1 ]; then read -r -p "  Apply this plan to dev? [y/N] " a; [ "$a" = y ] || die "aborted, nothing applied"; fi
  bash scripts/terraform/tf.sh dev apply -input=false -no-color -lock-timeout=120s "$plan_dir/dev.tfplan" > "$plan_dir/apply.txt" 2>&1 \
    || { tail -40 "$plan_dir/apply.txt"; die "apply failed: see docs/operations/runbook.md#when-the-deployment-itself-fails"; }
fi

step "5. Result"
touch "$plan_dir/apply.txt"; grep -q '^No changes' "$plan_dir/plan.txt" && echo "Apply complete! Resources: 0 added, 0 changed, 0 destroyed." > "$plan_dir/apply.txt"
bash scripts/ci/deploy-summary.sh dev "$tag" "$plan_dir/apply.txt" | sed -n '/^\*\*/p;/^#### ECS/,$p'
