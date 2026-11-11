# CI/CD Pipeline (M9 Task 9.1)

The pipeline file, **[`.github/workflows/ci.yml`](../../.github/workflows/ci.yml)**, runs on GitHub Actions where the repository lives: build, test, scan, publish and the automatic dev deployment. Its companion **[`.github/workflows/infra.yml`](../../.github/workflows/infra.yml)** runs Terraform: plans on pull requests, the gated test plan, the prod dry run, rollbacks and the nightly drift check. [`.gitlab-ci.yml`](../../.gitlab-ci.yml) is the equivalent pipeline for GitLab. It has the same stages and calls the same scripts, but it isn't executed for this project; see [deviations](#deviations-from-the-handbook). Every stage calls a script in `scripts/`, so a stage behaves the same in either CI system and on a laptop.

```text
          ┌ unit-tests: mortgage-service ┐
build ────┤ servicing-service, analytics ├──┐
          │ knowledge-assistant, ts-client│  │
          └ repo-checks                   ┘  ├─▶ container-build ─▶ container-scan ─▶ integration-tests ─▶ publish ─▶ deploy*
secret-detection ── sast ── dependency-scanning ┘   (4 images,      (4 images,       (compose stack from    (push only)
                                                     sha-<commit>)   fixable CRITICAL  the scanned images)
                                                                     fails)
* deploy-dev: develop pushes only. test (gated plan), prod (dry run) and rollback: manual runs of infra.yml
```

## Stages

