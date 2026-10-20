# Messaging and Event-Driven Architecture Runbook

## Local Topology

The local stack uses LocalStack SNS/SQS. Compose initializes the lifecycle topic, servicing queue, DLQ, and SNS-to-SQS subscription with `localstack/init/ready.d/01-create-mortgage-messaging.sh`.

| Resource | Name | Purpose |
| --- | --- | --- |
| SNS topic | `capstone-mortgage-lifecycle-dev` | Mortgage lifecycle event fan-out |
| SQS queue | `capstone-mortgage-servicing-dev` | Consumed by `servicing-service` |
| SQS DLQ | `capstone-mortgage-servicing-dlq-dev` | Holds messages after repeated processing failures |

The servicing queue uses a 30-second visibility timeout and a redrive policy with `maxReceiveCount=3`. Inside Compose, services reach LocalStack at `http://localstack:4566`; `localhost` refers to the calling container.

## Verify Resources

```bash
docker compose exec -T localstack awslocal sns list-topics
docker compose exec -T localstack awslocal sqs list-queues
docker compose exec -T localstack awslocal sns list-subscriptions-by-topic \
	--topic-arn arn:aws:sns:us-east-1:000000000000:capstone-mortgage-lifecycle-dev
```

## Processing and Retry Behavior

1. `mortgage-service` publishes an envelope containing `eventId`, `eventType`, `schemaVersion`, `occurredAt`, `correlationId`, and `payload`.
2. SNS delivers raw event JSON to the servicing queue.
3. `servicing-service` validates the envelope, resolves `mortgageExternalId` to the canonical mortgage UUID, and transactionally writes `servicing_history` plus the `event_inbox` row.
4. SQS acknowledgment occurs only after transaction commit. Duplicate event IDs are acknowledged without repeating the history write.
5. Failures are logged and left unacknowledged. SQS retries after visibility timeout and moves messages to the DLQ after three receives.

## Troubleshooting

- `QueueDoesNotExist`: confirm `messaging-init` exited successfully and inspect `awslocal sqs list-queues`.
- Messages remain visible: inspect `docker compose logs --tail=150 servicing-service`; verify the event envelope and that its business mortgage ID exists in `mortgage`.
- Messages land in the DLQ: inspect the message, fix the cause, then redrive deliberately; do not replay poison messages blindly.
- No event appears: inspect mortgage-service logs and verify the SNS topic ARN in Compose.
- The previous generated-schema database volume is retained. Current Compose uses the separate canonical volume `mortgage_platform_canonical_postgres_data_v2`; a dump of the earlier local DB is ignored by Git at `database/mortgage_intel-pre-canonical-schema.dump`.