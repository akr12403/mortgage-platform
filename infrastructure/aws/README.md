# infrastructure/aws (M8)

AWS sandbox definitions for Milestone 8. Resources are created by the scripts in `scripts/aws/`, which are idempotent and run from the repo root. Terraform replaces these scripts in M9.

| Path | What it holds |
| --- | --- |
| `resources.conf` | Resource names, Region, profile and tags. There are no secrets and no account id. |
| `iam/roles.json` | One entry per workload role: its trust policy and its permission policy |
| `iam/policies/*.json` | Least-privilege permission policies (templates using `${ACCOUNT_ID}`, `${REGION}` and resource names) |
| `iam/trust/*.json` | Who may assume each role |
| `iam/exercise/` | The over-permissioned "before" policy for the Task 8.1 mini exercise. It is never applied. |

Role-by-role detail: [docs/architecture/aws-iam-matrix.md](../../docs/architecture/aws-iam-matrix.md).

## Prerequisites (once)

- AWS CLI v2, version 2.32.0 or later (`brew install awscli`), and `python3`.
- The sandbox project's Region is `us-east-2`:

  ```bash
  aws configure set region us-east-2 --profile capstone-dev
  ```

There are no access keys. Each session starts with:

```bash
aws login --profile capstone-dev --region us-east-2      # browser sign-in; credentials last up to 12 h
aws sts get-caller-identity --profile capstone-dev
```

The scripts always use profile `capstone-dev` in `us-east-2`. They ignore `AWS_ENDPOINT_URL` (LocalStack) and any key variables in your shell. `.env` and docker compose keep pointing at LocalStack in `us-east-1`, so the local stack is unaffected.

## Commands

```bash
python3 tests/security/test_iam_policies.py   # static least-privilege guard (no AWS needed, also runs in CI)
bash scripts/aws/iam-apply.sh                 # validate (IAM Access Analyzer) + create/update the roles
bash scripts/aws/iam-verify.sh                # policy simulator: 39 allow/deny cases must match
bash scripts/aws/teardown.sh                  # delete everything M8 created (asks first; --yes to skip)
```

Rendered policies, which contain the account id, are written to `reports/aws/`. That folder is git-ignored.

## Cost

The sandbox is on the AWS Free plan, so it cannot be charged. Credits and the plan end date are shown in the console account menu. Still, run `teardown.sh` when M8 is signed off.