| Handbook stage | Job(s) | What runs | Fails the pipeline when | Artifacts |
| --- | --- | --- | --- | --- |
| Build | `build` | `mvn package` for both Java services (tests skipped here), `npm ci && npm run build` for the TS client (type-check), `compileall` for all Python | anything doesn't compile | none |
| Unit Test | `unit-tests (<suite>)`, 6 in parallel | `scripts/ci/unit-tests.sh <suite>`:<br>• Java: `mvn test`<br>• Python services: the Dockerfile's own `test` stage + pytest<br>• TS: `node --test`<br>• `repo-checks`: event contract tests, static SQL guard, IAM/S3 policy guard, Lambda and Glue unit tests | any test fails | `junit-<suite>` (JUnit XML) + a table in the job summary |
| SAST | `sast` | Semgrep (OWASP Top 10 + Java/Python/TS rules + project rules), static SQL guard, IAM policy guard | any ERROR finding | `semgrep-report` |
| SCA | `dependency-scanning` | Trivy (Maven, npm) + pip-audit (both Python services) | Maven/npm CRITICAL, any known Python vulnerability | `dependency-reports` |
| Secret Scan | `secret-detection` | gitleaks over the **full** git history + a self-test that a planted secret is caught | any finding | `gitleaks-report` |
| Container Build | `container-build (<service>)`, 4 in parallel | Buildx builds the runtime stage of each Dockerfile, pushes `ghcr.io/<owner>/mortgage-platform/<service>:sha-<commit>` with OCI labels (source, revision); layer cache in GitHub Actions cache | the build fails | the image in GHCR |
| Container Scan | `container-scan (<service>)` | `scripts/ci/container-scan.sh`: Trivy on the pushed image ([policy](#container-scan-policy)) | a **CRITICAL** vulnerability **with a fix available** | `container-scan-<service>` (table + JSON) + a summary per image |
| Integration Tests | `integration-tests` | `scripts/ci/integration-tests.sh`: pulls the **scanned** images, starts the full compose stack (PostgreSQL + pgvector, LocalStack SNS/SQS, 4 services) with throwaway secrets, runs the M6 auth/RBAC/OWASP smoke tests and `tests/integration/test_stack_smoke.py` (payment → SNS → both SQS consumers, exactly once) | any test fails, or a service isn't healthy within 5 min | `integration-reports` (JUnit + stack logs on failure) |
| (release) | `publish` (pushes and tags only) | Promotes the tested `sha-<commit>` images **without rebuilding** (same digest): `:develop` / `:main` on branch pushes, `:<semver>` on `v*` tags | n/a | digests in the job summary |
| Deploy | `deploy-dev` (ci.yml), `manual` (infra.yml) | [Deploy](#deploy-part-b): dev automatically after `publish` on `develop`; test = manual gated plan; prod = manual dry run (plan only) | the image copy or `terraform apply` fails | deployment summary (image, Terraform result, ECS services) |

**Gates before images:** container builds start only after all unit tests and all three security gates pass. A vulnerable or untested commit never produces an image.

## Image tags and versions

| Tag | When | Mutable? |
| --- | --- | --- |
| `sha-<40-char commit>` | every pipeline run that reaches `container-build` | no: one commit, one image |
| `develop`, `main` | after a green pipeline on a push to that branch | yes: always the latest tested build |
| `1.4.2` (semver) | after a green pipeline on a git tag `v1.4.2` | no, by convention |

To release, tag a commit on `main`: `git tag -a v1.0.0 -m "…" && git push origin v1.0.0`. Deployments refer to an **immutable** tag (`sha-…` or a semver), never `develop`.

## Container scan policy

| Finding | Effect |
| --- | --- |
| CRITICAL with a fixed version available (OS package or library in the image) | **Pipeline fails.** Rebuild on a patched base image or bump the library. |
| CRITICAL with no fix yet | Reported in the summary and artifact, not blocking. Tracked: add to `.trivyignore` with a reason and an `exp:` date only if it's actually reachable. |
| HIGH | Reported, not blocking. Fixed with the next base-image bump. |
| Accepted exceptions | `.trivyignore` (shared with the SCA gate). Each entry has a reason and an expiry, after which the gate fails again. The existing Spring 6.2 entries expire on 2026-12-31 (R-17). |

Why only *fixable* CRITICAL blocks: a CVE with no fix can't be acted on by this team. Failing on it would stop all delivery until a third party ships a patch. It stays visible on every run instead.

## Secrets in the pipeline

- **No long-lived secrets are needed for part A.** GHCR uses the run's `GITHUB_TOKEN`, scoped with `packages: write` only on the jobs that push. All other jobs get `contents: read`.
- **Integration secrets are generated per run.** The JWT secret, database password and seed password are random values written to a `.env` that exists only on the runner. They're never printed, and the runner is destroyed after the job.
- **Credentials don't go on command lines.** Registry credentials reach Trivy through the environment (`TRIVY_USERNAME`/`TRIVY_PASSWORD`). GitHub masks secret values in logs.
- **AWS access uses OIDC, not keys** (backlog B-20). Each job that touches AWS gets a 1-hour session for one of two roles ([below](#aws-access-from-ci)). The repository stores only role ARNs.
- **Later secrets are masked repository secrets, never files.** Task 9.3: log shipping to Splunk takes `SPLUNK_HEC_HOST`, `SPLUNK_HEC_PORT` and `SPLUNK_HEC_TOKEN` from the environment ([observability.md](observability.md#splunk)).

## Triggers and cost

| Event | Runs |
| --- | --- |
| Pull request to `develop` / `main` | everything up to `integration-tests` (no `publish`) |
| Push to `develop` / `main` (merge) | everything, plus `publish`; on `develop` also `deploy-dev` |
| Tag `v*.*.*` | everything, plus `publish` with the semver tag |
| Manual (`workflow_dispatch`) | the same as a push |
| Pull request touching `infrastructure/**` or `scripts/terraform/**` | `infra`: fmt + validate, plans for dev, test and prod |
| Nightly, 07:17 UTC | `infra / drift check (dev)`: about 2 minutes, roughly 60 minutes a month |
| Manual `infra` run | test plan, prod dry run, or a dev apply (rollback/redeploy) |

- **Superseded runs:** PR runs on the same branch cancel the older run.
- **Cost:** the repository is private on a free plan, so it gets **2,000 Actions minutes a month**. A full run uses about 40–60 minutes across parallel jobs, and Docker layer and Maven caches cut repeat runs.
- **To save minutes:** run `bash scripts/security-gates.sh all`, `bash scripts/ci/unit-tests.sh <suite>` and `LOCAL_IMAGES=1 bash scripts/ci/integration-tests.sh` locally before pushing.

## Deploy (part B)

> **Sandbox status: CI has no AWS access, so dev is deployed by a person with one command.** The sandbox organization's SCP explicitly denies `iam:CreateOpenIDConnectProvider` (tried on 2026-11-09). GitHub can't be trusted as an identity provider, and long-lived access keys are against this project's rules (R-21). So:
> - After every green `develop` run, `ci / deploy-dev (run locally)` prints the exact command: `bash scripts/deploy/deploy-dev.sh sha-<commit>`.
> - [`scripts/deploy/deploy-dev.sh`](../../scripts/deploy/deploy-dev.sh) does what the CI job would do, using the developer session: it checks the tag had a green `ci` run, copies the images to dev's ECR, plans, and applies after confirmation.
> - test plans and the prod dry run are `bash scripts/terraform/tf.sh test|prod plan`, and the drift check is `bash scripts/terraform/tf.sh dev plan -detailed-exitcode`.
> - In `infra.yml`, `fmt` and `validate` still run on every IaC PR, because they don't need AWS.
>
> The CI path below is fully implemented and switched off by one flag. In an account that allows OIDC (or once the sandbox admin creates the GitHub provider):
> 1. set `enable_github_oidc = true` in bootstrap and apply it;
> 2. add the 3 secrets;
> 3. set the repository variable `AWS_OIDC_ENABLED = true`.
>
> No workflow change is needed.

| Environment | Sandbox (now) | With OIDC enabled |
| --- | --- | --- |
| **dev** | `bash scripts/deploy/deploy-dev.sh` after each green `develop` run (the run summary gives the tag) | automatic `ci / deploy-dev` |
| **test** | `bash scripts/terraform/tf.sh test plan` | manual *infra → Run workflow* (gated plan) |
| **prod** | `bash scripts/terraform/tf.sh prod plan` (dry run) | manual *infra → Run workflow* (dry run) |
| dev rollback | `bash scripts/deploy/deploy-dev.sh <last good tag>` | manual *infra → Run workflow*, dev apply with `image_tag` |
| drift check | `bash scripts/terraform/tf.sh dev plan -detailed-exitcode` | nightly `infra / drift check (dev)` |

The rest of this section describes the CI path.

| Environment | How | Job | AWS role |
| --- | --- | --- | --- |
| **dev** | **automatic**: every push to `develop` that passes all gates, after `publish` | `ci / deploy-dev` | `capstone-mortgage-ci-deploy-dev` |
| **test** | **gated**: a person runs *Actions → infra → Run workflow*, environment `test`, action `plan` | `infra / test plan` | `capstone-mortgage-ci-plan` (read-only) |
| **prod** | **dry run**: *Run workflow*, environment `prod`, action `plan`. It's never applied in the sandbox. | `infra / prod plan (dry run)` | `capstone-mortgage-ci-plan` (read-only) |
| dev rollback / redeploy | *Run workflow* on `develop`, environment `dev`, action `apply`, `image_tag` = the tag to run | `infra / dev apply` | `capstone-mortgage-ci-deploy-dev` |

What `deploy-dev` does:
1. It assumes the deploy role over OIDC.
2. It copies the four tested and scanned `sha-<commit>` images from GHCR to dev's ECR without rebuilding (`scripts/ci/promote-to-ecr.sh`). ECR tags are immutable, so an existing tag is reused, never overwritten.
3. It runs `terraform apply` for dev with `image_tag = sha-<commit>`. The ECS services get a new task definition revision; while `desired_count` is 0 (no database yet) that's the whole deployment.
4. It writes a summary: the image, the Terraform result and each service's task definition, desired and running counts, and rollout state.

Terraform on pull requests ([`infra.yml`](../../.github/workflows/infra.yml)) runs only when the IaC paths change:
- `terraform fmt -check` and `validate` with no AWS access;
- then a plan for dev, test and prod with the read-only role. Each plan's summary lists every resource that would change, with account ids redacted.

A nightly drift check plans dev and fails the run if AWS differs from the code (exit 2).

Rollback, failure handling and break-glass: [runbook](runbook.md#rollback).

### AWS access from CI

Both roles are defined in [`infrastructure/terraform/bootstrap/ci-roles.tf`](../../infrastructure/terraform/bootstrap/ci-roles.tf), applied with the developer's session, and are never changed by CI.

| Role | Trusted for (OIDC `sub`) | Can |
| --- | --- | --- |
| `capstone-mortgage-ci-plan` | this repository's pull requests and the `develop` and `main` branches | `ReadOnlyAccess`, read every environment's state and take its lock |
| `capstone-mortgage-ci-deploy-dev` | the `develop` branch only | read-only, plus writes scoped to **dev's named resources**: the 6 dev roles (no managed policies, PassRole only to ECS, Lambda or Glue), the 2 buckets, 2 tables, Lambda, Glue job, log groups, alert rule and alarm, topic and queues, dev ECR and ECS, VPC resources tagged `Project=mortgage-intelligence`, and dev's state |

Both roles have an explicit **deny on business-data reads**: DynamoDB items, SQS messages, uploaded documents, the raw and curated exports, SSM and Secrets Manager values, and log contents. Terraform needs configuration, not data. The roles can't change themselves, the OIDC provider or the state bucket; those stay with the developer session (break-glass).

**Repository secrets.** Set these once under *Settings → Secrets and variables → Actions*. Get the values from `bash scripts/terraform/tf.sh bootstrap output`.

| Secret | Value | Why a secret |
| --- | --- | --- |
| `AWS_PLAN_ROLE_ARN` | `github_secret_AWS_PLAN_ROLE_ARN` | contains the account id |
| `AWS_DEPLOY_DEV_ROLE_ARN` | `github_secret_AWS_DEPLOY_DEV_ROLE_ARN` | contains the account id |
| `TF_DEVELOPER_PRINCIPAL_ARN` | `github_secret_TF_DEVELOPER_PRINCIPAL_ARN` | Terraform must keep trusting the developer role in the app roles. Without it, a CI apply would make the CI role the trusted principal. |

### Deployment record

Deployments to dev on 2026-11-09, all with `scripts/deploy/deploy-dev.sh` and the developer session (sandbox: no CI access to AWS). The plans changed only the 4 task definitions (new revision) and the 4 services; nothing else.

| # | What | Image | Images to ECR | Task definitions | Result |
| --- | --- | --- | --- | --- | --- |
| 1 | First deploy (develop after PR #109) | `sha-fe79157` | 4 pushed | `:1` → `:2` | Apply complete (4 added, 4 changed, 4 destroyed); rollout `COMPLETED`; follow-up plan exit 0 |
| 2 | Deploy of PR #110 (newest green develop) | `sha-1f0a8ac` | 4 pushed | `:2` → `:3` | Apply complete |
| 3 | **Rollback drill** to the previous release | `sha-fe79157` | skipped (already in ECR, immutable) | `:3` → `:4` | Apply complete: one command, no rebuild |
| 4 | Roll forward again | `sha-1f0a8ac` | skipped | `:4` → `:5` | Apply complete |

"Destroyed" in these applies is the previous task definition revision being deregistered. ECS task definitions are immutable, so every new image is a new revision. Services run 0 tasks until a database exists ([terraform.md](terraform.md#design-decisions)).

## Running stages locally

```bash
bash scripts/ci/unit-tests.sh mortgage-service      # or servicing-service | analytics-service | knowledge-assistant | ts-client | repo-checks
sh scripts/security-gates.sh all                    # secrets + SAST + SCA (Docker)
docker compose build && bash scripts/ci/container-scan.sh capstone/mortgage-service:dev mortgage-service
docker compose up -d && LOCAL_IMAGES=1 bash scripts/ci/integration-tests.sh   # uses your .env; posts a 1.00 test payment
python3 scripts/ci/junit_summary.py local reports/junit
```

## Deviations from the handbook

| Handbook | Implemented | Why |
| --- | --- | --- |
| GitLab CI/CD | GitHub Actions (`ci.yml`); `.gitlab-ci.yml` kept as the documented equivalent | The repository, its PRs and its branch protection live on GitHub. Running two CI systems would double the minutes and the maintenance. |
| GitLab registry | GHCR (`ghcr.io/<owner>/mortgage-platform/*`); copied to ECR for the ECS deploy (part B) | GitHub's registry, authenticated by the run's own token. ECS pulls from ECR natively with IAM. |
| "test manual or gated" | `workflow_dispatch` run by a person (`infra / test plan`) | Environment protection rules (required reviewers) aren't available for private repositories on the free plan. A manual run is the gate, and the deploy role's trust (develop only) is the hard limit. |
| test deployed | test **planned**, not applied | One sandbox account with limited credits. test and prod use the identical Terraform definition, so a test apply would need only a deploy role for test. |
| "terraform apply … with manual approval for prod" | prod **dry run** (plan only, manual) | The handbook asks for a prod dry-run job. There's no prod account, and the plan role can't write. |
| "Deploy to dev automatically" from the pipeline | the pipeline stops at **publish** and hands off. `scripts/deploy/deploy-dev.sh` runs the identical steps with the developer session. The CI deploy is implemented and switched off. | The sandbox SCP denies creating the GitHub OIDC provider, and access keys are not allowed (R-21). |
| Scan reports "stored in GitLab" | Workflow artifacts (default 90-day retention) + job summaries | Code-scanning (SARIF) upload needs GitHub Advanced Security on private repositories |
