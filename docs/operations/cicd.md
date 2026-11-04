# CI/CD Pipeline (M9 Task 9.1)

One pipeline file, **[`.github/workflows/ci.yml`](../../.github/workflows/ci.yml)**, runs on GitHub Actions where the repository lives. [`.gitlab-ci.yml`](../../.gitlab-ci.yml) is the equivalent pipeline for GitLab. It has the same stages and calls the same scripts, but it isn't executed for this project; see [deviations](#deviations-from-the-handbook). Every stage calls a script in `scripts/`, so a stage behaves the same in either CI system and on a laptop.

```text
          ┌ unit-tests: mortgage-service ┐
build ────┤ servicing-service, analytics ├──┐
          │ knowledge-assistant, ts-client│  │
          └ repo-checks                   ┘  ├─▶ container-build ─▶ container-scan ─▶ integration-tests ─▶ publish ─▶ deploy*
secret-detection ── sast ── dependency-scanning ┘   (4 images,      (4 images,       (compose stack from    (push only)
                                                     sha-<commit>)   fixable CRITICAL  the scanned images)
                                                                     fails)
* deploy: dev automatic, test manual, prod plan-only (Task 9.1 part B, after Terraform)
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
| Deploy | Task 9.1 part B | dev on every `develop` push after `publish`; test manual; prod `terraform plan` only | | |

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
- **Later secrets are masked repository secrets, never files.**
  - Part B: AWS access uses **OIDC**, a short-lived role assumed per job (backlog B-20). There are no AWS keys.
  - Task 9.3: Splunk uses `SPLUNK_HEC_URL` and `SPLUNK_HEC_TOKEN`.

## Triggers and cost

| Event | Runs |
| --- | --- |
| Pull request to `develop` / `main` | everything up to `integration-tests` (no `publish`) |
| Push to `develop` / `main` (merge) | everything, plus `publish` (+ deploy dev in part B) |
| Tag `v*.*.*` | everything, plus `publish` with the semver tag |
| Manual (`workflow_dispatch`) | the same as a push |

- **Superseded runs:** PR runs on the same branch cancel the older run.
- **Cost:** the repository is private on a free plan, so it gets **2,000 Actions minutes a month**. A full run uses about 40–60 minutes across parallel jobs, and Docker layer and Maven caches cut repeat runs.
- **To save minutes:** run `bash scripts/security-gates.sh all`, `bash scripts/ci/unit-tests.sh <suite>` and `LOCAL_IMAGES=1 bash scripts/ci/integration-tests.sh` locally before pushing.

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
| "test manual or gated" | `workflow_dispatch` run by a person | Environment protection rules (required reviewers) aren't available for private repositories on the free plan |
| Scan reports "stored in GitLab" | Workflow artifacts (default 90-day retention) + job summaries | Code-scanning (SARIF) upload needs GitHub Advanced Security on private repositories |
