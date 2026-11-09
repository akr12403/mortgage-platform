#!/usr/bin/env bash
# Terraform wrapper (M9 Task 9.2): right directory, right account, short-lived credentials, remote state bucket.
#   bash scripts/terraform/tf.sh bootstrap init|plan|apply          # once per account: the state bucket
#   bash scripts/terraform/tf.sh dev init                           # backend = s3://capstone-mortgage-tfstate-<account>
#   bash scripts/terraform/tf.sh dev plan [-out=dev.tfplan] [...]   # any terraform subcommand and flags
#   bash scripts/terraform/tf.sh prod plan                          # test/prod: plan only in the sandbox
# Locally: credentials come from the `aws login --profile capstone-dev` session and live only in this process's
# environment (never written, never printed). In GitHub Actions (part B): from the OIDC role in the job environment.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TF_DIR="$ROOT/infrastructure/terraform"
PROFILE="${AWS_SANDBOX_PROFILE:-capstone-dev}"
REGION="${AWS_SANDBOX_REGION:-us-east-2}"

usage() { echo "usage: $0 <bootstrap|dev|test|prod> <terraform subcommand> [args...]" >&2; exit 2; }
die() { printf '\033[1;31mFAIL\033[0m %s\n' "$*" >&2; exit 1; }

target="${1:-}"; [ $# -ge 2 ] || usage; shift
case "$target" in
  bootstrap)    dir="$TF_DIR/bootstrap" ;;
  dev|test|prod) dir="$TF_DIR/environments/$target" ;;
  *) usage ;;
esac
command -v terraform >/dev/null || die "terraform not found (macOS: brew tap hashicorp/tap && brew install hashicorp/tap/terraform)"
command -v aws >/dev/null || die "AWS CLI v2 not found (brew install awscli)"

# Never LocalStack, always the sandbox Region.
unset AWS_ENDPOINT_URL AWS_ENDPOINT_URL_S3 AWS_ENDPOINT_URL_SNS AWS_ENDPOINT_URL_SQS AWS_ENDPOINT_URL_DYNAMODB
export AWS_REGION="$REGION" AWS_DEFAULT_REGION="$REGION"

if [ -z "${GITHUB_ACTIONS:-}" ]; then
  unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN AWS_PROFILE
  # Works for every credential type the CLI supports (including `aws login`), so Terraform needs no profile support.
  creds="$(aws configure export-credentials --profile "$PROFILE" --format env 2>/dev/null)" \
    || die "No valid AWS session for profile $PROFILE. Run: aws login --profile $PROFILE --region $REGION"
  eval "$creds"
  unset creds
fi
account="$(aws sts get-caller-identity --query Account --output text)" || die "cannot read the caller identity"

sub="$1"; shift
if [ "$sub" = "init" ] && [ "$target" != "bootstrap" ]; then
  exec terraform -chdir="$dir" init -input=false -backend-config="bucket=capstone-mortgage-tfstate-$account" "$@"
fi
exec terraform -chdir="$dir" "$sub" "$@"
