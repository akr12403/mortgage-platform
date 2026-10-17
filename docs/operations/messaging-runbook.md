# Messaging & Event-Driven Architecture Runbook

## Overview
The Enterprise Mortgage Platform utilizes an asynchronous, event-driven pattern combining **AWS SNS** for event publishing and **AWS SQS** for reliable message fan-out and consumption across downstream microservices.

## Queue Topology & Settings

| Queue Name | Target Consumer | Purpose | Key DLQ / Timeout Settings |
| :--- | :--- | :--- | :--- |
| **`capstone-mortgage-servicing-dev`**[cite: 4] | `servicing-service`[cite: 4] | Consumes lifecycle events (`MortgageCreated`, `PaymentReceived`, etc.) to write audit logs. | Visibility Timeout $\ge$ 30s<br>`maxReceiveCount` = 3[cite: 4] |
| **`capstone-mortgage-analytics-dev`**[cite: 4] | `analytics-service`[cite: 4] | Handles analytical calculations and cache refreshes.[cite: 4] | Visibility Timeout = 30s<br>`maxReceiveCount` = 3 |
| **`capstone-mortgage-servicing-dlq-dev`**[cite: 4] | Manual Replay[cite: 4] | Captures poisoned or repeatedly failing messages after max retries. | Manual inspection & replay workflow[cite: 4] |

## Dead-Letter Queue (DLQ) & Failure Handling Policy
1. **Max Receives**: Any message that fails processing 3 times (`maxReceiveCount = 3`) is automatically routed to `capstone-mortgage-servicing-dlq-dev`[cite: 4].
2. **Idempotency**: Consumers check the `event_inbox` table (`event_id` primary key) before executing side-effects to ensure duplicate message deliveries are safely ignored[cite: 4].
3. **Manual Replay**: Operations personnel can inspect messages in the DLQ via LocalStack / AWS Console, resolve the underlying application bug, and redrive messages back to the primary servicing queue.