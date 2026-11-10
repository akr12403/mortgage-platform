#!/usr/bin/env bash
# Markdown summary of a deployment for $GITHUB_STEP_SUMMARY: image tag, terraform result, ECS service state.
#   bash scripts/ci/deploy-summary.sh <env> <image tag> <apply log> >> "$GITHUB_STEP_SUMMARY"
set -uo pipefail
env_name="$1"; tag="$2"; log="$3"
bash "$(dirname "$0")/plan-summary.sh" "Deploy $env_name ($tag)" "$log" "$( grep -q '^Apply complete!' "$log" 2>/dev/null && echo 0 || echo 1 )"
echo
echo "#### ECS services (cluster capstone-mortgage-$env_name)"
echo
echo "| Service | Task definition | Desired | Running | Rollout |"
echo "| --- | --- | ---: | ---: | --- |"
aws ecs describe-services --cluster "capstone-mortgage-$env_name" \
  --services mortgage-service servicing-service analytics-service knowledge-assistant \
  --query 'services[].[serviceName, taskDefinition, desiredCount, runningCount, deployments[?status==`PRIMARY`].rolloutState | [0]]' \
  --output text 2>/dev/null \
  | awk -F'\t' '{ n=split($2, a, "/"); printf "| `%s` | `%s` | %s | %s | %s |\n", $1, a[n], $3, $4, $5 }' \
  || echo "| (could not read the services) | | | | |"
echo
echo "Desired count 0 = deployed but idle (no database yet, see docs/operations/terraform.md). Rollback: docs/operations/runbook.md#rollback."
