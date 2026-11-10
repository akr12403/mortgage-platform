#!/usr/bin/env bash
# M9 Task 9.1 part B: copy the tested, scanned images from GHCR into an environment's ECR repositories (same tag).
#   bash scripts/ci/promote-to-ecr.sh <env> <tag>          # e.g. dev sha-<40-char commit>
# Needs AWS credentials (CI: OIDC deploy role) and a GHCR login. ECR tags are immutable: an existing tag is skipped,
# never overwritten, so a redeploy or rollback of an older tag re-uses exactly the image that was tested.
set -euo pipefail
env_name="${1:?usage: promote-to-ecr.sh <env> <tag>}"
tag="${2:?usage: promote-to-ecr.sh <env> <tag>}"
region="${AWS_REGION:-us-east-2}"
SERVICES="mortgage-service servicing-service analytics-service knowledge-assistant"

account="$(aws sts get-caller-identity --query Account --output text)"
[ -n "${GITHUB_ACTIONS:-}" ] && echo "::add-mask::$account"
registry="$account.dkr.ecr.$region.amazonaws.com"
src_prefix="$(printf '%s' "${IMAGE_PREFIX:-ghcr.io/${GITHUB_REPOSITORY:?set IMAGE_PREFIX or GITHUB_REPOSITORY}}" | tr '[:upper:]' '[:lower:]')"

aws ecr get-login-password --region "$region" | docker login --username AWS --password-stdin "$registry" >/dev/null

for s in $SERVICES; do
  repo="capstone-mortgage-$env_name/$s"
  if aws ecr describe-images --region "$region" --repository-name "$repo" --image-ids "imageTag=$tag" >/dev/null 2>&1; then
    echo "  $repo:$tag already in ECR (immutable), skipped"
    continue
  fi
  # CI builds linux/amd64; --platform also makes this work on an Apple-silicon laptop (local deploy).
  docker pull -q --platform linux/amd64 "$src_prefix/$s:$tag" >/dev/null
  docker tag "$src_prefix/$s:$tag" "$registry/$repo:$tag"
  docker push -q "$registry/$repo:$tag" >/dev/null
  echo "  $repo:$tag pushed"
done
