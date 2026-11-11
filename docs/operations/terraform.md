# Terraform (M9 Task 9.2)

Terraform defines the AWS side of the platform in [`infrastructure/terraform/`](../../infrastructure/terraform/):
- the five modules from the handbook;
- three environments built from the same modules;
- remote state in S3 with locking.

The M8 resources aren't rebuilt. Terraform **imports** them into `dev`, and the M8 policy and table templates in `infrastructure/aws/` remain the single source of truth that both Terraform and the M8 scripts read.

```text
infrastructure/terraform/
├── bootstrap/            state bucket (run once per account, local state)
├── modules/
│   ├── networking/       VPC, 2 public subnets, internet gateway, default SG locked down (no NAT gateway)
│   ├── security/         the 5 M8 IAM roles (from infrastructure/aws/iam), ECS execution role, ECS task SG
│   ├── storage/          the 2 S3 buckets (hardening from infrastructure/aws/s3), 2 DynamoDB tables
│   ├── compute/          document Lambda + S3 trigger + alarm, Glue job + failure alert, ECR, ECS Fargate
│   └── messaging/        SNS lifecycle topic -> 2 SQS queues + DLQs (the M5 topology on real AWS)
└── environments/
    ├── dev/              applied in the sandbox; imports.tf adopts the M8 resources
    ├── test/             plan only
    └── prod/             plan only (CI: manual approval, Task 9.1 part B)
```

## Design decisions

