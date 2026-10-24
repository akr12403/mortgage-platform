# Database Setup & Migrations

PostgreSQL DDL, migrations, and synthetic seed data for the Mortgage Intelligence Platform. Table ownership per service: [`docs/architecture/service-ownership-matrix.md`](../docs/architecture/service-ownership-matrix.md).

## Migrations

| File | Applied by | Notes |
| --- | --- | --- |
| `migrations/001_core_schema.sql` | Postgres init (empty volume only) | canonical schema from the reference data model |
| `seed/seed_mortgage_data.sql` | Postgres init (empty volume only) | synthetic data, no real PII |
| `migrations/002_event_inbox_and_indexes.sql` | compose `db-migrate` on every `up` | `event_inbox` (servicing-service consumer idempotency) + indexes; idempotent |
| `migrations/003_idempotency_record.sql` | compose `db-migrate` on every `up` | payment `Idempotency-Key` store (mortgage-service); idempotent |
| `migrations/004_app_user.sql` | compose `db-migrate` on every `up` | M6 login users (mortgage-service): username, BCrypt `password_hash`, roles; idempotent |

New migrations must be idempotent (`IF NOT EXISTS`) and numbered `NNN_description.sql`; `db-migrate` applies every file after `001` in order.

## Demo IDs

| ID | Scenario |
| --- | --- |
| `BOR-001` | Primary demo borrower (Jamie Nguyen) |
| `MTG-1001` | `ACTIVE`, on-time payments (`LOAN-2001`, APPROVED) |
| `MTG-1002` | `DELINQUENT`, 45 days past due, `MODERATE` |
| `MTG-1003` | `ACTIVE`, recently onboarded |
| `MTG-1005` | `DELINQUENT`, 88 days past due, `SEVERE` (second delinquent case per the 30-day rule) |
| `MTG-1006`, `MTG-1009` | `CLOSED` (excluded from the delinquency-rate denominator) |

Severity bands (event-driven and seed): `MODERATE` 30–59, `SEVERE` 60–89, `CRITICAL` 90+ days past due. Delinquency rule and rate formula: `guides/standards.md` (no successful payment within 30 days after `due_date` → `DELINQUENT`; rate = `DELINQUENT / (ACTIVE + DELINQUENT)`).

## Seed users (M6)

| Username | Role |
| --- | --- |
| `admin@capstone.local` | `ADMIN` |
| `underwriter@capstone.local` | `UNDERWRITER` |
| `servicing@capstone.local` | `SERVICING_AGENT` |
| `risk@capstone.local` | `RISK_ANALYST` |
| `support@capstone.local` | `SUPPORT` |

Rows are created by mortgage-service on startup (not by SQL seed) using the **`AUTH_SEED_PASSWORD`** value from your local `.env`, stored only as a BCrypt hash. The default dev password is therefore whatever you put in `.env`; it is never committed. To change it after first start, update the hash (or delete the `app_user` rows and restart). Details: [`docs/security/authentication.md`](../docs/security/authentication.md).

## Connection settings

Copy `.env.example` to configure local database environments:

```text
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=mortgage_intel
POSTGRES_USER=mortgage_app
POSTGRES_PASSWORD=<set_locally>
```
