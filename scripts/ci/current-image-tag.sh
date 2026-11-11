#!/usr/bin/env bash
# Print the image tag the environment's ECS services currently run (from the live task definition), or "unset".
#   bash scripts/ci/current-image-tag.sh dev
# Used by plans that are not deployments (PR plans, the nightly drift check, test/prod dry runs), so the plan shows
# infrastructure changes only and not "new image" noise.
set -euo pipefail
env_name="${1:?usage: current-image-tag.sh <env>}"
cluster="capstone-mortgage-$env_name"
td="$(aws ecs describe-services --cluster "$cluster" --services mortgage-service \
        --query 'services[0].taskDefinition' --output text 2>/dev/null || true)"
case "$td" in ""|None) echo unset; exit 0 ;; esac
image="$(aws ecs describe-task-definition --task-definition "$td" \
           --query 'taskDefinition.containerDefinitions[0].image' --output text 2>/dev/null || true)"
case "$image" in *:*) echo "${image##*:}" ;; *) echo unset ;; esac
