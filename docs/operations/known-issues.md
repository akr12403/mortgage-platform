# Known Issues and Workarounds (M10 Task 10.6)

Open issues in release `v1.0.0-capstone`, what they mean for users and operators, and what to do about them until they're fixed. The go-live conditions that depend on them are in [production-readiness.md](production-readiness.md#appendix-go-live-recommendation). Tracking items are in the [remediation backlog](../security/remediation-backlog.md) (B-…) and the [risk register](../security/risk-register.md) (R-…).

## Platform and functionality

| # | Issue | Impact | Workaround | Tracking |
| --- | --- | --- | --- | --- |
| K-1 | A request already inside a database transaction when PostgreSQL goes away returns **500** instead of 503 | During a database outage, about one request per service at the moment of failure gets a non-retryable status. Every later request gets 503 with `Retry-After` | Clients retry payments with the same `Idempotency-Key`, which is safe for 500 too | B-26 (P3) |
| K-2 | Delinquency severity isn't re-evaluated as days past due grow; some seed rows are mislabelled (MTG-1005: 88 days, `CRITICAL`) | The snapshot can show an older severity band | Read `daysPastDue` and apply the bands (30–59 MODERATE, 60–89 SEVERE, 90+ CRITICAL) | B-19 (P3), R-22 |
| K-3 | API responses still include the internal UUID `id` | Exposes internal identifiers; clients must not depend on them | Use the business IDs (`BOR-…`, `MTG-…`) only | B-07 (P3) |
| K-4 | analytics-service serves `/docs`, `/redoc` and `/openapi.json` | API structure visible to anyone who can reach the service | Don't expose port 8000 outside the private network | B-08 (P3) |
| K-5 | Uploaded documents aren't scanned for malware | A malicious file could be stored and downloaded by staff | Type allowlist and magic-byte checks block executables; open downloads only in a sandboxed viewer | B-13 (P2), R-08 |

## Security and identity

| # | Issue | Impact | Workaround | Tracking |
| --- | --- | --- | --- | --- |
| K-6 | Spring Boot 3.5 / Spring Framework 6.2 get no open-source fixes; two Spring CVEs are accepted in `.trivyignore` until 2026-12-31 | New framework CVEs won't be patched | Don't add XSLT views or server-sent-event views; watch the dependency gate | B-18 (P2), R-17 |
| K-7 | Staff log in with a password only (no MFA); one shared HMAC key signs and verifies tokens; tokens can't be revoked individually | A stolen password or token is usable until it's changed or expires (1 h) | Rotate `JWT_SECRET` to revoke every token at once ([runbook](runbook.md#jwt-signing-key-jwt_secret)) | B-15, B-10, B-11, R-01, R-04, R-05 |
| K-8 | Rate limits are counted per container | With more than one replica, a user gets the limit once per replica | Run one replica per service until B-09 | B-09 (P2), R-09 |
| K-9 | No automated check that log messages are free of personal data (tokens are covered: every service has a test that a bearer token never reaches a log line) | Personal data in a new log message would only be caught in review | Logging rules: IDs and usernames only, never bodies, query strings or headers ([observability.md](observability.md)) | B-14 (P2), R-14 |
| K-10 | GitHub doesn't enforce branch protection on this plan | A PR with a red check could technically be merged | Team rule: never merge with a red check; the gates still run on every PR | R-16 |

## Delivery and operations

| # | Issue | Impact | Workaround | Tracking |
| --- | --- | --- | --- | --- |
| K-11 | CI can't deploy to AWS: the sandbox's organization policy denies the GitHub OIDC provider | Every deployment needs a person with a developer session | `bash scripts/deploy/deploy-dev.sh sha-<commit>` with `aws login --profile capstone-dev`; the CI run prints the command | B-20 (P2), R-21 |
| K-12 | No database in AWS: the ECS services run at 0 tasks with a placeholder database host | dev proves the infrastructure and deployments, not a running service | Run the platform with the local stack; AWS serves images, data platform and infrastructure | Go-live condition C-2 |
| K-13 | The documents bucket has no object versioning | A deleted or overwritten document can't be restored from S3 | Keep the source file; re-upload | Go-live condition C-2 |
| K-14 | Logs go to a local Splunk, not the course's Splunk (no HEC token issued yet) | The dashboard and alerts exist only on the developer machine | `bash scripts/splunk/local-up.sh`; switching is configuration only ([monitoring/splunk/README.md](../../monitoring/splunk/README.md)) | Go-live condition C-6 |
| K-15 | The fast-burn payment alert can take up to about 2 minutes, because it evaluates the last complete minute | Not the fastest signal for a full outage | *Database unreachable* fires within about 40 s for database failures ([RCA §7](rca-2026-11-10.md#7-re-run-after-the-fixes-p-5)) | none (by design) |
| K-16 | During a database outage, each failed request logs three ERROR lines (driver, pool, handler) | Error counts look about three times higher than the number of failed requests | Count failures with `message=http_request http.status>=500`, or search `"Database unavailable"` | none |
| K-17 | Python dependencies aren't pinned with hashes | Two builds a week apart can resolve different package versions | The container scan and `pip-audit` run on every build | B-21 (P3), R-16 |
| K-18 | Line coverage isn't measured (no JaCoCo or `pytest-cov` reports) | Coverage is argued by layer and journey, not by a percentage | See [test-strategy.md](test-strategy.md) for what each layer covers | none (candidate) |

## Developer machine

| # | Issue | Workaround |
| --- | --- | --- |
| K-19 | Node.js isn't part of the stack; the E2E suite needs Node 22+ on the machine that runs it | `brew install node`; CI brings its own |
| K-20 | Homebrew's Python refuses `pip install` (PEP 668) | Use a virtual environment: `python3 -m venv /tmp/rc-venv` |
| K-21 | `gh run view --log` fails with `permission denied` on `~/.cache/gh` (the cache was created by `sudo`) | `sudo chown -R "$USER" ~/.cache/gh`, or fetch logs with `gh api --allow-escape-sequences repos/<repo>/actions/jobs/<id>/logs` |
| K-22 | The local Splunk image is amd64 only and runs under Rosetta on Apple silicon | Allow about 4 GB of memory for Docker; first start takes a few minutes |
