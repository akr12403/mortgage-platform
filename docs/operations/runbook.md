# Operations Runbook

The platform's single operations entry point. M6 adds **secrets rotation**. M9 adds deploy and rollback, and M10 adds startup and common failures (sections reserved below). Messaging operations live in [messaging-runbook.md](./messaging-runbook.md).

## Secrets rotation

Data classes and encryption are covered in [security-controls.md](../security/security-controls.md#data-classification-task-65). Every secret on this page is **Restricted**.

### Principles

- **Secrets live only in the environment**, never in Git, images or logs. Locally that means the git-ignored root `.env`; in AWS it means Secrets Manager, injected into ECS tasks at start. Compose refuses to start without `JWT_SECRET` and `AUTH_SEED_PASSWORD`, and mortgage-service refuses a `JWT_SECRET` shorter than 32 bytes.
- **One secret, one purpose, one environment.** Dev, test and prod never share a value.
- **Rotate on a schedule and on any suspicion.** A secret that may have been exposed (pasted in chat, committed, printed in CI output, held by someone who left) is rotated **immediately**, not at the next scheduled date.
- **Generate, don't invent:** `openssl rand -base64 48` for keys and `openssl rand -base64 24 | tr -d '/+='` for passwords.
- **Verify after every rotation** with the smoke tests at the end of this section.

### Inventory and cadence

| Secret | Used by | Store (local / AWS) | Rotation cadence | Effect of rotating |
| --- | --- | --- | --- | --- |
| `JWT_SECRET` (HS256 signing key) | mortgage-service signs; servicing and analytics verify | `.env` / Secrets Manager `capstone/<env>/jwt-signing-key` | every **90 days**, and on suspicion | all outstanding tokens become invalid; clients log in again (the TS client does this automatically) |
| `POSTGRES_PASSWORD` (app DB user) | all three services, `db-migrate` | `.env` / Secrets Manager `capstone/<env>/db/app` with **managed rotation** | every **30 days** (automatic in AWS), and on suspicion | services pick up the new value on restart; AWS uses alternating users, so there is no downtime |
| RDS master password | DBAs only, break-glass | — / Secrets Manager (RDS-managed) | automatic (RDS-managed, 7 days) | none for apps; they never use it |
| `AUTH_SEED_PASSWORD` | local and dev seed users only; **never set in prod** | `.env` | when shared outside the team, or per sprint for shared dev | seed users need re-seeding (below) |
| AWS credentials | services | local: LocalStack dummy values (`test`) / AWS: **IAM task roles**: short-lived, auto-rotated | nothing to rotate | no long-lived access keys exist; if one is ever created for break-glass, rotate it within 90 days and delete it after use |
| TLS certificates | public ALB, internal targets | ACM / AWS Private CA | **automatic** renewal before expiry | none; alert if ACM reports a renewal failure |
| KMS keys | RDS, S3, SNS/SQS, Secrets Manager, logs | KMS | **automatic yearly** | none; old key versions keep decrypting existing data |

### JWT signing key (`JWT_SECRET`)

The services currently accept exactly **one** key, so a rotation is a hard cut-over: every token signed with the old key gets **401 `INVALID_TOKEN`** after the switch, and clients log in again. Access tokens live for 1 hour (`JWT_TTL_SECONDS`), so the impact is "everyone re-authenticates once".

**Local (Docker Compose):**

```bash
cd ~/projects/mortgage-platform
NEW_KEY="$(openssl rand -base64 48)"
sed -i '' "s|^JWT_SECRET=.*|JWT_SECRET=${NEW_KEY}|" .env      # macOS sed; on Linux use: sed -i "s|...|...|" .env
unset NEW_KEY
docker compose up -d          # recreates mortgage-, servicing- and analytics-service with the new key
docker compose ps             # wait for all three to be healthy
python3 tests/security/test_auth_smoke.py
```

An old token now gets 401 everywhere, and a fresh login works against all three services.

**AWS:**

1. Put a new random value into `capstone/<env>/jwt-signing-key` as a new version (`AWSPENDING` → `AWSCURRENT`). The old version is kept as `AWSPREVIOUS`, ready for rollback.
2. Force a new deployment of **all three** ECS services in the same change window. Validators must not run with a different key than the issuer, or every request fails with 401.
3. Run the smoke tests (below) against the environment, and watch the 401 rate in CloudWatch: one spike while clients re-login, then back to baseline.
4. **Rollback:** move `AWSCURRENT` back to the previous version and redeploy the three services.

**Suspected key compromise:** rotate immediately (as above), then review the access logs for tokens issued or used during the exposure window: subjects, roles, source IPs, writes. Anyone holding the old key could have minted an ADMIN token, so treat every write in that window as suspect, and open an incident (M9 `incident-response.md`).

#### Zero-downtime key rotation (future)

To rotate with no forced logout, the services would add a `kid` header to tokens. They would accept the **current and previous** keys during a grace period of at least `JWT_TTL_SECONDS`, and only ever sign with the current one:

1. deploy validators that accept `kid=k2` (new) and `kid=k1` (old);
2. switch the issuer to sign with `k2`;
3. after one TTL, remove `k1`.

The alternative is asymmetric signing (RS256/ES256) with a JWKS endpoint, where validators hold only public keys. Both are M9 candidates. The single-key design is a deliberate simplification for M6.

### Database password (`POSTGRES_PASSWORD`)

**Local (Docker Compose):** the Postgres container only reads `POSTGRES_PASSWORD` when it first creates the database volume, so change the role's password in the database **and** in `.env`:

```bash
cd ~/projects/mortgage-platform
NEW_PW="$(openssl rand -base64 24 | tr -d '/+=')"
docker compose exec -T postgres psql -U mortgage_app -d mortgage_intel -c "ALTER ROLE mortgage_app PASSWORD '${NEW_PW}';"
sed -i '' "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=${NEW_PW}|" .env
unset NEW_PW
docker compose up -d          # recreates postgres (data stays in the volume) and the services with the new password
docker compose ps             # all healthy => services reconnected with the new password
```

If you change `.env` without running the `ALTER ROLE`, the services fail their health checks with authentication errors in the logs. Run the `ALTER ROLE` (or put the old value back) to recover.

**AWS:** use Secrets Manager **managed rotation** with the *alternating users* strategy. Two DB users (`app_a`, `app_b`) take turns: rotation changes the password of the inactive user and then makes it current, so connections using the active user keep working. Services read the secret at start, so a new ECS deployment, or a scheduled daily task recycle, picks up the new value. The HikariCP (`maxLifetime`) and SQLAlchemy (`pool_recycle`) connection pools drop old connections well inside the rotation window.

Since Task 6.6 (DP-GAP-2) there is no default password anywhere: a missing secret stops the service and compose instead of silently using a guessable value.

### Seed user password (`AUTH_SEED_PASSWORD`, local/dev only)

Seed users are created once, and existing users are never overwritten. To change their password, delete them and let mortgage-service re-create them:

```bash
cd ~/projects/mortgage-platform
NEW_PW="$(openssl rand -base64 24 | tr -d '/+=')"
sed -i '' "s|^AUTH_SEED_PASSWORD=.*|AUTH_SEED_PASSWORD=${NEW_PW}|" .env
unset NEW_PW
docker compose exec -T postgres psql -U mortgage_app -d mortgage_intel \
  -c "DELETE FROM app_user WHERE username IN ('admin@capstone.local','underwriter@capstone.local','servicing@capstone.local','risk@capstone.local','support@capstone.local');"
docker compose up -d mortgage-service     # SeedUserInitializer re-creates the five users with the new BCrypt hash
python3 tests/security/test_auth_smoke.py  # reads the new password from .env
```

In production there are no seed users. Real staff accounts come from the identity provider, and their passwords are never handled by this platform.

### If a secret was committed to Git

1. **Rotate it first.** Assume it's compromised the moment it's pushed; removing the commit doesn't un-leak it.
2. Remove it from the branch, and from history if the repo is shared (`git filter-repo`, then force-push under the protected-branch exception process, coordinated with the team).
3. Confirm secret scanning (M2 baseline, `docs/operations/devsecops-baseline.md`) flagged it. If it didn't, add a rule. Then record the event in the M6 vulnerability report (Task 6.6).

### Verify after any rotation

```bash
docker compose ps                              # all services healthy
python3 tests/security/test_auth_smoke.py      # login + token accepted by every service; old/tampered tokens rejected
python3 tests/security/test_rbac_smoke.py      # roles still enforced
```

Record each rotation (secret, environment, date, who, reason) in the team's change log. Never record the value itself.

## Startup, deploy and rollback

*Added in M9/M10.* Until then, local start-up is in the root `README.md` and messaging operations are in [messaging-runbook.md](./messaging-runbook.md).
