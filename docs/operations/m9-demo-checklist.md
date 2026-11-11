# M9 Demo & Sign-off Checklist

Demo helper: `bash scripts/m9-demo.sh`. It takes about 10 minutes; `PAUSE=1` waits for Enter before each step. It follows the milestone's 5-step demo scenario against the local stack, the local Splunk and the AWS sandbox. Step 1 (the pipeline) is shown in GitHub.

## Before the demo

```bash
cd ~/projects/mortgage-platform
git switch develop && git pull
bash scripts/splunk/local-up.sh                      # stack + local Splunk + log shipping (reuses everything)
aws login --profile capstone-dev --region us-east-2  # step 2 (Terraform plan) only
python3 scripts/splunk/traffic.py --minutes 3        # a few minutes of data for the dashboard
PAUSE=1 bash scripts/m9-demo.sh
```

Have these open in the browser:
- the last green `ci` run on `develop` (Actions → ci);
- the Splunk dashboard http://localhost:8002/en-US/app/search/mortgage_platform_overview, with the time range covering the re-run of the drill: 2026-11-10 08:44–09:00 UTC, which is 3:44–4:00 AM Eastern (drill 1: 04:44–05:00 UTC);
- Splunk *Activity → Triggered Alerts*;
- [rca-2026-11-10.md](rca-2026-11-10.md).

## Demo scenario (the milestone's demo script)

