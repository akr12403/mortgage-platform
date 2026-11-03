# Shared helpers for the M8 AWS scripts (sourced, not executed). Bash 3.2+ (macOS default) and python3.
#   source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
# Credentials: the developer's short-lived `aws login` session (profile capstone-dev). No access keys anywhere.

AWS_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$AWS_LIB_DIR/../.." && pwd)"
AWS_INFRA_DIR="$REPO_ROOT/infrastructure/aws"
IAM_DIR="$AWS_INFRA_DIR/iam"
RENDER_DIR="$REPO_ROOT/reports/aws"   # git-ignored (reports/): rendered policies contain the account id

# These scripts always target the real sandbox: never LocalStack, never keys from the environment.
unset AWS_ENDPOINT_URL AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN

log()  { printf '\n\033[1;36m== %s ==\033[0m\n' "$*"; }
ok()   { printf '  \033[1;32mOK\033[0m   %s\n' "$*"; }
warn() { printf '  \033[1;33mWARN\033[0m %s\n' "$*"; }
err()  { printf '  \033[1;31mFAIL\033[0m %s\n' "$*" >&2; }
die()  { err "$*"; exit 1; }

# KEY=value lines from resources.conf; a variable already set in the environment wins.
load_resources() {
  local key value
  while IFS='=' read -r key value; do
    case "$key" in ''|\#*) continue ;; esac
    if [ -z "${!key:-}" ]; then export "$key=$value"; else export "$key"; fi
  done < "$AWS_INFRA_DIR/resources.conf"
  export REGION="$AWS_SANDBOX_REGION"
}

aws_sb() { aws --profile "$AWS_SANDBOX_PROFILE" --region "$AWS_SANDBOX_REGION" "$@"; }

# Sets ACCOUNT_ID, CALLER_ARN and DEV_PRINCIPAL_ARN (the IAM role behind the developer's console session).
require_session() {
  command -v aws >/dev/null || die "AWS CLI v2 not found (brew install awscli)"
  command -v python3 >/dev/null || die "python3 not found"
  local ident
  if ! ident=$(aws_sb sts get-caller-identity --query '[Account,Arn]' --output text 2>&1); then
    die "No valid AWS session for profile $AWS_SANDBOX_PROFILE. Run: aws login --profile $AWS_SANDBOX_PROFILE --region $AWS_SANDBOX_REGION"
  fi
  ACCOUNT_ID=$(printf '%s' "$ident" | awk '{print $1}')
  CALLER_ARN=$(printf '%s' "$ident" | awk '{print $2}')
  export ACCOUNT_ID CALLER_ARN
  if [ -z "${DEV_PRINCIPAL_ARN:-}" ]; then
    case "$CALLER_ARN" in
      arn:aws:sts::*:assumed-role/*)
        local role_name
        role_name=$(printf '%s' "$CALLER_ARN" | cut -d/ -f2)
        DEV_PRINCIPAL_ARN=$(aws_sb iam get-role --role-name "$role_name" --query Role.Arn --output text) ;;
      arn:aws:iam::*:user/*) DEV_PRINCIPAL_ARN="$CALLER_ARN" ;;
      *) die "Unexpected caller $CALLER_ARN: set DEV_PRINCIPAL_ARN to the role or user that may assume the app roles" ;;
    esac
  fi
  export DEV_PRINCIPAL_ARN
  printf '  account %s  region %s  caller %s\n' "$ACCOUNT_ID" "$AWS_SANDBOX_REGION" "$CALLER_ARN"
}

# render TEMPLATE OUT: substitute ${VAR} from the environment; any unknown ${VAR} is an error.
render() {
  mkdir -p "$(dirname "$2")"
  python3 - "$1" "$2" <<'PY'
import json, os, string, sys
src, out = sys.argv[1], sys.argv[2]
text = string.Template(open(src).read()).substitute(os.environ)
doc = json.loads(text)
doc = {k: v for k, v in doc.items() if not k.startswith("_")}
with open(out, "w") as f:
    json.dump(doc, f, indent=2)
PY
}

# Role manifest as "name|trust|policy|description" lines.
roles() {
  python3 - "$IAM_DIR/roles.json" <<'PY'
import json, sys
for r in json.load(open(sys.argv[1]))["roles"]:
    print("|".join([r["name"], r["trust"], r["policy"], r["description"]]))
PY
}

tag_args() {
  printf '%s\n' "Key=Project,Value=$TAG_PROJECT" "Key=Environment,Value=$TAG_ENVIRONMENT" "Key=Team,Value=$TAG_TEAM"
}

load_resources
