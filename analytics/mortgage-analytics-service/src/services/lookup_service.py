"""M8 Task 8.4: fast mortgage lookup in DynamoDB table CapstoneMortgageLookup-dev.

Access pattern: one item per mortgage, read by key (GetItem on PK mortgageExternalId). PostgreSQL stays the system
of record (ADR-001); the table is a cache that is
  * bulk-loaded from PostgreSQL (python -m src.services.lookup_load, scripts/aws/lookup-load.sh) and
  * kept current by lifecycle events from the analytics SQS queue (apply_event), e.g. PaymentReceived updates
    outstandingBalance, LoanDelinquent sets status DELINQUENT.

Event updates are conditional: an event older than the one already applied (or the same event again) is ignored,
so SQS redelivery and out-of-order delivery cannot roll the cache back. No borrower PII is stored (no names,
contact details or date of birth): only business IDs, status and amounts.

IAM (mortgage-analytics-role): dynamodb:GetItem, PutItem, UpdateItem, BatchWriteItem on this table only.
"""
from __future__ import annotations

import logging
import os
import random
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterable, Optional

logger = logging.getLogger(__name__)

TABLE_ENV = "DYNAMODB_LOOKUP_TABLE"


class LookupUnavailableError(RuntimeError):
    """DynamoDB is not configured or could not be reached."""


def _client():
    import boto3
    from botocore.config import Config

    endpoint = os.getenv("DYNAMODB_ENDPOINT_URL")
    # Same rule as s3_service: DYNAMODB_ENDPOINT_URL="" means real AWS even when AWS_ENDPOINT_URL points at LocalStack.
    endpoint_url = (os.getenv("AWS_ENDPOINT_URL", "") if endpoint is None else endpoint) or None
    region = os.getenv("DYNAMODB_REGION") or os.getenv("AWS_REGION") or None
    config = Config(retries={"max_attempts": 3, "mode": "standard"}, connect_timeout=3, read_timeout=5,
                    ignore_configured_endpoint_urls=(endpoint == ""))
    return boto3.client("dynamodb", config=config, endpoint_url=endpoint_url, region_name=region)


def _num(value) -> dict:
    return {"N": str(Decimal(str(value)).quantize(Decimal("0.01")))}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _plain(item: dict) -> dict:
    out = {}
    for key, value in item.items():
        if "S" in value:
            out[key] = value["S"]
        elif "N" in value:
            number = Decimal(value["N"])
            out[key] = int(number) if number == number.to_integral_value() and key == "daysPastDue" else float(number)
    return out


# eventType -> (SET expression parts, value builder). Only fields the event actually carries are written.
def _event_updates(event_type: str, payload: dict) -> dict:
    if event_type == "MortgageCreated":
        updates = {"status": {"S": payload["status"]}} if payload.get("status") else {}
        if payload.get("borrowerExternalId"):
            updates["borrowerExternalId"] = {"S": payload["borrowerExternalId"]}
        if payload.get("originalAmount") is not None:
            updates["originalAmount"] = _num(payload["originalAmount"])
        return updates
    if event_type == "LoanApproved":
        return {"underwritingDecision": {"S": payload["underwritingDecision"]}} if payload.get("underwritingDecision") else {}
    if event_type == "PaymentReceived":
        updates = {}
        if payload.get("outstandingBalanceAfter") is not None:
            updates["outstandingBalance"] = _num(payload["outstandingBalanceAfter"])
        if payload.get("paidDate"):
            updates["lastPaymentDate"] = {"S": payload["paidDate"]}
        return updates
    if event_type == "PaymentMissed":
        updates = {}
        if payload.get("daysPastDue") is not None:
            updates["daysPastDue"] = {"N": str(int(payload["daysPastDue"]))}
        if payload.get("dueDate"):
            updates["lastMissedDueDate"] = {"S": payload["dueDate"]}
        return updates
    if event_type == "LoanDelinquent":
        updates = {"status": {"S": "DELINQUENT"}}
        if payload.get("daysPastDue") is not None:
            updates["daysPastDue"] = {"N": str(int(payload["daysPastDue"]))}
        if payload.get("severity"):
            updates["delinquencySeverity"] = {"S": payload["severity"]}
        return updates
    return {}