| Decision | Why |
| --- | --- |
| Policies and table definitions are read from `infrastructure/aws/*.json` with `templatefile()` | There is one definition of least privilege. `tests/security/test_iam_policies.py`, the IAM policy simulator (`iam-verify.sh`) and Terraform all check or apply the same files. |
| `aws_iam_role_policies_exclusive` and `aws_iam_role_policy_attachments_exclusive` | Each role has exactly one inline policy and no managed policies, the same rule `iam-apply.sh` enforced. A policy attached in the console shows up as drift, as the [drift exercise](terraform-drift-exercise.md) demonstrates. |
| Environments differ only in `terraform.tfvars` and `backend.tf` | `main.tf`, `variables.tf`, `outputs.tf` and `versions.tf` are identical in all three, and a CI test checks this, so test and prod can't drift from dev in code. |
| dev names equal the M8 names | They are checked against `infrastructure/aws/resources.conf`, so the import adopts the existing resources. test and prod get `-test` / `-prod` suffixes, including on IAM role names, so all three can live in one account. |
| ECS Fargate, `desired_count = 0`, no load balancer, no NAT gateway | Idle cost is close to zero (see [cost](#cost)). Tasks get a public IP to reach ECR and the AWS APIs. Inbound traffic is closed unless you pass your own IP with `-var` for a demo; `0.0.0.0/0` is rejected. |
| No RDS | The handbook allows "RDS or EC2/ECS placeholder". `database_host` is the placeholder, and the services stay at 0 tasks until a database exists. |
| Secrets are SSM SecureString parameters under `/capstone-mortgage/<env>/`, created outside Terraform | The values never enter the Terraform state or Git. The execution role may read only its own environment's path. |
| ECS deployment circuit breaker with rollback | A deployment whose tasks never become healthy rolls back to the last working task definition by itself. Part B's rollback runbook builds on this. |
| Account id never committed | It comes from `aws_caller_identity` at plan time. The state bucket name includes it, so it's passed at `init`. |

## Prerequisites (once)

```bash
brew tap hashicorp/tap && brew install hashicorp/tap/terraform   # 1.10 or later
terraform version
aws login --profile capstone-dev --region us-east-2              # same short-lived session as M8
```

`scripts/terraform/tf.sh` runs every command. It works as follows:
- **Directory:** it picks the right one (`bootstrap`, `dev`, `test` or `prod`).
- **Credentials:** it pins `us-east-2`, ignores LocalStack variables and gets short-lived credentials from your `aws login` session. They live only in that process's environment.
- **State bucket:** at `init` it passes `capstone-mortgage-tfstate-<account>` as the backend bucket.

## First run: bootstrap, import, apply

```bash
# 1. State bucket (versioned, encrypted, TLS-only, public access blocked). Local state, git-ignored.
bash scripts/terraform/tf.sh bootstrap init
bash scripts/terraform/tf.sh bootstrap apply

# 2. dev: connect to the remote state, then review the import plan
bash scripts/terraform/tf.sh dev init
bash scripts/terraform/tf.sh dev validate
bash scripts/terraform/tf.sh dev plan -out=dev.tfplan

# 3. apply exactly the plan you reviewed
bash scripts/terraform/tf.sh dev apply dev.tfplan

# 4. commit the provider lock file that init created (pins provider versions and checksums)
git add infrastructure/terraform/environments/*/.terraform.lock.hcl infrastructure/terraform/bootstrap/.terraform.lock.hcl
```

**Expected first plan for dev.** The summary line reads roughly `Plan: ~50 to import, ~40 to add, ~15 to change, 0 to destroy`.
- **Import:** the 5 roles with their policies, both buckets and their 5 settings each, both tables, the Lambda, its log group, permission, trigger and alarm, the Glue job, its 2 assets and 3 log groups, the alert rule, target and log policy.
- **Add:** the VPC, the messaging topology, ECR, the ECS cluster, task definitions and services, and the ECS execution role. None of these existed in M8.
- **Change:**
  - the new `ManagedBy = terraform` tag;
  - the ECS trust statement on the three app roles;
  - `force_destroy` on the buckets (Terraform only, not an AWS change);
  - the Lambda code hash: Terraform zips `handler.py` itself, so the same code gets a new hash.
- **`0 to destroy` and no `must be replaced`.** If either appears, stop and look before applying.

**test / prod (plan only):**

```bash
bash scripts/terraform/tf.sh test init && bash scripts/terraform/tf.sh test plan
bash scripts/terraform/tf.sh prod init && bash scripts/terraform/tf.sh prod plan
```

Both show only `to add`, since nothing exists for them. On 2026-11-09 both showed `Plan: 90 to add, 0 to change, 0 to destroy`. That's dev's 92 resources minus the two account-wide Glue log groups, which only dev manages. They're never applied in the sandbox. In CI (part B), prod gets this plan behind a manual approval.

## Everyday use

| Task | Command |
| --- | --- |
| See what would change | `bash scripts/terraform/tf.sh dev plan` |
| Check for drift (exit 2 = drift) | `bash scripts/terraform/tf.sh dev plan -detailed-exitcode` |
| Demo: run the services | Create the SSM secrets (below), then `bash scripts/terraform/tf.sh dev apply -var desired_count=1 -var image_tag=sha-<commit> -var 'allowed_ingress_cidrs=["<your-ip>/32"]'` |
| Back to idle | `bash scripts/terraform/tf.sh dev apply -var desired_count=0` |
| Outputs (queue URLs, ECR URLs, …) | `bash scripts/terraform/tf.sh dev output` |
| Remove everything from dev | `bash scripts/terraform/tf.sh dev destroy`. This replaces `scripts/aws/teardown.sh`; the state bucket stays. |

Secrets for a demo are created once per environment with the AWS CLI, never with Terraform. Type each value at the prompt so it doesn't go into your shell history:

```bash
for name in JWT_SECRET POSTGRES_PASSWORD AUTH_SEED_PASSWORD LLM_API_KEY; do
  read -rs -p "$name: " value; echo
  aws ssm put-parameter --profile capstone-dev --region us-east-2 --name "/capstone-mortgage/dev/$name" \
    --type SecureString --value "$value" --overwrite >/dev/null
done
```

The images must be in the environment's ECR repositories first. The part B deploy job copies the tested `sha-<commit>` images from GHCR.

## M8 scripts after the import

| M8 script | Now |
| --- | --- |
| `iam-apply.sh`, `s3-apply.sh`, `lambda-deploy.sh`, `lookup-deploy.sh`, `pipeline-deploy.sh` | **Don't run against dev any more.** Terraform owns those resources, so a script change would show up as drift and be reverted. They stay in the repo as the M8 record. |
| `iam-verify.sh`, `s3-verify.sh`, `lambda-verify.sh`, `pipeline-run.sh`, `reconcile.sh`, `lookup-load.sh`, `compose-aws-up.sh` | Still used. They only read or exercise the resources, so they work the same on the Terraform-managed ones. |
| `teardown.sh` | Replaced by `tf.sh dev destroy` |

## CI

**Sandbox status:** CI can't reach AWS, because the SCP denies the GitHub OIDC provider. In CI, `infra.yml` runs `fmt` and `validate` only. Plans, applies and the drift check run locally with `tf.sh`, and deploys with [`scripts/deploy/deploy-dev.sh`](../../scripts/deploy/deploy-dev.sh). The table describes the CI path, which a single flag enables ([cicd.md](cicd.md#deploy-part-b)).

| When | What runs | Role |
| --- | --- | --- |
| PR changing `infrastructure/**`, `scripts/terraform/**` or `infra.yml` | `fmt -check`, `validate` (no AWS), then `plan` for dev, test and prod, summarized in the run | `capstone-mortgage-ci-plan` (read-only) |
| Push to `develop` | `ci / deploy-dev`: images to ECR, then `apply` dev with the new `image_tag` | `capstone-mortgage-ci-deploy-dev` |
| Nightly | `infra / drift check (dev)`: `plan -detailed-exitcode`. Exit 2 fails the run. | plan role |
| Manual | test plan, prod dry run, dev apply (rollback/redeploy) | plan role, or the deploy role for a dev apply |

CI plans use the image tag that's already running (`scripts/ci/current-image-tag.sh`), so they show infrastructure changes only. The roles, the OIDC provider and the state bucket are in `bootstrap/` and are applied only from the developer session. Details are in [cicd.md](cicd.md#aws-access-from-ci).

## State and locking

- **Location:** `s3://capstone-mortgage-tfstate-<account>/mortgage-platform/<env>/terraform.tfstate`. Each environment has its own key.
- **Locking:** S3-native, with `use_lockfile = true`. A second `plan` or `apply` waits for, or fails on, the `<key>.tflock` object, so two people or a person and CI can't write the state at the same time. `-lock-timeout=60s` waits instead of failing.
- **Versioning:** every state write is kept for 30 days. To roll back a bad state, restore the previous object version in S3.
- **Never in Git.** `.gitignore` covers `*.tfstate*`, `.terraform/`, `*.tfplan` and `.build/`. The state holds resource ARNs and the account id, but no secrets, since there are no Terraform-managed secret values.

## Cost

| While | What costs | About |
| --- | --- | --- |
| Idle (`desired_count = 0`) | ECR storage (4 images × ~200 MB), S3 state and objects, CloudWatch Logs, on-demand DynamoDB, SNS/SQS/Lambda requests | under $0.20 / month |
| Demo (`desired_count = 1`) | Fargate: 2 × (0.5 vCPU, 1 GB) + 2 × (0.25 vCPU, 0.5 GB), plus 4 public IPv4 addresses | about $0.10 / hour |
| Never | NAT gateway, load balancer, RDS, interface VPC endpoints, Container Insights | |

Everything is charged against the sandbox credits ($100, Free plan). The account can't be billed beyond them.

## Deviations from the handbook

| Handbook | Implemented | Why |
| --- | --- | --- |
| Remote state "S3 + DynamoDB lock" | S3 with native locking (`use_lockfile`), no DynamoDB lock table | Terraform 1.10 added S3-native locking, and DynamoDB locking for the S3 backend is deprecated. One fewer resource, and the same guarantee. |
| "RDS or EC2/ECS placeholder" | ECS Fargate services at `desired_count = 0`, with database host as a placeholder | Keeps idle cost near zero (decision recorded in M9 planning) |
| plan/apply for every environment from CI | dev: plan on PRs, apply on every `develop` push (CI); test and prod: plan-only, manual | One sandbox account with limited credits. The identical-definition test makes a test or prod apply a tfvars change, not a code change. |

Related:
- [drift exercise](terraform-drift-exercise.md)
- [CI/CD](cicd.md): the deploy jobs are Task 9.1 part B
- [IAM matrix](../architecture/aws-iam-matrix.md)