| # | Show (time) | What to say | Pass criteria |
| --- | --- | --- | --- |
| 1 | **Push → pipeline green through deploy dev** (4 min) | One pipeline, `ci.yml`: build → unit tests (6 suites) → secret scan, SAST and SCA → container build → container scan (fixable CRITICAL fails) → integration tests on the scanned images → publish. Deployment: the sandbox's organization policy blocks GitHub OIDC, so `deploy-dev (run locally)` hands off the exact command, and `deploy-dev.sh` deploys only images with a green `ci` run. The CI deploy job is implemented and switched off by one flag. | A green run on `develop`, then `deploy-dev.sh` output ending in an ECS task definition revision |
| 2 | **Terraform plan / apply artifact** (2 min) | 5 modules and 3 environments, identical except `tfvars`. S3 state with native locking. The M8 resources were imported, not recreated (48 imported). Drift is detected (exit 2) and remediated by apply. test and prod are plan-only. | `tf.sh dev plan -detailed-exitcode` → exit 0. [Drift record](terraform-drift-exercise.md#record-of-the-run). [Deployment record](cicd.md#deployment-record) |
| 3 | **Splunk search by correlationId from a live API call** (2 min) | Every log line in all 4 services is JSON with the same fields. The correlation ID comes from the caller or is generated, returned in the response, and carried through events into the consumers. | The script's request ID is found in `index=mortgage_dev`, with the `http_request` line (route template, status, `durationMs`) |
| 4 | **Dashboard + the alert that fired during the sim** (2 min) | Payment SLI, p95, request rate, 5xx rate, errors, consumer failures. 5 alerts as code, each with a runbook section. Drill 1: *Error spike* after 1 min 4 s, payment SLO alerts at 3 min 3 s. Re-run after the fixes: *Database unreachable* and both payment SLO alerts after 40 s. | Dashboard over the re-run window; *Triggered Alerts* lists 4 alerts at 08:48 and the fast burn at 08:49 UTC |
| 5 | **RCA summary** (2 min) | DB outage: requests hung 30 s (pool timeout), 30 payments failed, SLI 94.1% for the window, recovered 1 s after the restart. Detection was slowed by the 5-minute alert window; throttled requests were invisible to payment searches. Follow-ups B-22 to B-25 done the same day; the re-run failed requests in ~3 s with 503 and alerted in 40 s. | [rca-2026-11-10.md](rca-2026-11-10.md) sections 1–7 |

## Validation (from the milestone)

- [x] **Pipeline green on `develop` with tests + scans.** Every merge from PR #108 to #114 went green on `develop`. The gates caught real issues on the way:
  - Semgrep: XXE in `junit_summary.py`, and a subprocess call in the drill script;
  - Trivy: a stale `certifi` in pip's vendored copy;
  - integration tests: a race in my own smoke test.
- [x] **Container images published with tag.** `ghcr.io/akr12403/mortgage-platform/<service>:sha-<commit>`, then `:develop` and semver from `publish`. The same tags are in dev's ECR, which is immutable.
- [x] **`terraform apply` succeeds in dev.** 48 imported, 44 added, 21 changed, 0 destroyed; the follow-up plan exits 0. Four deploys and a rollback drill since ([record](cicd.md#deployment-record)).
- [x] **Logs searchable in Splunk by correlationId.** `local-up.sh` proves it on every run (`splunk-check-…`). The RCA trace follows `traffic-d2d1c30e-…`.
- [x] **Dashboard renders; alert fired during sim.** [Screenshots](rca-2026-11-10.md#3-timeline-utc); all 3 alerts fired in drill 1, and all 5 in the re-run ([§7](rca-2026-11-10.md#7-re-run-after-the-fixes-p-5)).
- [x] **RCA reviewed and linked in MR.** [rca-2026-11-10.md](rca-2026-11-10.md) was added in PR #114 and is linked from [incident-response.md](incident-response.md#exercises) and the README. Review is the sign-off below.

## Definition of Done → evidence

| DoD item | Evidence |
| --- | --- |
| CI/CD pipeline working end-to-end | [`ci.yml`](../../.github/workflows/ci.yml), [cicd.md](cicd.md), and the GitLab equivalent `.gitlab-ci.yml` (same scripts) |
| Security gates (SAST/SCA/secrets/container scan) working | `secret-detection`, `sast` (with the IAM and static SQL guards; the Terraform layout guard runs in repo-checks), `dependency-scanning`, `container-scan` with its [policy](cicd.md#container-scan-policy). Each blocked a real finding during M9 (above). |
| Docker images built and stored in registry | GHCR (every run) and dev ECR (deploys) |
| Deployment automated to dev (test/prod gated) | `deploy-dev.sh`: one command, tested images only, plan then apply. test plan and prod dry run are manual. CI automation is implemented and blocked by the sandbox organization policy ([deviation](cicd.md#deviations-from-the-handbook), B-20). |
| Terraform modules and environments created | [`infrastructure/terraform/`](../../infrastructure/terraform/): 5 modules, dev/test/prod, bootstrap; [terraform.md](terraform.md) |
| Infrastructure reproducible from IaC | dev rebuilt from code (`tf.sh dev apply`); test and prod plan 90 to add from the same definition; `tests/infrastructure/test_terraform_layout.py` in CI |
| Logs available in Splunk with correlation IDs | [observability.md](observability.md) (log contract, shipping, troubleshooting) |
| Dashboard created for mortgage KPIs/errors | [`monitoring/splunk/dashboards/`](../../monitoring/splunk/dashboards/) |
| Alert created and tested | [`monitoring/splunk/alerts.json`](../../monitoring/splunk/alerts.json); all 5 fired in the re-run |
| Incident simulation completed | `scripts/incident/db_outage_drill.py`, run 2026-11-10 04:44–04:59 UTC, re-run after the fixes 08:44–08:59 UTC |
| RCA submitted and linked in docs/operations | [rca-2026-11-10.md](rca-2026-11-10.md) |
| Runbook and incident-response updated | [runbook.md](runbook.md): *Startup, deploy and rollback* and *Alerts* (with the drill's database signature). [incident-response.md](incident-response.md) is new. |
| Merged to develop via reviewed PR(s) | PRs #108 to #114, all with every gate green. Solo project, so human review is the sign-off below. |

## Deviations from the handbook (recorded)

| Handbook | Implemented | Why / where |
| --- | --- | --- |
| GitLab CI/CD | GitHub Actions; `.gitlab-ci.yml` kept as the equivalent | [cicd.md](cicd.md#deviations-from-the-handbook) |
| Deploy dev automatically from the pipeline | Pipeline hands off; `deploy-dev.sh` with the developer session | The sandbox SCP denies the GitHub OIDC provider; no access keys allowed (B-20) |
| Remote state "S3 + DynamoDB lock" | S3-native lock (`use_lockfile`) | DynamoDB locking deprecated ([terraform.md](terraform.md#deviations-from-the-handbook)) |
| RDS | ECS Fargate at 0 tasks, database host as a placeholder | "RDS or EC2/ECS placeholder" is allowed; idle cost near zero |
| test and prod deployed | plan-only | One sandbox account, limited credits |
| The course's Splunk | Local Splunk Enterprise | No HEC token issued yet. Switching is configuration only ([monitoring/splunk/README.md](../../monitoring/splunk/README.md)). |

## Sign-off

- [x] **Reviewed by a peer or the instructor** at the M9 review: demo run, cicd.md, terraform.md, observability.md, slo.md, RCA and incident-response read. Reviewer: **Sumanth Donur**. Review due: **2026-11-10**. Tick this box when the review is done. **Done: reviewed and approved by Sumanth Donur, 2026-11-10.**

## After the final demo: cleanup

The order matters: AWS resources first, the Terraform state bucket last, local containers any time.

1. **AWS dev (all Terraform-managed resources, the former M8 resources included):**
   ```bash
   aws login --profile capstone-dev --region us-east-2
   bash scripts/terraform/tf.sh dev plan -destroy        # review: about 92 to destroy, nothing else
   bash scripts/terraform/tf.sh dev destroy
   ```
   - Buckets and ECR repositories are emptied first (`sandbox_teardown = true` in dev).
   - Old ECS task definition revisions stay as INACTIVE, which is free.
   - Don't use `scripts/aws/teardown.sh` any more: it predates Terraform and would leave the state wrong.
2. **The Terraform state bucket** (versioned, so it has to be emptied with all its versions):
   ```bash
   bash scripts/terraform/tf.sh bootstrap apply -var force_destroy_state=true
   bash scripts/terraform/tf.sh bootstrap destroy -var force_destroy_state=true
   ```
3. **Check nothing is left:**
   ```bash
   aws resourcegroupstaggingapi get-resources --profile capstone-dev --region us-east-2 \
     --tag-filters Key=Project,Values=mortgage-intelligence --query 'ResourceTagMappingList[].ResourceARN'
   ```
   It should print `[]`. It can take a few minutes after the destroy.
4. **Local Splunk** (frees about 4 GB of RAM and about 3 GB of disk):
   ```bash
   bash scripts/splunk/local-up.sh --down
   docker volume rm mortgage-platform_splunk-var mortgage-platform_splunk-etc
   docker image rm splunk/splunk:10.2 fluent/fluent-bit:5.1.2
   rm .env.splunk-local
   ```
5. **Local stack** (optional): `docker compose down`. Add `-v` to also drop the local database.
6. **GitHub (optional):** delete old `sha-…` image versions under your profile → Packages, if storage matters.
