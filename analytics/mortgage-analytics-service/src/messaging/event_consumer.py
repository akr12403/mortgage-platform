"""Analytics SQS consumer (M5 optional queue: capstone-mortgage-analytics-dev).

SNS topic capstone-mortgage-lifecycle-dev fans out to this service's own queue. Each lifecycle
event triggers a refresh of the cached portfolio snapshot. The consumer is idempotent (bounded
eventId dedupe cache) and acknowledges a message only after it has been handled; failures stay
on the queue and SQS moves them to capstone-mortgage-analytics-dlq-dev after maxReceiveCount.

The event-handling logic (AnalyticsEventProcessor) has no AWS imports so it can be unit tested
without boto3; SqsAnalyticsConsumer wraps it with the SQS polling loop.
"""
from __future__ import annotations

import json
import logging
import threading
import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Callable, Optional

logger = logging.getLogger(__name__)

KNOWN_EVENT_TYPES = {"MortgageCreated", "LoanApproved", "PaymentReceived", "PaymentMissed", "LoanDelinquent"}
REQUIRED_ENVELOPE_FIELDS = ("eventId", "eventType", "schemaVersion", "occurredAt", "correlationId", "payload")
SUPPORTED_SCHEMA_MAJOR = "1."


class InvalidEventError(ValueError):
    """Raised for envelopes that must not be acknowledged (they will retry, then dead-letter)."""


def parse_envelope(body: str) -> dict:
    try:
        node = json.loads(body)
    except json.JSONDecodeError as exc:
        raise InvalidEventError(f"Message body is not JSON: {exc}") from exc
    # Support both raw delivery and the SNS JSON wrapper.
    if isinstance(node, dict) and "TopicArn" in node and isinstance(node.get("Message"), str):
        return parse_envelope(node["Message"])
    if not isinstance(node, dict):
        raise InvalidEventError("Event envelope must be a JSON object")
    missing = [field for field in REQUIRED_ENVELOPE_FIELDS if node.get(field) in (None, "")]
    if missing:
        raise InvalidEventError(f"Event envelope is missing {', '.join(missing)}")
    try:
        uuid.UUID(str(node["eventId"]))
    except ValueError as exc:
        raise InvalidEventError("eventId must be a UUID") from exc
    if not str(node["schemaVersion"]).startswith(SUPPORTED_SCHEMA_MAJOR):
        raise InvalidEventError(f"Unsupported schemaVersion {node['schemaVersion']}")
    if not isinstance(node["payload"], dict) or not node["payload"].get("mortgageExternalId"):
        raise InvalidEventError("payload.mortgageExternalId is required")
    return node


class AnalyticsEventProcessor:
    """Validates, dedupes and applies lifecycle events (refreshes the portfolio snapshot)."""

    def __init__(self, refresh_snapshot: Callable[[], dict], dedupe_capacity: int = 10_000):
        self._refresh_snapshot = refresh_snapshot
        self._seen: OrderedDict[str, None] = OrderedDict()
        self._capacity = dedupe_capacity
        self._lock = threading.Lock()
        self._counts: dict[str, int] = {}
        self._duplicates = 0
        self._failures = 0
        self._last_event: Optional[dict] = None
        self._snapshot: Optional[dict] = None
        self._snapshot_refreshed_at: Optional[str] = None

    def handle(self, body: str) -> str:
        """Returns PROCESSED, DUPLICATE or SKIPPED. Raises InvalidEventError / other errors on failure."""
        event = parse_envelope(body)
        event_id = str(event["eventId"])
        event_type = event["eventType"]

        with self._lock:
            if event_id in self._seen:
                self._duplicates += 1
                return "DUPLICATE"

        if event_type not in KNOWN_EVENT_TYPES:
            logger.warning("Skipping unknown eventType %s (eventId=%s, correlationId=%s)",
                           event_type, event_id, event["correlationId"])
            self._remember(event_id)
            return "SKIPPED"

        snapshot = self._refresh_snapshot()

        with self._lock:
            self._snapshot = snapshot
            self._snapshot_refreshed_at = datetime.now(timezone.utc).isoformat()
            self._counts[event_type] = self._counts.get(event_type, 0) + 1
            self._last_event = {
                "eventId": event_id,
                "eventType": event_type,
                "mortgageExternalId": event["payload"]["mortgageExternalId"],
                "correlationId": event["correlationId"],
                "occurredAt": event["occurredAt"],
            }
        self._remember(event_id)
        logger.info("Processed %s for %s (eventId=%s, correlationId=%s)", event_type,
                    event["payload"]["mortgageExternalId"], event_id, event["correlationId"])
        return "PROCESSED"

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1

    def _remember(self, event_id: str) -> None:
        with self._lock:
            self._seen[event_id] = None
            while len(self._seen) > self._capacity:
                self._seen.popitem(last=False)

    def stats(self) -> dict:
        with self._lock:
            return {
                "eventsProcessed": dict(self._counts),
                "duplicatesIgnored": self._duplicates,
                "failures": self._failures,
                "lastEvent": self._last_event,
                "portfolioSnapshot": self._snapshot,
                "snapshotRefreshedAt": self._snapshot_refreshed_at,
            }


class SqsAnalyticsConsumer(threading.Thread):
    """Long-polls the analytics queue on a daemon thread."""

    def __init__(self, queue_url: str, processor: AnalyticsEventProcessor, sqs_client,
                 max_receive_count: int = 3, wait_seconds: int = 5):
        super().__init__(name="analytics-sqs-consumer", daemon=True)
        self.queue_url = queue_url
        self.processor = processor
        self.sqs = sqs_client
        self.max_receive_count = max_receive_count
        self.wait_seconds = wait_seconds
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        logger.info("Analytics consumer polling %s", self.queue_url)
        while not self._stop_event.is_set():
            try:
                response = self.sqs.receive_message(
                    QueueUrl=self.queue_url,
                    MaxNumberOfMessages=5,
                    WaitTimeSeconds=self.wait_seconds,
                    AttributeNames=["ApproximateReceiveCount"],
                )
            except Exception:  # noqa: BLE001 - keep the loop alive; surface at ERROR
                logger.exception("Unable to poll analytics event queue %s", self.queue_url)
                self._stop_event.wait(5)
                continue
            for message in response.get("Messages", []):
                self.process_message(message)

    def process_message(self, message: dict) -> str:
        receive_count = int(message.get("Attributes", {}).get("ApproximateReceiveCount", "1"))
        try:
            outcome = self.processor.handle(message["Body"])
        except Exception as exc:  # noqa: BLE001
            self.processor.record_failure()
            if receive_count >= self.max_receive_count:
                logger.error("Analytics event failed on final attempt %s/%s; SQS will move messageId=%s to the DLQ: %s",
                             receive_count, self.max_receive_count, message.get("MessageId"), exc)
            else:
                logger.error("Analytics event failed on attempt %s/%s; messageId=%s left for retry: %s",
                             receive_count, self.max_receive_count, message.get("MessageId"), exc)
            return "FAILED"
        self.sqs.delete_message(QueueUrl=self.queue_url, ReceiptHandle=message["ReceiptHandle"])
        return outcome