class MortgageLookupStore:
    def __init__(self, table: Optional[str] = None, client=None):
        self.table = table or os.getenv(TABLE_ENV, "")
        self._client = client

    @property
    def configured(self) -> bool:
        return bool(self.table)

    @property
    def client(self):
        if self._client is None:
            self._client = _client()
        return self._client

    def get(self, mortgage_external_id: str) -> Optional[dict]:
        if not self.configured:
            raise LookupUnavailableError(f"{TABLE_ENV} is not set")
        try:
            response = self.client.get_item(TableName=self.table, Key={"mortgageExternalId": {"S": mortgage_external_id}})
        except Exception as exc:  # botocore errors: credentials, network, throttling
            raise LookupUnavailableError(type(exc).__name__) from exc
        item = response.get("Item")
        return _plain(item) if item else None

    def apply_event(self, event: dict) -> str:
        """UPDATED, or STALE when the item already reflects this or a newer event. Raises on DynamoDB errors."""
        payload = event["payload"]
        updates = _event_updates(event["eventType"], payload)
        names = {f"#a{i}": key for i, key in enumerate(updates)}
        values = {f":v{i}": value for i, value in enumerate(updates.values())}
        sets = [f"#a{i} = :v{i}" for i in range(len(updates))]
        names.update({"#le": "lastEventAt", "#lid": "lastEventId", "#lt": "lastEventType", "#u": "updatedAt", "#src": "source"})
        values.update({":at": {"S": event["occurredAt"]}, ":id": {"S": str(event["eventId"])},
                       ":t": {"S": event["eventType"]}, ":now": {"S": _now()}, ":src": {"S": "event"}})
        sets += ["#le = :at", "#lid = :id", "#lt = :t", "#u = :now", "#src = :src"]
        try:
            self.client.update_item(
                TableName=self.table,
                Key={"mortgageExternalId": {"S": payload["mortgageExternalId"]}},
                UpdateExpression="SET " + ", ".join(sets),
                ConditionExpression="(attribute_not_exists(#le) OR #le < :at) OR (#le = :at AND #lid <> :id)",
                ExpressionAttributeNames=names,
                ExpressionAttributeValues=values,
            )
        except Exception as exc:
            if type(exc).__name__ == "ConditionalCheckFailedException" or "ConditionalCheckFailed" in str(exc):
                return "STALE"
            raise
        return "UPDATED"

    def bulk_load(self, rows: Iterable[dict], batch_size: int = 25, max_retries: int = 5) -> int:
        """Write one item per PostgreSQL row with BatchWriteItem (25 per request, the API maximum).

        Rows are shuffled first: a bulk load in key order (MTG-1001, MTG-1002, ...) would otherwise send runs of
        neighbouring keys in the same instant. DynamoDB hashes the partition key, so this matters little at this
        size, but it is the Session 29 rule for bulk loads (see docs/architecture/aws-dynamodb-mortgage-lookup.md).
        """
        items = [self._row_item(row) for row in rows]
        random.shuffle(items)
        written = 0
        for start in range(0, len(items), batch_size):
            pending = [{"PutRequest": {"Item": item}} for item in items[start:start + batch_size]]
            for attempt in range(max_retries + 1):
                response = self.client.batch_write_item(RequestItems={self.table: pending})
                unprocessed = response.get("UnprocessedItems", {}).get(self.table, [])
                written += len(pending) - len(unprocessed)
                if not unprocessed:
                    break
                if attempt == max_retries:
                    raise LookupUnavailableError(f"{len(unprocessed)} items still unprocessed after {max_retries} retries")
                pending = unprocessed
                time.sleep(min(2 ** attempt * 0.1, 2.0))  # exponential backoff on throttling
        return written

    @staticmethod
    def _row_item(row: dict) -> dict:
        item = {
            "mortgageExternalId": {"S": row["mortgage_external_id"]},
            "borrowerExternalId": {"S": row["borrower_external_id"]},
            "status": {"S": row["status"]},
            "outstandingBalance": _num(row["outstanding_balance"]),
            "originalAmount": _num(row["original_amount"]),
            "originationDate": {"S": str(row["origination_date"])},
            "updatedAt": {"S": _now()},
            "source": {"S": "pg-bulk-load"},
        }
        return item
