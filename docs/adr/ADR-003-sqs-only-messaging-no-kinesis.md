# ADR-003: SNS → SQS Messaging Only, No Kinesis (M8)

| Field | Value |
| --- | --- |
| **Status** | Accepted |
| **Milestone** | M8: AWS & Data Platform (Task 8.4) |
| **Deciders** | Engineering team |
| **Date** | 2026-11-03 |
| **Related** | ADR-002 (decomposition, SNS → SQS events), `docs/architecture/event-catalog.md`, `docs/operations/messaging-runbook.md`, [aws-dynamodb-mortgage-lookup.md](../architecture/aws-dynamodb-mortgage-lookup.md) |

---

## Context

M8 Task 8.4 asks us to enhance the event flow with a Kinesis stream for servicing updates, **or** to justify SQS-only messaging in an ADR if the account limits it.

The M5 flow:

```text
mortgage-service ──publish──▶ SNS capstone-mortgage-lifecycle-dev
                                 ├─▶ SQS capstone-mortgage-servicing-dev ─▶ servicing-service   (DLQ after 3 receives)
                                 └─▶ SQS capstone-mortgage-analytics-dev ─▶ analytics-service   (DLQ after 3 receives)
```

Five event types are published: `MortgageCreated`, `LoanApproved`, `PaymentReceived`, `PaymentMissed` and `LoanDelinquent`.

Facts that shape the decision:

1. **Account limit.** The sandbox is an AWS "new experience" project on the **Free plan**. Kinesis Data Streams is only in the **Paid plan**: the project's guardrail policy denies it on Free. Upgrading would remove the guarantee that the account cannot be charged.
2. **Volume.** The portfolio has 33 seeded mortgages, and production would see at most a few thousand lifecycle events a day, so traffic is well under one message per second. A single Kinesis shard handles 1 MB/s or 1,000 records/s of writes; we would use less than 0.1 % of it.
3. **Consumers need per-message semantics.** Each consumer acknowledges messages one at a time, retries failures, and parks poison messages in its own DLQ (M5 Task 5.5). That's what SQS provides. Kinesis is a log read by shard and position: one bad record blocks its shard until the consumer skips or parks it itself.
4. **Ordering is per mortgage, not global.** What matters is that a mortgage's events aren't applied out of order. The consumers already handle this:
   - servicing-service dedupes through `event_inbox`;
   - analytics dedupes by `eventId`;
   - the DynamoDB lookup update (Task 8.4) is a conditional write that ignores any event older than the last one applied.
5. **Replay.** Kinesis keeps records for 24 h to 365 days, so a new consumer can rebuild from history. We don't need that: PostgreSQL is the system of record (ADR-001), and every projection can be rebuilt from it. The lookup table, for example, is bulk-loaded with `lookup-load.sh`.

## Decision

1. **Keep SNS → SQS fan-out as the only event transport.** Each consumer has its own standard queue and DLQ, uses raw message delivery, and keeps `maxReceiveCount=3`. No Kinesis stream is created.
2. **Enhance the flow without a new transport.** The analytics consumer now also updates the **DynamoDB lookup table** `CapstoneMortgageLookup-dev`, which serves fast reads by mortgage ID:
   - `PaymentReceived` updates `outstandingBalance` and `lastPaymentDate`.
   - `LoanDelinquent` sets `status=DELINQUENT`, `daysPastDue` and the severity.
   - `MortgageCreated`, `LoanApproved` and `PaymentMissed` update their own fields.
   - Updates are **conditional on `occurredAt`**, so an SQS redelivery or an out-of-order event can't roll the cache back.
   - If the write fails, the message is **not** acknowledged. SQS retries it, then dead-letters it, so the cache can't silently miss an event.
3. **The partition key is the same everywhere: `mortgageExternalId`.** It's the DynamoDB partition key. It would be the Kinesis partition key and the SQS FIFO `MessageGroupId` if either is adopted later. All three need the same property: one mortgage's events stay together, and different mortgages spread out.
4. **Roles stay least-privilege for the queues they use.** IAM (Task 8.1) gives each consumer only `ReceiveMessage` and `DeleteMessage` on its own queue, and gives the publisher only `sns:Publish` on the one topic.

## Options considered

| Option | Pros | Cons | Verdict |
| --- | --- | --- | --- |
| **A. SNS → SQS standard (current) + DynamoDB projection** | On the Free plan; per-message retries and DLQ already built and tested (M5); the free tier covers 1 M SQS requests/month; no new code paths | No global ordering (not needed); no replay (PostgreSQL rebuilds projections) | **Chosen** |
| B. Kinesis Data Streams (1 provisioned shard) for servicing updates | Ordered per partition key; replay; several consumers read the same records | Needs the Paid plan; about $11/month per shard ($0.015/h) plus PUT units, even when idle; we'd have to build checkpointing, retry and poison-record handling ourselves; one shard is 1000× more capacity than we need | Rejected for M8 |
| C. SQS FIFO queues (`MessageGroupId = mortgageExternalId`) | Strict per-mortgage order and 5-minute deduplication, still on SQS | SNS → SQS FIFO needs an SNS FIFO topic, so the topology and publisher change; 300 msg/s per API action without high-throughput mode (fine); the consumers' conditional/dedupe logic already gives the same result | Not needed now; first upgrade path if strict ordering becomes a requirement |
| D. EventBridge bus | Content-based routing, archive and replay | A different integration model from M5; no benefit at this scale | Rejected |

## Consequences

- **Positive:**
  - No new infrastructure or cost, and the account stays non-billable.
  - The M5 retry/DLQ runbook still applies unchanged.
  - The lookup cache is eventually consistent: it's updated within seconds of the event and protected against stale writes.
- **Negative:**
  - No event replay. Rebuilding a projection means a bulk load from PostgreSQL, not a stream re-read.
  - A consumer that's down long enough loses messages after 4 days of SQS retention. Today the DLQ keeps them for 14 days, and the queue's own retention is the default 4 days. That's acceptable because PostgreSQL holds the truth.
  - In this local setup the queues run in LocalStack and DynamoDB runs in AWS. If the analytics role's 1-hour credentials expire, lookup updates fail and the messages go to the DLQ, which is the intended, visible failure. They can be redriven, or the table reloaded (`messaging-runbook.md`, `lookup-load.sh`).
- **Revisit when** one of these becomes true:
  1. Event volume approaches hundreds per second.
  2. Several new consumers need to replay history, for example a streaming analytics or fraud model.
  3. The account moves to the Paid plan and the M10 production design asks for an immutable event log.

  Then add **Kinesis Data Streams, on-demand mode**, with partition key `mortgageExternalId`, alongside the SNS fan-out. Don't replace it, so the existing consumers are unaffected.

## Kinesis design (ready if revisited)

| Item | Design |
| --- | --- |
| Stream | `capstone-mortgage-servicing-updates-dev`, on-demand capacity, 24 h retention, KMS encryption |
| Producer | mortgage-service publishes to SNS (unchanged); a small SNS → Kinesis bridge (Firehose or a Lambda), so the publisher code doesn't change |
| Partition key | `mortgageExternalId`: one loan's events land in one shard, in order; about 1,000 distinct keys spread evenly over the shards' hash ranges. Never `eventType` (5 values → hot shards) or a date (all of today's traffic on one key). |
| Consumer | Lambda event source mapping: batch size 100, bisect-on-error, on-failure destination SQS DLQ, `ReportBatchItemFailures` |
| IAM | Producer `kinesis:PutRecord(s)` on the stream ARN only; consumer `GetRecords`, `GetShardIterator`, `DescribeStream`, `ListShards` on the stream ARN only |
