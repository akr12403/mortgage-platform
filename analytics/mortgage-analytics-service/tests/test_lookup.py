"""M8 Task 8.4: DynamoDB mortgage lookup (store, bulk load, event updates, API read path). DynamoDB is faked."""
import json
import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.api.routes.lookup import get_lookup_store
from src.messaging.event_consumer import AnalyticsEventProcessor
from src.services import lookup_service
from src.services.lookup_service import LookupUnavailableError, MortgageLookupStore
from tests.conftest import auth_header

TABLE = "CapstoneMortgageLookup-dev"


class ConditionalCheckFailedException(Exception):
    pass


class FakeDynamo:
    """Implements just enough of GetItem / UpdateItem (incl. our condition) / BatchWriteItem."""

    def __init__(self, unprocessed_first=0):
        self.items = {}
        self.batches = []
        self._unprocessed_first = unprocessed_first

    def get_item(self, TableName, Key):
        item = self.items.get(Key["mortgageExternalId"]["S"])
        return {"Item": item} if item else {}

    def update_item(self, TableName, Key, UpdateExpression, ConditionExpression, ExpressionAttributeNames,
                    ExpressionAttributeValues):
        pk = Key["mortgageExternalId"]["S"]
        current = self.items.get(pk, {})
        at, eid = ExpressionAttributeValues[":at"]["S"], ExpressionAttributeValues[":id"]["S"]
        last_at = current.get("lastEventAt", {}).get("S")
        last_id = current.get("lastEventId", {}).get("S")
        if not (last_at is None or last_at < at or (last_at == at and last_id != eid)):
            raise ConditionalCheckFailedException("The conditional request failed")
        item = dict(current, mortgageExternalId={"S": pk})
        for part in UpdateExpression[len("SET "):].split(", "):
            name, value = part.split(" = ")
            item[ExpressionAttributeNames[name]] = ExpressionAttributeValues[value]
        self.items[pk] = item

    def batch_write_item(self, RequestItems):
        requests = RequestItems[TABLE]
        self.batches.append(len(requests))
        keep = requests
        unprocessed = []
        if self._unprocessed_first:
            keep, unprocessed = requests[:-self._unprocessed_first], requests[-self._unprocessed_first:]
            self._unprocessed_first = 0
        for request in keep:
            item = request["PutRequest"]["Item"]
            self.items[item["mortgageExternalId"]["S"]] = item
        return {"UnprocessedItems": {TABLE: unprocessed} if unprocessed else {}}


def row(n, balance="305000.00", status="ACTIVE"):
    return {"mortgage_external_id": f"MTG-{n}", "borrower_external_id": "BOR-001", "status": status,
            "outstanding_balance": Decimal(balance), "original_amount": Decimal("310000.00"),
            "origination_date": "2024-01-15"}


def event(event_type, payload, occurred="2026-11-03T10:00:00Z", event_id=None):
    return {"eventId": event_id or str(uuid.uuid4()), "eventType": event_type, "schemaVersion": "1.0",
            "occurredAt": occurred, "correlationId": "cid-1", "payload": payload}


# ---------- store ----------

def test_bulk_load_writes_every_row_in_batches_of_25_and_retries_unprocessed(monkeypatch):
    monkeypatch.setattr(lookup_service.time, "sleep", lambda s: None)
    fake = FakeDynamo(unprocessed_first=3)
    store = MortgageLookupStore(TABLE, fake)
    written = store.bulk_load([row(1000 + i) for i in range(60)])
    assert written == 60 and len(fake.items) == 60
    assert fake.batches[:3] == [25, 3, 25]  # 3 throttled items retried before the next batch
    assert fake.items["MTG-1007"]["outstandingBalance"] == {"N": "305000.00"}
    assert "firstName" not in json.dumps(fake.items) and "email" not in json.dumps(fake.items)


def test_get_returns_plain_values_and_none_when_missing():
    fake = FakeDynamo()
    store = MortgageLookupStore(TABLE, fake)
    store.bulk_load([row(1002, balance="198250.50")])
    item = store.get("MTG-1002")
    assert item["outstandingBalance"] == 198250.5 and item["status"] == "ACTIVE"
    assert item["borrowerExternalId"] == "BOR-001" and item["source"] == "pg-bulk-load"
    assert store.get("MTG-9999") is None


def test_unconfigured_store_raises_unavailable():
    with pytest.raises(LookupUnavailableError):
        MortgageLookupStore(table="", client=FakeDynamo()).get("MTG-1001")


def test_payment_received_updates_balance_and_redelivery_is_ignored():
    fake = FakeDynamo()
    store = MortgageLookupStore(TABLE, fake)
    store.bulk_load([row(1001)])
    pay = event("PaymentReceived", {"mortgageExternalId": "MTG-1001", "paymentAmount": 1850.0,
                                    "paidDate": "2026-11-03", "outstandingBalanceAfter": 303150.0})
    assert store.apply_event(pay) == "UPDATED"
    assert store.get("MTG-1001")["outstandingBalance"] == 303150.0
    assert store.get("MTG-1001")["lastEventType"] == "PaymentReceived"
    assert store.apply_event(pay) == "STALE"  # SQS at-least-once redelivery: same event, no change


