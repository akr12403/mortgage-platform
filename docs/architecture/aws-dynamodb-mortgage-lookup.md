# DynamoDB Mortgage Lookup (M8 Task 8.4)

`CapstoneMortgageLookup-dev` is a key-value cache of each mortgage's current status and balance, read by ID with one `GetItem`. Inside AWS that's single-digit milliseconds. From the local stack on a laptop, `lookupMs` measures the internet round trip to `us-east-2`: about 550 ms for the first call, which sets up TLS, then about 150 ms. PostgreSQL stays the system of record (ADR-001). The table is filled two ways:
- a bulk load from PostgreSQL;
- lifecycle events from the analytics SQS queue, which keep it current ([ADR-003](../adr/ADR-003-sqs-only-messaging-no-kinesis.md)).

```text
PostgreSQL (truth) ──bulk load: lookup-load.sh──────────────────────────▶ DynamoDB CapstoneMortgageLookup-dev
mortgage-service ─▶ SNS ─▶ SQS analytics ─▶ analytics consumer ─UpdateItem (conditional)─▶      │
client ─JWT─▶ GET :8000/api/v1/lookup/mortgages/{id} ─GetItem──────────────────────────────────┘
```

## Table

| Attribute | Type | Source | Notes |
| --- | --- | --- | --- |
| **PK `mortgageExternalId`** | S | PG / events | `MTG-1001`; the only key, no sort key |
| `borrowerExternalId` | S | PG / `MortgageCreated` | Business ID only. **No names, email, phone or DOB in this table.** |
| `status` | S | PG / `MortgageCreated` / `LoanDelinquent` | `PENDING`, `ACTIVE`, `DELINQUENT`, `CLOSED` |
| `outstandingBalance` | N | PG / `PaymentReceived.outstandingBalanceAfter` | 2 decimals |
| `originalAmount`, `originationDate` | N, S | PG | |
| `lastPaymentDate`, `daysPastDue`, `delinquencySeverity`, `lastMissedDueDate`, `underwritingDecision` | S/N | events | Written only when the event carries them |
| `lastEventAt`, `lastEventId`, `lastEventType` | S | events | Guard against stale or duplicate events (see below) |
| `updatedAt`, `source` | S | both | `pg-bulk-load` or `event`: shows how fresh the item is and where it came from |

- **Capacity:** on-demand, so there's no idle cost and no capacity to tune.
- **Encryption:** at rest, with an AWS-owned key.
- **Definition:** [`infrastructure/aws/dynamodb/mortgage-lookup-table.json`](../../infrastructure/aws/dynamodb/mortgage-lookup-table.json).
- **IAM:** `mortgage-analytics-role` gets `GetItem`, `PutItem`, `UpdateItem` and `BatchWriteItem` on this table only. There's deliberately no `Scan` or `Query` ([IAM matrix](aws-iam-matrix.md)).

## Partition key exercise (Session 29)

**Choice: `mortgageExternalId`.**

| Candidate PK | Hot-partition risk | Verdict |
| --- | --- | --- |
| **`mortgageExternalId`** (`MTG-1001`…) | Low. Every read and write targets one mortgage, and there are about as many keys as loans. DynamoDB **hashes** the partition key, so sequential IDs (`MTG-1001`, `MTG-1002`, …) still land on different partitions. | **Chosen** |
| `borrowerExternalId` alone | Medium. A borrower can have several loans, so the key isn't unique: it would need a sort key, and the read "give me MTG-1002" would need a Query plus a filter. A bulk load sorted by borrower writes all of a large borrower's loans to one partition back to back. | Rejected (handbook: "not `borrower_id` alone") |
| `status` | High. Only 4 values, and about 90 % of items are `ACTIVE`, so one partition takes almost all traffic and the item size limit per partition key is hit quickly. | Rejected: low cardinality |
| `originationDate` or event date | High. It's monotonic, so all of today's writes go to today's key: a moving hot spot. | Rejected: monotonic |
| `MTG-…#shard-n` (write sharding) | None, but every read must fan out to every shard | Not needed: a mortgage gets a few writes a day, far below the 1,000 WCU/s limit per partition |

