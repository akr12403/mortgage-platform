import json
import uuid

import pytest

from src.messaging.event_consumer import (
    AnalyticsEventProcessor,
    InvalidEventError,
    SqsAnalyticsConsumer,
    parse_envelope,
)


def envelope(event_type="PaymentReceived", schema_version="1.0", event_id=None, payload=None):
    return json.dumps({
        "eventId": event_id or str(uuid.uuid4()),
        "eventType": event_type,
        "schemaVersion": schema_version,
        "occurredAt": "2026-03-15T14:30:00Z",
        "correlationId": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
        "payload": payload or {"mortgageExternalId": "MTG-1001", "paymentAmount": 1850.0},
    })


class FakeSqs:
    def __init__(self):
        self.deleted = []

    def delete_message(self, QueueUrl, ReceiptHandle):
        self.deleted.append(ReceiptHandle)


def make_processor():
    calls = []

    def refresh():
        calls.append(1)
        return {"totalMortgages": 12, "delinquencyRate": 0.2}

    return AnalyticsEventProcessor(refresh), calls


def test_known_event_refreshes_snapshot_and_counts():
    processor, calls = make_processor()
    assert processor.handle(envelope()) == "PROCESSED"
    stats = processor.stats()
    assert calls == [1]
    assert stats["eventsProcessed"] == {"PaymentReceived": 1}
    assert stats["portfolioSnapshot"]["totalMortgages"] == 12
    assert stats["lastEvent"]["mortgageExternalId"] == "MTG-1001"


def test_duplicate_event_id_is_ignored():
    processor, calls = make_processor()
    event_id = str(uuid.uuid4())
    assert processor.handle(envelope(event_id=event_id)) == "PROCESSED"
    assert processor.handle(envelope(event_id=event_id)) == "DUPLICATE"
    assert calls == [1]
    assert processor.stats()["duplicatesIgnored"] == 1


def test_unknown_event_type_is_skipped():
    processor, calls = make_processor()
    assert processor.handle(envelope(event_type="EscrowAnalyzed")) == "SKIPPED"
    assert calls == []


@pytest.mark.parametrize("body", [
    "not json",
    json.dumps({"eventType": "PaymentReceived"}),
    envelope(schema_version="2.0"),
    envelope(payload={"paymentAmount": 1.0}),
])
def test_invalid_envelopes_raise(body):
    with pytest.raises(InvalidEventError):
        parse_envelope(body)


def test_sns_wrapper_is_unwrapped():
    wrapped = json.dumps({"Type": "Notification", "TopicArn": "arn:aws:sns:us-east-1:000000000000:x",
                          "Message": envelope()})
    assert parse_envelope(wrapped)["eventType"] == "PaymentReceived"


def test_consumer_acknowledges_only_successful_messages():
    processor, _ = make_processor()
    sqs = FakeSqs()
    consumer = SqsAnalyticsConsumer("queue-url", processor, sqs, max_receive_count=3)

    ok = consumer.process_message({"MessageId": "1", "ReceiptHandle": "rh-ok", "Body": envelope(),
                                   "Attributes": {"ApproximateReceiveCount": "1"}})
    bad = consumer.process_message({"MessageId": "2", "ReceiptHandle": "rh-bad", "Body": "not json",
                                    "Attributes": {"ApproximateReceiveCount": "3"}})

    assert ok == "PROCESSED"
    assert bad == "FAILED"
    assert sqs.deleted == ["rh-ok"]
    assert processor.stats()["failures"] == 1