def test_older_event_cannot_roll_the_cache_back():
    fake = FakeDynamo()
    store = MortgageLookupStore(TABLE, fake)
    newer = event("PaymentReceived", {"mortgageExternalId": "MTG-1001", "outstandingBalanceAfter": 300000.0},
                  occurred="2026-11-03T12:00:00Z")
    older = event("PaymentReceived", {"mortgageExternalId": "MTG-1001", "outstandingBalanceAfter": 301850.0},
                  occurred="2026-11-03T11:00:00Z")
    assert store.apply_event(newer) == "UPDATED"
    assert store.apply_event(older) == "STALE"
    assert store.get("MTG-1001")["outstandingBalance"] == 300000.0


def test_loan_delinquent_sets_status_days_and_severity():
    fake = FakeDynamo()
    store = MortgageLookupStore(TABLE, fake)
    store.bulk_load([row(1005)])
    store.apply_event(event("LoanDelinquent", {"mortgageExternalId": "MTG-1005", "delinquentSince": "2026-10-01",
                                               "daysPastDue": 33, "severity": "MODERATE"}))
    item = store.get("MTG-1005")
    assert (item["status"], item["daysPastDue"], item["delinquencySeverity"]) == ("DELINQUENT", 33, "MODERATE")


def test_processor_calls_lookup_update_before_ack_and_counts_outcomes():
    fake = FakeDynamo()
    store = MortgageLookupStore(TABLE, fake)
    processor = AnalyticsEventProcessor(lambda: {"totalMortgages": 1}, on_event=store.apply_event)
    body = json.dumps(event("PaymentReceived", {"mortgageExternalId": "MTG-1003", "outstandingBalanceAfter": 1.0}))
    assert processor.handle(body) == "PROCESSED"
    assert processor.stats()["lookupUpdates"] == {"UPDATED": 1}
    assert fake.items["MTG-1003"]["outstandingBalance"] == {"N": "1.00"}


def test_lookup_failure_propagates_so_the_message_is_retried():
    def broken(_event):
        raise RuntimeError("DynamoDB unavailable")
    processor = AnalyticsEventProcessor(lambda: {}, on_event=broken)
    with pytest.raises(RuntimeError):
        processor.handle(json.dumps(event("PaymentReceived", {"mortgageExternalId": "MTG-1003"})))


def test_dynamodb_client_targets_real_aws_when_endpoint_is_empty(monkeypatch):
    monkeypatch.setenv("AWS_ENDPOINT_URL", "http://localstack:4566")
    monkeypatch.setenv("DYNAMODB_ENDPOINT_URL", "")
    monkeypatch.setenv("DYNAMODB_REGION", "us-east-2")
    client = lookup_service._client()
    assert client.meta.endpoint_url == "https://dynamodb.us-east-2.amazonaws.com"


# ---------- API read path ----------

@pytest.fixture
def api():
    fake = FakeDynamo()
    store = MortgageLookupStore(TABLE, fake)
    store.bulk_load([row(1002)])
    app.dependency_overrides[get_lookup_store] = lambda: store
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.mark.parametrize("role,expected", [("ADMIN", 200), ("UNDERWRITER", 200), ("SERVICING_AGENT", 200),
                                           ("RISK_ANALYST", 200), ("SUPPORT", 403)])
def test_lookup_endpoint_role_matrix(api, role, expected):
    response = api.get("/api/v1/lookup/mortgages/MTG-1002", headers=auth_header(role))
    assert response.status_code == expected
    if expected == 200:
        body = response.json()
        assert body["mortgageExternalId"] == "MTG-1002" and body["lookupSource"] == "dynamodb"
        assert body["outstandingBalance"] == 305000.0


def test_lookup_endpoint_404_400_401(api):
    assert api.get("/api/v1/lookup/mortgages/MTG-9999", headers=auth_header("ADMIN")).json()["code"] == "NOT_FOUND"
    assert api.get("/api/v1/lookup/mortgages/BOR-001", headers=auth_header("ADMIN")).status_code == 400
    assert api.get("/api/v1/lookup/mortgages/MTG-1002").status_code == 401


def test_lookup_endpoint_503_when_dynamodb_not_configured():
    app.dependency_overrides[get_lookup_store] = lambda: MortgageLookupStore(table="", client=FakeDynamo())
    try:
        response = TestClient(app).get("/api/v1/lookup/mortgages/MTG-1002", headers=auth_header("ADMIN"))
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 503 and response.json()["code"] == "LOOKUP_UNAVAILABLE"
