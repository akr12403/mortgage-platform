# Messaging Runbook (SNS → SQS → consumers, DLQ)

Owner: platform team. Applies to the local LocalStack stack and the AWS sandbox (same names, `-dev` suffix per `guides/standards.md`).

## Topology

```text
mortgage-service ── publish (after DB commit) ──> SNS capstone-mortgage-lifecycle-dev
                                                    │  (RawMessageDelivery=true)
                     ┌──────────────────────────────┴───────────────────────────────┐
                     ▼                                                              ▼
     SQS capstone-mortgage-servicing-dev                           SQS capstone-mortgage-analytics-dev
       consumer: servicing-service                                   consumer: analytics-service
       VisibilityTimeout 30 s, maxReceiveCount 3                     VisibilityTimeout 30 s, maxReceiveCount 3
                     │ after 3 failed receives                                      │
                     ▼                                                              ▼
     DLQ capstone-mortgage-servicing-dlq-dev                       DLQ capstone-mortgage-analytics-dlq-dev
       (14-day retention, manual replay)                             (14-day retention, manual replay)
```

Created by `localstack/init/ready.d/01-create-mortgage-messaging.sh` (compose service `messaging-init`). The script is idempotent, so you can re-run it with `docker compose run --rm messaging-init`.

## Configuration

| Variable | Used by | Local value (in compose) | AWS sandbox |
| --- | --- | --- | --- |
| `SNS_TOPIC_MORTGAGE_EVENTS` | mortgage-service | `arn:aws:sns:us-east-1:000000000000:capstone-mortgage-lifecycle-dev` | `arn:aws:sns:us-east-1:<acct>:capstone-mortgage-lifecycle-dev` |
| `SQS_QUEUE_SERVICING_EVENTS` | servicing-service | `http://localstack:4566/000000000000/capstone-mortgage-servicing-dev` | `https://sqs.us-east-1.amazonaws.com/<acct>/capstone-mortgage-servicing-dev` |
| `SQS_QUEUE_SERVICING_DLQ` | operators | `…/capstone-mortgage-servicing-dlq-dev` | same pattern |
| `SQS_QUEUE_ANALYTICS_EVENTS` | analytics-service | `http://localstack:4566/000000000000/capstone-mortgage-analytics-dev` | same pattern |
| `SQS_MAX_RECEIVE_COUNT` | both consumers | `3` (must equal the queue's RedrivePolicy) | `3` |
| `AWS_ENDPOINT_URL` | all | `http://localstack:4566` | **unset** |
| AWS credentials | all | dummy `test`/`test` injected at runtime | IAM role or `AWS_PROFILE`, never in images or Git |

All keys are listed in `.env.example`.

## Processing semantics

1. **Publish after commit.** Events are sent only after the producing transaction commits. If SNS is unreachable at that moment the event is lost, and mortgage-service logs `ERROR Failed to publish <type> eventId=<id>`. Recover by re-driving the business action or replaying from the logs. A transactional outbox is the planned fix.
2. **Envelope validation.** The consumer requires `eventId` (UUID), `eventType`, `schemaVersion` `1.x`, `correlationId`, and `payload.mortgageExternalId`. A major version other than 1 is rejected, so it retries and then dead-letters. Unknown event types are acknowledged and skipped with a WARN.
3. **Idempotency.** servicing-service writes `servicing_history` (+ `delinquency` for `LoanDelinquent`) and `event_inbox(event_id)` in **one** transaction. A redelivered `eventId` is acknowledged with no side effects. analytics-service dedupes in memory, and its snapshot refresh is idempotent anyway.
4. **Acknowledge after commit.** The SQS message is deleted only after the transaction commits. Any exception leaves it on the queue.
5. **Retries → DLQ.** Redelivery happens after the 30 s visibility timeout. On receive #3 the consumer logs `ERROR … failed on final attempt 3/3; SQS will move messageId=… to the DLQ`, and SQS moves the message on the next receive. Earlier attempts log `ERROR … failed on attempt n/3 … left on queue for retry`. Every consumer log line carries `correlationId=` and `eventId=`.

## Everyday checks

```bash
Q=http://localhost:4566/000000000000
docker compose exec -T localstack awslocal sns list-subscriptions-by-topic \
  --topic-arn arn:aws:sns:us-east-1:000000000000:capstone-mortgage-lifecycle-dev
docker compose exec -T localstack awslocal sqs get-queue-attributes --queue-url $Q/capstone-mortgage-servicing-dev \
  --attribute-names RedrivePolicy VisibilityTimeout ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible
docker compose exec -T localstack awslocal sqs get-queue-attributes --queue-url $Q/capstone-mortgage-servicing-dlq-dev \
  --attribute-names ApproximateNumberOfMessages
docker compose logs --since=5m servicing-service | grep -E "ERROR|Processed"
```

Healthy means: `ApproximateNumberOfMessages` near 0 on both consumer queues, DLQ depth 0, and no `ERROR` lines.

## Incident: messages in a DLQ

1. **Inspect without deleting.** Receiving hides a message for 30 s; it does not remove it.
   ```bash
   docker compose exec -T localstack awslocal sqs receive-message --queue-url $Q/capstone-mortgage-servicing-dlq-dev \
     --max-number-of-messages 10 --attribute-names All --visibility-timeout 5
   ```
2. **Find the cause** in the consumer log using the `eventId` from the body:
   `docker compose logs servicing-service | grep <eventId>`. Typical causes: unknown `MTG-*` (data issue), malformed envelope or unsupported `schemaVersion` (producer bug), or the database down (transient).
3. **Fix the cause first.** Never replay a poison message unchanged.
4. **Replay** after the fix by moving messages back to the source queue:
   ```bash
   docker compose exec -T localstack awslocal sqs start-message-move-task \
     --source-arn arn:aws:sqs:us-east-1:000000000000:capstone-mortgage-servicing-dlq-dev \
     --destination-arn arn:aws:sqs:us-east-1:000000000000:capstone-mortgage-servicing-dev
   ```
   If your LocalStack version lacks `start-message-move-task`, replay one message at a time with `receive-message` from the DLQ, `send-message` of the same body to the source queue, and then `delete-message` from the DLQ. Replays are safe because consumers dedupe on `eventId`.
5. **Discard** a message that can never succeed (for example the demo poison event) with `delete-message`, and record why in the incident notes.

## Demo: force a failure into the DLQ

`scripts/m5-demo.sh` (step 6) sends a valid envelope for the non-existent mortgage `MTG-0000` straight to the servicing queue. You'll see `ERROR … attempt 1/3`, `2/3`, `3/3 … will move … to the DLQ`, then DLQ depth 1 after about 90–120 s. No `servicing_history` or `event_inbox` row is written.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| `QueueDoesNotExist` in consumer logs | `docker compose logs messaging-init`; re-run `docker compose run --rm messaging-init` |
| History not updating after a write | mortgage-service log has `Published <type>`? servicing log has `Processed <type>`? Queue depth growing → consumer down or failing |
| `ERROR Failed to publish` in mortgage-service | LocalStack health (`curl localhost:4566/_localstack/health`), `SNS_TOPIC_MORTGAGE_EVENTS` value |
| Messages land in the DLQ immediately | `SQS_MAX_RECEIVE_COUNT` and RedrivePolicy disagree, or the consumer crashes on every receive. Inspect the logs |
| Restarted LocalStack | Queues are recreated empty (no persistence); in-flight events are lost locally. Re-run the demo steps |