**Bulk loads:**
- `lookup_load` writes with `BatchWriteItem` (25 items per call, the API maximum).
- It **shuffles the rows first** rather than writing in key order.
- It retries `UnprocessedItems` with exponential backoff.

Shuffling doesn't matter for 33 items, and hashing already spreads sequential keys. It's the habit that prevents a hot partition when a real load of millions of rows arrives sorted by key.

**Indexes:** there's no GSI. The handbook's optional `borrowerExternalId` GSI would serve "all loans of a borrower", which no current endpoint needs. PostgreSQL already answers that, and a GSI costs a second write per update. If it's added later, the GSI partition key `borrowerExternalId` has the same skew concern as above: a few borrowers with many loans make it uneven, though it stays acceptable at mortgage scale.

## Read path: `GET /api/v1/lookup/mortgages/{mortgageExternalId}`

- **Roles:** `ADMIN`, `UNDERWRITER`, `SERVICING_AGENT`, `RISK_ANALYST` (`LOOKUP_READ`). Not `SUPPORT`, because the balance is financial data.
- **Read type:** a single `GetItem`, eventually consistent, which is half the read cost of a strongly consistent read. The cache is eventually consistent with PostgreSQL anyway.
- **Responses:**

  | Status | When |
  | --- | --- |
  | `200` | The item, plus `lookupSource: "dynamodb"` and `lookupMs` |
  | `404 NOT_FOUND` | No item for that ID |
  | `503 LOOKUP_UNAVAILABLE` | Table not configured (LocalStack-only mode) or AWS unreachable or credentials expired |
  | `400` | ID isn't `MTG-nnnn` |

```bash
curl -s localhost:8000/api/v1/lookup/mortgages/MTG-1002 -H "Authorization: Bearer $TOKEN"
{"mortgageExternalId":"MTG-1002","borrowerExternalId":"BOR-002","status":"ACTIVE","outstandingBalance":…,
 "source":"pg-bulk-load","updatedAt":"…","lookupSource":"dynamodb","lookupMs":160.4}
```

## Event updates: stale and duplicate protection

`MortgageLookupStore.apply_event` issues one `UpdateItem`, which **upserts** the item, with:

```text
ConditionExpression: attribute_not_exists(lastEventAt) OR lastEventAt < :occurredAt
                     OR (lastEventAt = :occurredAt AND lastEventId <> :eventId)
```

| Situation | Result |
| --- | --- |
| Newer event | Applied (`UPDATED`) |
| SQS redelivers the same event | Condition fails → `STALE`, nothing changes, message acknowledged |
| An older event arrives after a newer one | `STALE`, so the balance can't be rolled back |
| DynamoDB error (throttling, expired credentials) | Exception → message **not** acknowledged → retried → DLQ after 3 receives |

A bulk load rewrites whole items from PostgreSQL and clears `lastEventAt`. That's correct because PostgreSQL already contains the effect of every event. The `event-stats` endpoint shows the counts, for example `"lookupUpdates": {"UPDATED": 3, "STALE": 1}`.

## Commands

```bash
aws login --profile capstone-dev --region us-east-2
bash scripts/aws/lookup-deploy.sh            # create the table (idempotent)
bash scripts/aws/lookup-load.sh              # bulk load from local PostgreSQL as mortgage-analytics-role
bash scripts/aws/compose-aws-up.sh           # analytics-service: S3 + DynamoDB on AWS (lookup + event updates)
docker compose up -d analytics-service       # back to LocalStack-only (lookup endpoint then returns 503)
```

Demo step 5 is the partition key table above. The live part, as recorded on 2026-11-03:
1. Look up `MTG-1002` (`source: pg-bulk-load`).
2. Post a payment through mortgage-service.
3. Look up `MTG-1002` again: the new balance shows `lastEventType: PaymentReceived` and `source: event`, a second or two after the payment.

| Step | `outstandingBalance` | `source` | `lastEventType` |
| --- | --- | --- | --- |
| After `lookup-load.sh` | 279,000.00 | `pg-bulk-load` | – |
| `POST /payments` 1,850.00 → `PaymentReceived` → SQS → consumer, ~1 s | 277,150.00 | `event` | `PaymentReceived` |
